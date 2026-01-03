# Hatchet-Lite Performance Optimization Guide for Integration Tests

## Overview

This guide documents performance optimization options for **hatchet-lite** (self-hosted Hatchet) specifically for integration test environments where fast startup and low task queuing latency are critical.

**Key Sources:**
- [Hatchet GitHub Repository](https://github.com/hatchet-dev/hatchet)
- [Hatchet Documentation](https://docs.hatchet.run/)
- [Self-Hosting Performance Guide](https://docs.hatchet.run/self-hosting/improving-performance)

---

## Architecture Understanding

Hatchet-lite bundles three components in a single process:
1. **API Server** - REST API for management
2. **Engine** - Workflow orchestration and scheduling
3. **Static File Server** - Frontend UI

It uses either **PostgreSQL** (default) or **RabbitMQ** as the message queue backend.

---

## Performance Knobs Summary

### 1. Startup Time Optimization

| Setting | Default | Recommended for Tests | Description |
|---------|---------|----------------------|-------------|
| `SERVER_SECURITY_CHECK_ENABLED` | `true` | `false` | Disables external security endpoint check |
| Postgres healthcheck interval | 10s | 2s | Faster healthcheck polling |
| Postgres `start_period` | 10s | 2s | Reduces initial wait time |
| Postgres `fsync` | `on` | `off` | **Test only** - disables disk sync for speed |
| Postgres `synchronous_commit` | `on` | `off` | **Test only** - async commits |

### 2. Buffer/Flush Settings (Queue Latency)

These control how quickly writes are batched and sent to the database:

| Setting | Default | Fast Tests | High Throughput |
|---------|---------|-----------|-----------------|
| `SERVER_FLUSH_PERIOD_MILLISECONDS` | 10 | 5 | 250 |
| `SERVER_FLUSH_ITEMS_THRESHOLD` | 100 | 10 | 1000 |
| `SERVER_WORKFLOWRUNBUFFER_FLUSH_PERIOD_MILLISECONDS` | 10 | 5 | 100 |
| `SERVER_WORKFLOWRUNBUFFER_FLUSH_ITEMS_THRESHOLD` | 100 | 10 | 500 |
| `SERVER_EVENTBUFFER_FLUSH_PERIOD_MILLISECONDS` | 10 | 5 | 1000 |
| `SERVER_EVENTBUFFER_FLUSH_ITEMS_THRESHOLD` | 100 | 10 | 1000 |
| `SERVER_QUEUESTEPRUNBUFFER_FLUSH_PERIOD_MILLISECONDS` | 10 | 5 | 100 |
| `SERVER_QUEUESTEPRUNBUFFER_FLUSH_ITEMS_THRESHOLD` | 100 | 10 | 500 |
| `SERVER_RELEASESEMAPHOREBUFFER_FLUSH_PERIOD_MILLISECONDS` | 10 | 5 | 100 |
| `SERVER_RELEASESEMAPHOREBUFFER_FLUSH_ITEMS_THRESHOLD` | 100 | 10 | 200 |

**Trade-off**: Smaller values = lower latency but more DB writes. Larger values = higher throughput but more latency.

### 3. Scheduler/Polling Settings

| Setting | Default | Recommended for Tests | Description |
|---------|---------|----------------------|-------------|
| `SCHEDULER_CONCURRENCY_RATE_LIMIT` | 20 | 100 | Rate limit per second |
| `SCHEDULER_CONCURRENCY_POLLING_MIN_INTERVAL` | 500ms | 50ms | Min polling interval |
| `SCHEDULER_CONCURRENCY_POLLING_MAX_INTERVAL` | 5s | 200ms | Max polling interval |
| `SERVER_OPERATIONS_POLL_INTERVAL` | 2s | 1s | Status update polling |

### 4. Message Queue Settings

**For PostgreSQL Queue (default in hatchet-lite):**

| Setting | Default | Recommended | Description |
|---------|---------|-------------|-------------|
| `SERVER_MSGQUEUE_KIND` | `postgres` | `postgres` | Queue backend type |
| `SERVER_MSGQUEUE_POSTGRES_QOS` | 100 | 200 | Parallel message processing |

**For RabbitMQ Queue (optional):**

| Setting | Default | Recommended | Description |
|---------|---------|-------------|-------------|
| `SERVER_MSGQUEUE_KIND` | - | `rabbitmq` | Use RabbitMQ backend |
| `SERVER_MSGQUEUE_RABBITMQ_URL` | - | `amqp://...` | RabbitMQ connection |
| `SERVER_MSGQUEUE_RABBITMQ_QOS` | 100 | 200 | Parallel processing |
| `SERVER_MSGQUEUE_RABBITMQ_MAX_PUB_CHANS` | 20 | 40 | Publisher channels |
| `SERVER_MSGQUEUE_RABBITMQ_MAX_SUB_CHANS` | 100 | 200 | Subscriber channels |

### 5. Database Connection Settings

| Setting | Default | High Performance | Description |
|---------|---------|-----------------|-------------|
| `DATABASE_MAX_CONNS` | 50 | 100 | Max DB connections |
| `DATABASE_MIN_CONNS` | 1 | 10 | Min connection pool |
| `DATABASE_MAX_QUEUE_CONNS` | 50 | 100 | Queue pool max |
| `DATABASE_MIN_QUEUE_CONNS` | 10 | 20 | Queue pool min |
| Postgres `max_connections` | 100 | 200-500 | Total allowed connections |

---

## Recommended Configurations

### Configuration A: Fast Integration Tests (Low Latency)

```yaml
environment:
  # Disable security check
  SERVER_SECURITY_CHECK_ENABLED: "false"

  # Very fast buffer flushes
  SERVER_FLUSH_PERIOD_MILLISECONDS: "5"
  SERVER_FLUSH_ITEMS_THRESHOLD: "10"
  SERVER_WORKFLOWRUNBUFFER_FLUSH_PERIOD_MILLISECONDS: "5"
  SERVER_WORKFLOWRUNBUFFER_FLUSH_ITEMS_THRESHOLD: "10"
  SERVER_QUEUESTEPRUNBUFFER_FLUSH_PERIOD_MILLISECONDS: "5"
  SERVER_QUEUESTEPRUNBUFFER_FLUSH_ITEMS_THRESHOLD: "10"

  # Aggressive polling
  SCHEDULER_CONCURRENCY_RATE_LIMIT: "100"
  SCHEDULER_CONCURRENCY_POLLING_MIN_INTERVAL: "50ms"
  SCHEDULER_CONCURRENCY_POLLING_MAX_INTERVAL: "200ms"
  SERVER_OPERATIONS_POLL_INTERVAL: "1"

  # Increase parallelism
  SERVER_MSGQUEUE_POSTGRES_QOS: "200"
```

**Expected Latency**: ~50-100ms queuing latency

### Configuration B: High Throughput Tests

```yaml
environment:
  # Batched writes for throughput
  SERVER_FLUSH_PERIOD_MILLISECONDS: "100"
  SERVER_FLUSH_ITEMS_THRESHOLD: "500"
  SERVER_WORKFLOWRUNBUFFER_FLUSH_PERIOD_MILLISECONDS: "100"
  SERVER_WORKFLOWRUNBUFFER_FLUSH_ITEMS_THRESHOLD: "500"

  # Balance polling
  SCHEDULER_CONCURRENCY_RATE_LIMIT: "50"
  SCHEDULER_CONCURRENCY_POLLING_MIN_INTERVAL: "100ms"
  SCHEDULER_CONCURRENCY_POLLING_MAX_INTERVAL: "1s"

  # High connection pool
  DATABASE_MAX_CONNS: "100"
  DATABASE_MIN_CONNS: "20"
```

**Expected Throughput**: 100+ tasks/second

### Configuration C: Using RabbitMQ (Higher Scale)

```yaml
services:
  rabbitmq:
    image: "rabbitmq:3-management"
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: "user"
      RABBITMQ_DEFAULT_PASS: "password"
    healthcheck:
      test: ["CMD", "rabbitmqctl", "status"]
      interval: 5s
      timeout: 5s
      retries: 10

  hatchet-lite:
    environment:
      SERVER_MSGQUEUE_KIND: "rabbitmq"
      SERVER_MSGQUEUE_RABBITMQ_URL: "amqp://user:password@rabbitmq:5672/"
      SERVER_MSGQUEUE_RABBITMQ_QOS: "200"
```

---

## PostgreSQL Optimizations for Tests

For ephemeral test databases, these unsafe-but-fast settings can be used:

```yaml
postgres:
  command: >
    postgres
    -c 'max_connections=200'
    -c 'shared_buffers=128MB'
    -c 'fsync=off'
    -c 'synchronous_commit=off'
    -c 'full_page_writes=off'
```

**WARNING**: These settings disable durability guarantees. Only use for tests!

---

## Latency Breakdown

Based on analysis of the codebase, task queuing latency comes from:

1. **Client → Engine gRPC call**: ~1-5ms
2. **Engine buffer flush**: 5-250ms (configurable)
3. **Database write**: ~1-10ms
4. **Scheduler polling**: 50ms-5s (configurable)
5. **Task dispatch to worker**: ~1-5ms

**Total typical latency**: 60ms - 5s depending on configuration

### Optimizing for Minimal Latency

To achieve sub-100ms task start times:
- Set `SCHEDULER_CONCURRENCY_POLLING_MIN_INTERVAL` to `50ms`
- Set `SERVER_FLUSH_PERIOD_MILLISECONDS` to `5`
- Set `SERVER_FLUSH_ITEMS_THRESHOLD` to `10`
- Keep worker connections warm

---

## Monitoring Performance

Enable Prometheus metrics for observability:

```yaml
environment:
  SERVER_PROMETHEUS_ENABLED: "true"
  SERVER_PROMETHEUS_ADDRESS: ":9090"
  SERVER_PROMETHEUS_PATH: "/metrics"
```

Key metrics to watch:
- `hatchet_task_queue_latency_seconds` - Time in queue
- `hatchet_task_execution_time_seconds` - Task execution time
- `hatchet_scheduler_poll_duration_seconds` - Scheduler loop time
- `hatchet_db_query_duration_seconds` - Database query times

---

## Files Created for Testing

```
hatchet-test/
├── docker-compose.hatchet.yml  # Optimized docker-compose for tests
├── requirements.txt            # Python dependencies
├── hatchet_client.py          # Shared Hatchet client
├── workflows.py               # Benchmark workflows
├── worker.py                  # Worker process
├── benchmark.py               # Performance benchmark runner
└── run_tests.sh               # Complete test runner script
```

---

## Running the Benchmarks

```bash
cd /home/user/research-repo/hatchet-test
./run_tests.sh
```

This will:
1. Start hatchet-lite with optimized settings
2. Wait for it to be healthy
3. Generate an API token
4. Start a Python worker
5. Run benchmarks measuring:
   - Single task queuing latency
   - Concurrent task throughput
   - Multi-step workflow timing

---

## Summary of Key Recommendations

For **Integration Tests**:
1. Use PostgreSQL queue (simpler, no extra service)
2. Set flush period to 5ms, threshold to 10
3. Set scheduler polling min to 50ms
4. Disable security check
5. Use unsafe Postgres settings (fsync=off)

For **Higher Throughput**:
1. Consider RabbitMQ backend
2. Increase buffer thresholds
3. Tune database connection pools
4. Use bulk endpoints when possible

**Expected Performance (optimized for tests)**:
- Startup time: ~10-15 seconds
- Single task latency: ~50-100ms
- Throughput: 50-100+ tasks/second
