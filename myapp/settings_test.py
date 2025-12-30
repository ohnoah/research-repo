"""
Test settings for running basic Django checks without PostgreSQL.

This is used for CI validation when PostgreSQL isn't available.
For full testing with pgvector, use the Docker setup.
"""

from myapp.settings import *  # noqa: F401, F403

# Override databases for testing without PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    },
    'direct': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    },
}

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()
