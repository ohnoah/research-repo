"""
Django models for the sample application.

Demonstrates:
- Standard Django ORM models
- pgvector ArrayField for embeddings
- Custom managers for different database connections
"""

from django.db import models
from django.contrib.postgres.fields import ArrayField


class ItemManager(models.Manager):
    """Manager that uses the pooled connection by default."""
    pass


class DirectItemManager(models.Manager):
    """Manager that uses the direct connection for admin operations."""

    def get_queryset(self):
        return super().get_queryset().using('direct')


class Item(models.Model):
    """
    A sample model representing an item with various field types.

    This model demonstrates Django ORM with PostgreSQL features.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=0)
    # New field to test migrations
    is_active = models.BooleanField(default=True, help_text="Whether item is active")
    tags = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="Tags for categorization"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata as JSON"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Managers
    objects = ItemManager()  # Uses pooled connection
    direct_objects = DirectItemManager()  # Uses direct connection

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.name} (${self.price})"


class ItemEmbedding(models.Model):
    """
    A model for storing vector embeddings using Django ORM.

    Note: For advanced pgvector operations (similarity search, etc.),
    we use SQLAlchemy directly. This model is for basic CRUD operations.
    """
    item = models.OneToOneField(
        Item,
        on_delete=models.CASCADE,
        related_name='embedding'
    )
    # Store embedding as array of floats
    # pgvector operations are handled via SQLAlchemy for better control
    vector = ArrayField(
        models.FloatField(),
        size=384,  # Common embedding dimension (e.g., all-MiniLM-L6-v2)
        help_text="384-dimensional embedding vector"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Embedding for {self.item.name}"


class AuditLog(models.Model):
    """
    Audit log for tracking database operations.

    Useful for testing connection behavior and transaction boundaries.
    """
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('READ', 'Read'),
    ]

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict)
    connection_type = models.CharField(
        max_length=20,
        help_text="Whether this was via pooled or direct connection"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.model_name} at {self.created_at}"
