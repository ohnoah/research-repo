"""
URL configuration for myapp project.
"""

from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from sample.api import router as sample_router
from sample.api_sqlalchemy import router as sqlalchemy_router

# Create the Ninja API
api = NinjaAPI(
    title="Django Ninja PostgreSQL Demo",
    version="1.0.0",
    description="""
    A demo API showcasing Django Ninja with PostgreSQL, PgBouncer,
    SQLAlchemy, and pgvector integration.

    ## Features
    - Django ORM with dual database configuration
    - SQLAlchemy with pgvector for vector similarity search
    - Connection pooling via PgBouncer
    - Server-side cursor handling
    """
)

# Register routers
api.add_router("/items/", sample_router, tags=["Items"])
api.add_router("/vectors/", sqlalchemy_router, tags=["Vectors & SQLAlchemy"])

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
