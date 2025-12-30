"""
Management command to test database connections.

Tests both pooled (PgBouncer) and direct PostgreSQL connections.
"""

import time
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import connections, connection
from django.db import transaction

from sample.models import Item


class Command(BaseCommand):
    help = 'Test database connections (pooled and direct)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--iterations',
            type=int,
            default=10,
            help='Number of iterations for each test'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show verbose output'
        )

    def handle(self, *args, **options):
        iterations = options['iterations']
        verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Database Connection Tests'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Test 1: Basic connectivity
        self.test_basic_connectivity()

        # Test 2: Server-side cursor behavior
        self.test_server_side_cursors(verbose)

        # Test 3: Transaction behavior
        self.test_transaction_behavior(iterations, verbose)

        # Test 4: Iterator behavior
        self.test_iterator_behavior(verbose)

        # Test 5: Prepared statements (indirect test via query timing)
        self.test_prepared_statements(iterations, verbose)

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('All tests completed!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

    def test_basic_connectivity(self):
        """Test basic connectivity to both database aliases."""
        self.stdout.write('\n--- Test 1: Basic Connectivity ---')

        for alias in ['default', 'direct']:
            try:
                conn = connections[alias]
                with conn.cursor() as cursor:
                    cursor.execute("SELECT version()")
                    version = cursor.fetchone()[0]
                    cursor.execute("SELECT current_database(), current_user")
                    db, user = cursor.fetchone()

                self.stdout.write(
                    self.style.SUCCESS(f'  [{alias}] Connected: {db} as {user}')
                )
                self.stdout.write(f'    PostgreSQL: {version[:60]}...')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  [{alias}] Connection failed: {e}')
                )

    def test_server_side_cursors(self, verbose):
        """Test server-side cursor configuration."""
        self.stdout.write('\n--- Test 2: Server-Side Cursors ---')

        from django.conf import settings

        for alias in ['default', 'direct']:
            db_settings = settings.DATABASES[alias]
            disabled = db_settings.get('DISABLE_SERVER_SIDE_CURSORS', False)

            status = 'DISABLED' if disabled else 'ENABLED'
            style = self.style.WARNING if disabled else self.style.SUCCESS

            self.stdout.write(style(f'  [{alias}] Server-side cursors: {status}'))

            if disabled:
                self.stdout.write(
                    '    -> Safe for PgBouncer transaction pooling'
                )
            else:
                self.stdout.write(
                    '    -> Uses server-side cursors for iterator()'
                )

    def test_transaction_behavior(self, iterations, verbose):
        """Test transaction behavior with connection reuse."""
        self.stdout.write('\n--- Test 3: Transaction Behavior ---')

        # Test auto-commit queries
        pids_autocommit = []
        for _ in range(iterations):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids_autocommit.append(cursor.fetchone()[0])

        unique_autocommit = len(set(pids_autocommit))
        self.stdout.write(
            f'  Auto-commit queries: {unique_autocommit} unique PIDs '
            f'across {iterations} queries'
        )

        if verbose:
            self.stdout.write(f'    PIDs: {pids_autocommit}')

        # Test within transaction
        pids_transaction = []
        with transaction.atomic():
            for _ in range(iterations):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids_transaction.append(cursor.fetchone()[0])

        unique_transaction = len(set(pids_transaction))
        self.stdout.write(
            f'  Within transaction: {unique_transaction} unique PIDs '
            f'across {iterations} queries'
        )

        if unique_transaction == 1:
            self.stdout.write(
                self.style.SUCCESS('    -> All queries used same backend (correct)')
            )

    def test_iterator_behavior(self, verbose):
        """Test iterator() behavior on pooled vs direct connections."""
        self.stdout.write('\n--- Test 4: Iterator Behavior ---')

        # Ensure we have test data
        if Item.objects.count() < 50:
            self.stdout.write('  Creating test data...')
            for i in range(50):
                Item.objects.create(
                    name=f"Test Item {i}",
                    description=f"Description {i}",
                    price=Decimal("9.99") + i,
                    quantity=i * 10
                )

        # Test pooled iterator
        start = time.perf_counter()
        count_pooled = 0
        for item in Item.objects.all().iterator(chunk_size=10):
            count_pooled += 1
        pooled_time = (time.perf_counter() - start) * 1000

        self.stdout.write(
            f'  [default] Iterator: {count_pooled} items in {pooled_time:.2f}ms'
        )
        self.stdout.write('    -> Uses client-side batching (DISABLE_SERVER_SIDE_CURSORS=True)')

        # Test direct iterator
        start = time.perf_counter()
        count_direct = 0
        for item in Item.direct_objects.all().iterator(chunk_size=10):
            count_direct += 1
        direct_time = (time.perf_counter() - start) * 1000

        self.stdout.write(
            f'  [direct] Iterator: {count_direct} items in {direct_time:.2f}ms'
        )
        self.stdout.write('    -> Uses server-side cursors for streaming')

    def test_prepared_statements(self, iterations, verbose):
        """Test prepared statement behavior (timing-based)."""
        self.stdout.write('\n--- Test 5: Prepared Statements ---')

        # Run the same query multiple times and measure timing
        times = []
        for i in range(iterations):
            start = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, price FROM sample_item WHERE id > %s LIMIT 10",
                    [0]
                )
                cursor.fetchall()
            times.append((time.perf_counter() - start) * 1000)

        avg_time = sum(times) / len(times)
        first_5 = sum(times[:5]) / 5 if len(times) >= 5 else avg_time
        last_5 = sum(times[-5:]) / 5 if len(times) >= 5 else avg_time

        self.stdout.write(
            f'  {iterations} queries: avg {avg_time:.3f}ms'
        )
        self.stdout.write(
            f'  First 5 avg: {first_5:.3f}ms, Last 5 avg: {last_5:.3f}ms'
        )

        if first_5 > last_5 * 1.05:
            speedup = first_5 / last_5
            self.stdout.write(
                self.style.SUCCESS(
                    f'    -> ~{speedup:.1f}x speedup suggests prepared statements working'
                )
            )
        else:
            self.stdout.write(
                '    -> No significant speedup (queries may be too simple)'
            )

        if verbose:
            self.stdout.write(f'    All times: {[f"{t:.3f}" for t in times]}')
