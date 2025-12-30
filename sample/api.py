"""
Django Ninja API endpoints for the sample application.

Demonstrates:
- Basic CRUD operations through PgBouncer
- Server-side cursor behavior with iterator()
- Direct connection usage for specific operations
"""

from typing import Optional
from decimal import Decimal
from datetime import datetime

from django.db import connection, transaction
from ninja import Router, Schema
from pydantic import Field

from .models import Item, AuditLog

router = Router()


# =============================================================================
# Schemas
# =============================================================================

class ItemCreate(Schema):
    name: str
    description: str = ""
    price: Decimal
    quantity: int = 0
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ItemUpdate(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    quantity: Optional[int] = None
    tags: Optional[list[str]] = None
    metadata: Optional[dict] = None


class ItemOut(Schema):
    id: int
    name: str
    description: str
    price: Decimal
    quantity: int
    tags: list[str]
    metadata: dict
    created_at: datetime
    updated_at: datetime


class IteratorTestResult(Schema):
    items_processed: int
    chunk_size: int
    connection_type: str
    server_side_cursors_disabled: bool
    notes: str


class ConnectionInfo(Schema):
    database_alias: str
    host: str
    port: str
    server_side_cursors_disabled: bool
    using_pgbouncer: bool


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.post("/", response=ItemOut)
def create_item(request, payload: ItemCreate):
    """Create a new item (uses pooled connection)."""
    item = Item.objects.create(**payload.dict())

    # Log the operation
    AuditLog.objects.create(
        action='CREATE',
        model_name='Item',
        object_id=item.id,
        details={'name': item.name},
        connection_type='pooled'
    )

    return item


@router.get("/", response=list[ItemOut])
def list_items(request, limit: int = 100, offset: int = 0):
    """List items with pagination (uses pooled connection)."""
    items = Item.objects.all()[offset:offset + limit]
    return list(items)


@router.get("/{item_id}", response=ItemOut)
def get_item(request, item_id: int):
    """Get a single item by ID."""
    return Item.objects.get(id=item_id)


@router.put("/{item_id}", response=ItemOut)
def update_item(request, item_id: int, payload: ItemUpdate):
    """Update an existing item."""
    item = Item.objects.get(id=item_id)

    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(item, attr, value)
    item.save()

    AuditLog.objects.create(
        action='UPDATE',
        model_name='Item',
        object_id=item.id,
        details=payload.dict(exclude_unset=True),
        connection_type='pooled'
    )

    return item


@router.delete("/{item_id}")
def delete_item(request, item_id: int):
    """Delete an item."""
    item = Item.objects.get(id=item_id)
    item_id = item.id
    item.delete()

    AuditLog.objects.create(
        action='DELETE',
        model_name='Item',
        object_id=item_id,
        details={},
        connection_type='pooled'
    )

    return {"success": True, "deleted_id": item_id}


# =============================================================================
# Connection Testing Endpoints
# =============================================================================

@router.get("/test/connection-info", response=ConnectionInfo)
def get_connection_info(request):
    """
    Get information about the current database connection.

    This helps verify PgBouncer configuration is working correctly.
    """
    from django.conf import settings

    db_settings = settings.DATABASES['default']

    return {
        'database_alias': 'default',
        'host': db_settings['HOST'],
        'port': db_settings['PORT'],
        'server_side_cursors_disabled': db_settings.get('DISABLE_SERVER_SIDE_CURSORS', False),
        'using_pgbouncer': 'pgbouncer' in db_settings['HOST'].lower() or db_settings['PORT'] == '6432',
    }


@router.get("/test/iterator", response=IteratorTestResult)
def test_iterator_behavior(request, chunk_size: int = 100):
    """
    Test QuerySet.iterator() behavior with PgBouncer.

    This endpoint demonstrates how iterator() works differently
    with DISABLE_SERVER_SIDE_CURSORS=True (required for PgBouncer).

    When server-side cursors are disabled:
    - Django still streams results using chunk_size
    - But it's done at the driver layer, not with a database cursor
    - This is safe for transaction pooling
    """
    from django.conf import settings

    db_settings = settings.DATABASES['default']
    disabled = db_settings.get('DISABLE_SERVER_SIDE_CURSORS', False)

    # Create some test data if needed
    if Item.objects.count() < 10:
        for i in range(50):
            Item.objects.create(
                name=f"Test Item {i}",
                description=f"Test description {i}",
                price=Decimal("9.99") + i,
                quantity=i * 10
            )

    # Use iterator with specified chunk_size
    count = 0
    for item in Item.objects.all().iterator(chunk_size=chunk_size):
        count += 1

    notes = (
        "Server-side cursors DISABLED - safe for PgBouncer transaction pooling. "
        "Streaming is done at driver layer."
        if disabled else
        "Server-side cursors ENABLED - NOT safe for PgBouncer transaction pooling! "
        "May cause cursor errors if connection is reused."
    )

    return {
        'items_processed': count,
        'chunk_size': chunk_size,
        'connection_type': 'pooled',
        'server_side_cursors_disabled': disabled,
        'notes': notes,
    }


@router.get("/test/iterator-direct", response=IteratorTestResult)
def test_iterator_direct(request, chunk_size: int = 100):
    """
    Test iterator() on the direct connection (with server-side cursors).

    This uses the 'direct' database alias which bypasses PgBouncer.
    Server-side cursors are enabled, allowing efficient streaming of large datasets.
    """
    from django.conf import settings

    db_settings = settings.DATABASES['direct']
    disabled = db_settings.get('DISABLE_SERVER_SIDE_CURSORS', False)

    # Use direct connection with server-side cursors
    count = 0
    for item in Item.direct_objects.all().iterator(chunk_size=chunk_size):
        count += 1

    return {
        'items_processed': count,
        'chunk_size': chunk_size,
        'connection_type': 'direct',
        'server_side_cursors_disabled': disabled,
        'notes': "Direct connection with server-side cursors enabled - efficient streaming.",
    }


@router.get("/test/transaction")
def test_transaction_behavior(request):
    """
    Test transaction behavior with PgBouncer.

    In transaction pooling mode, the connection is released after each transaction.
    This test verifies that our Django configuration handles this correctly.
    """
    results = []

    # Test 1: Auto-commit mode (default)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        pid1 = cursor.fetchone()[0]
        results.append(f"First query PID: {pid1}")

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        pid2 = cursor.fetchone()[0]
        results.append(f"Second query PID: {pid2}")

    same_connection = pid1 == pid2
    results.append(f"Same backend PID: {same_connection}")

    # Test 2: Explicit transaction
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            pid3 = cursor.fetchone()[0]
            results.append(f"In transaction PID: {pid3}")

            # Multiple queries in same transaction should use same PID
            cursor.execute("SELECT pg_backend_pid()")
            pid4 = cursor.fetchone()[0]
            results.append(f"Still in transaction PID: {pid4}")
            results.append(f"Same PID in transaction: {pid3 == pid4}")

    return {
        'results': results,
        'notes': (
            "With PgBouncer transaction pooling, PIDs may differ between "
            "auto-commit queries but should be same within a transaction."
        )
    }


# =============================================================================
# Bulk Operations (for testing connection pool behavior)
# =============================================================================

@router.post("/bulk-create")
def bulk_create_items(request, count: int = 100):
    """
    Create multiple items in a single transaction.

    Tests bulk operations through PgBouncer.
    """
    items = [
        Item(
            name=f"Bulk Item {i}",
            description=f"Created in bulk operation",
            price=Decimal("10.00") + Decimal(str(i * 0.01)),
            quantity=i
        )
        for i in range(count)
    ]

    with transaction.atomic():
        created = Item.objects.bulk_create(items)

    return {
        'created_count': len(created),
        'connection_type': 'pooled',
    }


@router.delete("/bulk-delete")
def bulk_delete_items(request, name_prefix: str = "Bulk Item"):
    """Delete items matching a name prefix."""
    with transaction.atomic():
        count, _ = Item.objects.filter(name__startswith=name_prefix).delete()

    return {
        'deleted_count': count,
        'connection_type': 'pooled',
    }
