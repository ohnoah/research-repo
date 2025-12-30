"""
Pytest configuration for Django Ninja PostgreSQL tests.
"""

import os
import sys

import django
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapp.settings')


def pytest_configure(config):
    """Configure Django before running tests."""
    django.setup()


@pytest.fixture(scope='session')
def django_db_setup():
    """Set up the test database."""
    from django.conf import settings
    settings.DATABASES['default']['ATOMIC_REQUESTS'] = False


@pytest.fixture
def api_client():
    """Create a test client for the Ninja API."""
    from ninja.testing import TestClient
    from myapp.urls import api
    return TestClient(api)


@pytest.fixture
def sample_item(db):
    """Create a sample item for testing."""
    from decimal import Decimal
    from sample.models import Item

    return Item.objects.create(
        name="Test Item",
        description="A test item for unit tests",
        price=Decimal("19.99"),
        quantity=100,
        tags=["test", "sample"],
        metadata={"test": True}
    )


@pytest.fixture
def sample_items(db):
    """Create multiple sample items for testing."""
    from decimal import Decimal
    from sample.models import Item

    items = []
    for i in range(50):
        item = Item.objects.create(
            name=f"Item {i}",
            description=f"Description for item {i}",
            price=Decimal("9.99") + i,
            quantity=i * 10,
            tags=["bulk", f"item-{i}"],
            metadata={"index": i}
        )
        items.append(item)
    return items
