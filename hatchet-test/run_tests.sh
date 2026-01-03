#!/bin/bash
# Hatchet-lite Performance Test Runner
# =====================================
# This script starts hatchet-lite and runs performance benchmarks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "Hatchet-lite Performance Test Runner"
echo "============================================"

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    docker compose -f docker-compose.hatchet.yml down -v 2>/dev/null || true
}
trap cleanup EXIT

# Step 1: Start hatchet-lite
echo ""
echo "[1/5] Starting Hatchet-lite..."
docker compose -f docker-compose.hatchet.yml up -d

# Step 2: Wait for hatchet-lite to be ready
echo ""
echo "[2/5] Waiting for Hatchet-lite to be healthy..."
MAX_WAIT=120
COUNTER=0
until docker compose -f docker-compose.hatchet.yml exec -T hatchet-lite wget -q --spider http://localhost:8888/api/ready 2>/dev/null; do
    COUNTER=$((COUNTER + 1))
    if [ $COUNTER -ge $MAX_WAIT ]; then
        echo "Timeout waiting for hatchet-lite to be ready"
        docker compose -f docker-compose.hatchet.yml logs hatchet-lite
        exit 1
    fi
    echo "  Waiting... ($COUNTER seconds)"
    sleep 1
done
echo "  Hatchet-lite is ready!"

# Step 3: Get API token
echo ""
echo "[3/5] Getting API token..."
export HATCHET_CLIENT_TOKEN=$(docker compose -f docker-compose.hatchet.yml exec -T hatchet-lite /hatchet-admin token create --config /config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52 2>/dev/null | xargs)
echo "  Token acquired: ${HATCHET_CLIENT_TOKEN:0:20}..."

# Step 4: Install Python dependencies
echo ""
echo "[4/5] Installing Python dependencies..."
pip install -q -r requirements.txt

# Step 5: Start worker in background and run benchmarks
echo ""
echo "[5/5] Running benchmarks..."

# Set environment variables for the client
export HATCHET_CLIENT_GRPC_HOST=localhost
export HATCHET_CLIENT_GRPC_PORT=7077
export HATCHET_CLIENT_TLS_STRATEGY=none

# Start worker in background
echo "  Starting worker..."
python worker.py &
WORKER_PID=$!
sleep 5  # Give worker time to register

# Run benchmarks
echo "  Running benchmarks..."
python benchmark.py

# Cleanup worker
kill $WORKER_PID 2>/dev/null || true

echo ""
echo "============================================"
echo "Tests complete!"
echo "============================================"
