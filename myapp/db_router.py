"""
Database Router for Django with PgBouncer setup.

This router ensures:
1. Migrations always run on the 'direct' database connection
2. All other operations use the 'default' (pooled) connection
"""


class DirectMigrationRouter:
    """
    A router that directs migrations to the 'direct' database connection.

    This is important because:
    - Migrations can be long-running and would pin pool connections
    - Some migration operations may use session features (SET, temp tables)
    - PgBouncer query_wait_timeout can cause migration failures under load
    """

    def db_for_read(self, model, **hints):
        """Use default (pooled) for reads."""
        return 'default'

    def db_for_write(self, model, **hints):
        """Use default (pooled) for writes."""
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects from both databases."""
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Only allow migrations on the 'direct' database.

        This ensures migrations don't go through PgBouncer, avoiding:
        - Pool starvation during long migrations
        - Query wait timeout issues
        - Session feature incompatibilities
        """
        return db == 'direct'
