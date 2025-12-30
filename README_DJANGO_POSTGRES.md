# Django Ninja + PostgreSQL + PgBouncer Demo

This project demonstrates a production-ready Django Ninja application with:
- **PostgreSQL** with pgvector extension for vector similarity search
- **PgBouncer** for connection pooling (transaction mode)
- **SQLAlchemy** for advanced database operations alongside Django ORM
- **Dual database configuration** (pooled + direct connections)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Django Application                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Django Ninja API                          │ │
│  │  ┌───────────────────┐    ┌───────────────────┐             │ │
│  │  │   Django ORM      │    │    SQLAlchemy     │             │ │
│  │  │   (Items, etc.)   │    │    (pgvector)     │             │ │
│  │  └─────────┬─────────┘    └─────────┬─────────┘             │ │
│  └────────────┼────────────────────────┼───────────────────────┘ │
│               │                        │                         │
│     ┌─────────┴────────────┐    ┌─────┴────────────┐            │
│     │   default (pooled)   │    │   direct         │            │
│     │   Port 6432          │    │   Port 5432      │            │
│     └─────────┬────────────┘    └─────┬────────────┘            │
└───────────────┼────────────────────────┼────────────────────────┘
                │                        │
       ┌────────▼────────┐      ┌───────▼────────┐
       │    PgBouncer    │      │   PostgreSQL   │
       │  (Transaction   │      │   (Direct)     │
       │   Pooling)      │      │                │
       └────────┬────────┘      └───────▲────────┘
                │                       │
                └───────────────────────┘
                         │
              ┌──────────▼──────────┐
              │     PostgreSQL      │
              │   (with pgvector)   │
              └─────────────────────┘
```

## Key Features

### 1. Dual Database Configuration
- **`default`** (pooled): Uses PgBouncer on port 6432 for web traffic
  - `DISABLE_SERVER_SIDE_CURSORS=True` for transaction pooling compatibility
- **`direct`**: Direct PostgreSQL connection on port 5432 for migrations and admin

### 2. Server-Side Cursor Handling
The `default` connection disables server-side cursors, which is **critical** for PgBouncer transaction pooling. Without this, `QuerySet.iterator()` and `aiterator()` can fail.

### 3. SQLAlchemy + pgvector
Direct SQLAlchemy access for advanced vector operations:
- Cosine similarity search
- L2 (Euclidean) distance search
- Inner product search
- Prepared statement handling

### 4. Prepared Statements with PgBouncer
PgBouncer is configured with `MAX_PREPARED_STATEMENTS=100` to support prepared statement tracking in transaction pooling mode.

## Quick Start

### 1. Start the Services

```bash
docker compose up -d
```

This starts:
- PostgreSQL with pgvector (port 5432)
- PgBouncer (port 6432)
- Django application (port 8000)

### 2. Run Migrations (Direct Connection)

```bash
docker compose exec web python manage.py migrate --database=direct
```

### 3. Setup SQLAlchemy Tables

```bash
docker compose exec web python manage.py setup_sqlalchemy_tables --seed=50
```

### 4. Access the API

- API Documentation: http://localhost:8000/api/docs
- Admin: http://localhost:8000/admin/

## API Endpoints

### Items (Django ORM)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/items/` | Create item |
| GET | `/api/items/` | List items |
| GET | `/api/items/{id}` | Get item |
| PUT | `/api/items/{id}` | Update item |
| DELETE | `/api/items/{id}` | Delete item |

### Connection Testing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/items/test/connection-info` | Show connection config |
| GET | `/api/items/test/iterator` | Test iterator (pooled) |
| GET | `/api/items/test/iterator-direct` | Test iterator (direct) |
| GET | `/api/items/test/transaction` | Test transaction behavior |

### Vector Search (SQLAlchemy + pgvector)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vectors/documents` | Create document |
| GET | `/api/vectors/documents` | List documents |
| POST | `/api/vectors/search/cosine` | Cosine similarity search |
| POST | `/api/vectors/search/l2` | L2 distance search |
| GET | `/api/vectors/test/prepared-statements` | Test prepared statements |
| GET | `/api/vectors/test/connection-reuse` | Test connection reuse |

## Testing

### Run All Tests

```bash
docker compose run --rm test
```

### Run Connection Tests

```bash
docker compose exec web python manage.py test_connections --iterations=20
```

### Run Pytest

