"""
Local development settings for running without Docker.

Uses SQLite for basic testing when PostgreSQL is not available.
"""

from myapp.settings import *  # noqa: F401, F403

# Override databases for local development without PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'DISABLE_SERVER_SIDE_CURSORS': True,
    },
    'direct': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'DISABLE_SERVER_SIDE_CURSORS': False,
    },
}
