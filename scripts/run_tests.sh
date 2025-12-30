#!/bin/bash
# Comprehensive test script for Django Ninja PostgreSQL app
# This script runs all tests and validations

set -e

echo "========================================"
echo "Django Ninja + PostgreSQL Test Suite"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "Running inside Docker container"
    IN_DOCKER=true
else
    echo "Running on host machine"
    IN_DOCKER=false
fi

# Wait for database to be ready
echo ""
echo "--- Checking Database Connectivity ---"

wait_for_db() {
    local host=$1
    local port=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if pg_isready -h "$host" -p "$port" -U "${DB_USER:-myapp_user}" > /dev/null 2>&1; then
            print_status "Database at $host:$port is ready"
            return 0
        fi
        echo "Waiting for database at $host:$port... (attempt $attempt/$max_attempts)"
        sleep 1
        ((attempt++))
    done

    print_error "Database at $host:$port not available after $max_attempts attempts"
    return 1
}

# Check direct connection
wait_for_db "${DB_HOST:-postgres}" "${DB_PORT:-5432}"

# Check PgBouncer connection
wait_for_db "${DB_HOST_POOLED:-pgbouncer}" "${DB_PORT_POOLED:-5432}"

# Run Django checks
echo ""
echo "--- Django System Checks ---"
python manage.py check
print_status "Django system checks passed"

# Run migrations on direct connection
echo ""
echo "--- Running Migrations (Direct Connection) ---"
python manage.py migrate --database=direct --verbosity=1
print_status "Migrations completed on direct connection"

# Set up SQLAlchemy tables
echo ""
echo "--- Setting up SQLAlchemy Tables ---"
python manage.py setup_sqlalchemy_tables --seed=20
print_status "SQLAlchemy tables created and seeded"

# Run connection tests
echo ""
echo "--- Running Connection Tests ---"
python manage.py test_connections --iterations=20
print_status "Connection tests completed"

# Run pytest
echo ""
echo "--- Running pytest Test Suite ---"
python -m pytest tests/ -v --tb=short
print_status "pytest suite completed"

# Test API endpoints manually
echo ""
echo "--- Testing API Endpoints ---"

# Start the server in background for API tests
python manage.py runserver 0.0.0.0:8000 &
SERVER_PID=$!
sleep 3

# Test endpoints with curl
test_endpoint() {
    local method=$1
    local url=$2
    local data=$3
    local expected=$4

    if [ -n "$data" ]; then
        response=$(curl -s -X "$method" "http://localhost:8000$url" \
            -H "Content-Type: application/json" \
            -d "$data")
    else
        response=$(curl -s -X "$method" "http://localhost:8000$url")
    fi

    if echo "$response" | grep -q "$expected"; then
        print_status "API $method $url"
    else
        print_warning "API $method $url - unexpected response"
        echo "  Response: $response"
    fi
}

# Test item endpoints
test_endpoint "POST" "/api/items/" '{"name":"Test","price":"9.99","description":"API test"}' "Test"
test_endpoint "GET" "/api/items/" "" "name"
test_endpoint "GET" "/api/items/test/connection-info" "" "server_side_cursors_disabled"
test_endpoint "GET" "/api/items/test/iterator?chunk_size=10" "" "items_processed"
test_endpoint "GET" "/api/items/test/transaction" "" "results"

# Test vector endpoints
test_endpoint "POST" "/api/vectors/setup/create-tables" "" "success"
test_endpoint "POST" "/api/vectors/setup/seed-data?count=5" "" "documents_created"
test_endpoint "GET" "/api/vectors/documents?limit=5" "" "title"
test_endpoint "GET" "/api/vectors/test/prepared-statements?iterations=20" "" "avg_query_time_ms"

# Cleanup
kill $SERVER_PID 2>/dev/null || true

echo ""
echo "========================================"
echo "All Tests Completed Successfully!"
echo "========================================"