```bash
docker compose exec web pytest tests/ -v
```

## Configuration

### Database Settings (settings.py)

```python
DATABASES = {
    # Pooled connection via PgBouncer
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'pgbouncer',
        'PORT': '6432',
        # CRITICAL: Disable server-side cursors for transaction pooling
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'CONN_HEALTH_CHECKS': True,
        'CONN_MAX_AGE': 60,
    },
    # Direct connection for migrations
    'direct': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'postgres',
        'PORT': '5432',
        'DISABLE_SERVER_SIDE_CURSORS': False,
    },
}
```

### PgBouncer Settings

| Setting | Value | Description |
|---------|-------|-------------|
| `POOL_MODE` | `transaction` | Release connection after each transaction |
| `DEFAULT_POOL_SIZE` | `20` | Connections per user/database |
| `MAX_CLIENT_CONN` | `100` | Max client connections |
| `MAX_PREPARED_STATEMENTS` | `100` | Track prepared statements |

## PgBouncer Gotchas

### 1. Server-Side Cursors
**Problem**: Django's `QuerySet.iterator()` uses server-side cursors, which break under transaction pooling.

**Solution**: Set `DISABLE_SERVER_SIDE_CURSORS=True` on the pooled connection.

### 2. Session Features
The following **don't work** with transaction pooling:
- `SET` / `RESET` commands
- `LISTEN` / `NOTIFY`
- Session-level advisory locks
- Temp tables with preserve semantics

**Solution**: Use the `direct` connection for these operations.

### 3. Migrations
**Problem**: Migrations can pin connections and use session features.

**Solution**: Always run migrations on the `direct` connection:
```bash
python manage.py migrate --database=direct
```

### 4. Prepared Statements
**Problem**: psycopg3 uses prepared statements by default, which can fail with PgBouncer.

**Solution**: Configure PgBouncer with `MAX_PREPARED_STATEMENTS > 0`.

## Project Structure

```
├── docker-compose.yml          # Docker services
├── Dockerfile                  # Django app container
├── requirements.txt            # Python dependencies
├── manage.py                   # Django management
│
├── myapp/                      # Django project
│   ├── settings.py             # Main settings (dual DB config)
│   ├── settings_local.py       # Local development settings
│   ├── db_router.py            # Database router
│   └── urls.py                 # URL configuration
│
├── sample/                     # Sample Django app
│   ├── models.py               # Django models
│   ├── api.py                  # Django Ninja API (ORM)
│   ├── api_sqlalchemy.py       # SQLAlchemy API (pgvector)
│   ├── sqlalchemy_models.py    # SQLAlchemy models
│   └── management/commands/    # Custom commands
│       ├── test_connections.py
│       └── setup_sqlalchemy_tables.py
│
├── tests/                      # Test suite
│   ├── conftest.py             # Pytest fixtures
│   ├── test_django_orm.py      # ORM tests
│   └── test_sqlalchemy_pgvector.py  # pgvector tests
│
├── docker/postgres/            # PostgreSQL init
│   └── init.sql                # Enable pgvector
│
└── scripts/
    └── run_tests.sh            # Comprehensive test script
```

## Common Operations

### Create Superuser

```bash
docker compose exec web python manage.py createsuperuser
```

### Shell Access

```bash
# Django shell
docker compose exec web python manage.py shell

# PostgreSQL shell (direct)
docker compose exec postgres psql -U myapp_user -d myapp_db

# PostgreSQL via PgBouncer
docker compose exec pgbouncer psql -h 127.0.0.1 -U myapp_user -d myapp_db
```

### View PgBouncer Stats

```bash
docker compose exec pgbouncer psql -h 127.0.0.1 -U myapp_user -d pgbouncer -c "SHOW POOLS"
```

## Troubleshooting

### "Cursor not found" errors
- Ensure `DISABLE_SERVER_SIDE_CURSORS=True` on pooled connection
- Wrap iterator operations in `transaction.atomic()` if needed

### Connection timeouts
- Check `QUERY_WAIT_TIMEOUT` in PgBouncer config
- Increase `DEFAULT_POOL_SIZE` if under heavy load

### Prepared statement errors
- Verify `MAX_PREPARED_STATEMENTS > 0` in PgBouncer
- Check `prepare_threshold` in SQLAlchemy engine config

### Migration failures
- Always use `--database=direct` for migrations
- Ensure PostgreSQL is accepting direct connections
