"""
Tests for Django ORM operations with PgBouncer.

These tests verify:
- Basic CRUD operations work through pooled connection
- Iterator behavior with server-side cursors disabled
- Transaction handling
- Direct vs pooled connection behavior
"""

import pytest
from decimal import Decimal

from django.db import connection, transaction
from django.conf import settings


@pytest.mark.django_db
class TestBasicCRUD:
    """Test basic CRUD operations through the API."""

    def test_create_item(self, api_client):
        """Test creating an item through the API."""
        response = api_client.post(
            "/items/",
            json={
                "name": "New Item",
                "description": "A new test item",
                "price": "29.99",
                "quantity": 50,
                "tags": ["new", "test"],
                "metadata": {"created_via": "api"}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Item"
        assert data["price"] == "29.99"

    def test_list_items(self, api_client, sample_items):
        """Test listing items with pagination."""
        response = api_client.get("/items/?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    def test_get_item(self, api_client, sample_item):
        """Test getting a single item."""
        response = api_client.get(f"/items/{sample_item.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_item.name

    def test_update_item(self, api_client, sample_item):
        """Test updating an item."""
        response = api_client.put(
            f"/items/{sample_item.id}",
            json={"name": "Updated Name", "price": "39.99"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["price"] == "39.99"

    def test_delete_item(self, api_client, sample_item):
        """Test deleting an item."""
        response = api_client.delete(f"/items/{sample_item.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.django_db
class TestConnectionBehavior:
    """Test connection behavior with PgBouncer configuration."""

    def test_server_side_cursors_disabled_on_default(self):
        """Verify server-side cursors are disabled on the default connection."""
        db_settings = settings.DATABASES['default']
        assert db_settings.get('DISABLE_SERVER_SIDE_CURSORS') is True

    def test_server_side_cursors_enabled_on_direct(self):
        """Verify server-side cursors are enabled on the direct connection."""
        db_settings = settings.DATABASES['direct']
        assert db_settings.get('DISABLE_SERVER_SIDE_CURSORS') is False

    def test_connection_info_endpoint(self, api_client):
        """Test the connection info endpoint."""
        response = api_client.get("/items/test/connection-info")
        assert response.status_code == 200
        data = response.json()
        assert data["server_side_cursors_disabled"] is True


@pytest.mark.django_db
class TestIteratorBehavior:
    """Test QuerySet.iterator() behavior."""

    def test_iterator_on_pooled_connection(self, api_client, sample_items):
        """Test iterator works through pooled connection."""
        response = api_client.get("/items/test/iterator?chunk_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["items_processed"] >= 50
        assert data["server_side_cursors_disabled"] is True

    def test_iterator_on_direct_connection(self, api_client, sample_items):
        """Test iterator works on direct connection."""
        response = api_client.get("/items/test/iterator-direct?chunk_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["items_processed"] >= 50
        assert data["server_side_cursors_disabled"] is False


@pytest.mark.django_db
class TestTransactionBehavior:
    """Test transaction handling."""

    def test_transaction_endpoint(self, api_client, sample_items):
        """Test transaction behavior endpoint."""
        response = api_client.get("/items/test/transaction")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0

    def test_atomic_transaction_uses_same_connection(self, db):
        """Verify that atomic transactions use the same backend PID."""
        pids = []

        with transaction.atomic():
            for _ in range(5):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.append(cursor.fetchone()[0])

        # All PIDs should be the same within a transaction
        assert len(set(pids)) == 1


@pytest.mark.django_db
class TestBulkOperations:
    """Test bulk operations through PgBouncer."""

    def test_bulk_create(self, api_client):
        """Test bulk create operation."""
        response = api_client.post("/items/bulk-create?count=50")
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 50

    def test_bulk_delete(self, api_client):
        """Test bulk delete operation."""
        # First create some items
        api_client.post("/items/bulk-create?count=20")

        # Then delete them
        response = api_client.delete("/items/bulk-delete?name_prefix=Bulk%20Item")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] >= 20
