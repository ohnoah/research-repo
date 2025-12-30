"""
Django settings for myapp project.

Demonstrates dual database configuration for PgBouncer pooling:
- 'default': Uses PgBouncer (transaction pooling) for web requests
- 'direct': Direct PostgreSQL connection for migrations and admin tasks
"""

import os
from pathlib import Path

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Security settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Our apps
    'sample',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'myapp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'myapp.wsgi.application'

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
# Two database aliases pointing to the same DB, different connection paths:
#
# 1. 'default' (pooled via PgBouncer):
#    - Used for web request traffic
#    - Transaction pooling mode
#    - DISABLE_SERVER_SIDE_CURSORS=True (critical for transaction pooling!)
#
# 2. 'direct' (no PgBouncer):
#    - Used for migrations, management commands
#    - Supports all PostgreSQL features (LISTEN, advisory locks, etc.)
#    - Server-side cursors enabled for streaming large datasets
# =============================================================================

DB_NAME = os.environ.get('DB_NAME', 'myapp_db')
DB_USER = os.environ.get('DB_USER', 'myapp_user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'myapp_password')
DB_HOST_DIRECT = os.environ.get('DB_HOST', 'localhost')
DB_HOST_POOLED = os.environ.get('DB_HOST_POOLED', 'localhost')
DB_PORT_DIRECT = os.environ.get('DB_PORT', '5432')
# For local testing without PgBouncer, defaults to direct port
DB_PORT_POOLED = os.environ.get('DB_PORT_POOLED', '5432')

DATABASES = {
    # Pooled connection via PgBouncer - for web traffic
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST_POOLED,
        'PORT': DB_PORT_POOLED,
        # CRITICAL: Disable server-side cursors for transaction pooling!
        # Without this, QuerySet.iterator() will break under PgBouncer
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            # Connection options for psycopg3
            'options': '-c statement_timeout=30000',  # 30s timeout
        },
        # Connection health check (Django 4.1+)
        'CONN_HEALTH_CHECKS': True,
        # Persistent connections (reduce connection overhead)
        'CONN_MAX_AGE': 60,
    },

    # Direct connection to PostgreSQL - for migrations and admin
    'direct': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST_DIRECT,
        'PORT': DB_PORT_DIRECT,
        # Server-side cursors enabled (default) for streaming
        'DISABLE_SERVER_SIDE_CURSORS': False,
        'OPTIONS': {
            'options': '-c statement_timeout=300000',  # 5min for migrations
        },
        'CONN_HEALTH_CHECKS': True,
    },
}

# Database router to use direct connection for migrations
DATABASE_ROUTERS = ['myapp.db_router.DirectMigrationRouter']

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
# Useful for debugging database queries and connection behavior
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
