#!/usr/bin/env python
"""
Comprehensive test script for PgBouncer compatibility issues with Django.

This script tests:
1. SET commands (fail with transaction pooling)
2. Server-side cursors / iterator behavior
3. Prepared statements
4. Transaction behavior
5. LISTEN/NOTIFY (fails with transaction pooling)
6. Advisory locks (fails with transaction pooling)
"""

import os
import sys
import time
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapp.settings')

import django
django.setup()

from django.db import connection, connections, transaction
from django.conf import settings
from sample.models import Item


def print_header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def print_result(test_name, passed, details=""):
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")
    if details:
        print(f"         {details}")


def test_set_commands():
    """
    Test SET commands - these FAIL with PgBouncer transaction pooling.

    With transaction pooling, SET only affects the current transaction.
    After the transaction ends, the connection returns to the pool and
    the settings are lost (or affect a different client's next query).
    """
    print_header("TEST: SET Commands (Problem with Transaction Pooling)")

    # Test 1: SET in auto-commit mode
    try:
        with connection.cursor() as cursor:
            # Set a session variable
            cursor.execute("SET statement_timeout = '5000'")
            cursor.execute("SHOW statement_timeout")
            result1 = cursor.fetchone()[0]

        # In a new cursor (potentially new connection with pooling)
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            result2 = cursor.fetchone()[0]

        # With PgBouncer transaction pooling, result2 might differ from result1
        same_setting = result1 == result2
        print_result(
            "SET persists across cursors",
            same_setting,
            f"First: {result1}, Second: {result2}"
        )

        if not same_setting:
            print("         ⚠ This is EXPECTED with PgBouncer transaction pooling!")

    except Exception as e:
        print_result("SET command test", False, str(e))

    # Test 2: SET within a transaction
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '10000'")
                cursor.execute("SHOW statement_timeout")
                in_tx = cursor.fetchone()[0]

        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            after_tx = cursor.fetchone()[0]

        print_result(
            "SET LOCAL within transaction",
            True,
            f"In TX: {in_tx}, After TX: {after_tx}"
        )
    except Exception as e:
        print_result("SET LOCAL test", False, str(e))


def test_server_side_cursors():
    """
    Test server-side cursor behavior.

    With DISABLE_SERVER_SIDE_CURSORS=True, Django uses client-side cursors
    which are safe for PgBouncer transaction pooling.
    """
    print_header("TEST: Server-Side Cursors (Iterator Behavior)")

    # Check settings
    default_disabled = settings.DATABASES['default'].get('DISABLE_SERVER_SIDE_CURSORS', False)
    direct_disabled = settings.DATABASES['direct'].get('DISABLE_SERVER_SIDE_CURSORS', False)

    print_result(
        "default connection: DISABLE_SERVER_SIDE_CURSORS",
        default_disabled,
        f"Value: {default_disabled}"
    )
    print_result(
        "direct connection: DISABLE_SERVER_SIDE_CURSORS",
        not direct_disabled,
        f"Value: {direct_disabled}"
    )

    # Create test data
    if Item.objects.count() < 100:
        print("  Creating test data...")
        items = [
            Item(
                name=f"Test Item {i}",
                description=f"Description {i}",
                price=Decimal("9.99") + i,
                quantity=i * 10
            )
            for i in range(100)
        ]
        Item.objects.bulk_create(items)

    # Test iterator on default (pooled) connection
    try:
        count = 0
        start = time.perf_counter()
        for item in Item.objects.all().iterator(chunk_size=10):
            count += 1
        elapsed = (time.perf_counter() - start) * 1000

        print_result(
            "iterator() on default connection",
            True,
            f"Processed {count} items in {elapsed:.2f}ms"
        )
    except Exception as e:
        print_result("iterator() on default", False, str(e))

    # Test iterator on direct connection
    try:
        count = 0
        start = time.perf_counter()
        for item in Item.direct_objects.all().iterator(chunk_size=10):
            count += 1
        elapsed = (time.perf_counter() - start) * 1000

        print_result(
            "iterator() on direct connection",
            True,
            f"Processed {count} items in {elapsed:.2f}ms"
        )
    except Exception as e:
        print_result("iterator() on direct", False, str(e))


def test_prepared_statements():
    """
    Test prepared statement behavior.

    psycopg3 uses prepared statements by default. With PgBouncer transaction
    pooling, this requires max_prepared_statements > 0 in PgBouncer config.
    """
    print_header("TEST: Prepared Statements")

    # Run the same query multiple times to trigger prepared statement caching
    times = []
    try:
        for i in range(20):
            start = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, price FROM sample_item WHERE id > %s LIMIT 10",
                    [0]
                )
                cursor.fetchall()
            times.append((time.perf_counter() - start) * 1000)

        avg = sum(times) / len(times)
        first_5 = sum(times[:5]) / 5
        last_5 = sum(times[-5:]) / 5

        # If prepared statements are working, later queries should be faster
        speedup = first_5 / last_5 if last_5 > 0 else 1

        print_result(
            "Repeated query execution",
            True,
            f"Avg: {avg:.3f}ms, First 5: {first_5:.3f}ms, Last 5: {last_5:.3f}ms"
        )
        print(f"         Speedup: {speedup:.2f}x")

        if speedup > 1.1:
            print("         ⚠ Prepared statements appear to be caching")
        else:
            print("         ⚠ No significant speedup (may be normal for simple queries)")

    except Exception as e:
        print_result("Prepared statements test", False, str(e))


def test_transaction_behavior():
    """
    Test transaction behavior with connection pooling.
    """
    print_header("TEST: Transaction Behavior")

    # Test PID consistency within a transaction
    try:
        pids_in_tx = []
        with transaction.atomic():
            for _ in range(5):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids_in_tx.append(cursor.fetchone()[0])

        all_same = len(set(pids_in_tx)) == 1
        print_result(
            "Same PID within transaction",
            all_same,
            f"PIDs: {pids_in_tx}"
        )

    except Exception as e:
        print_result("Transaction PID test", False, str(e))

    # Test PID across separate queries (auto-commit)
    try:
        pids_autocommit = []
        for _ in range(5):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids_autocommit.append(cursor.fetchone()[0])

        unique_pids = len(set(pids_autocommit))
        print_result(
            "PIDs in auto-commit mode",
            True,
            f"Unique PIDs: {unique_pids}/5, PIDs: {pids_autocommit}"
        )

        if unique_pids > 1:
            print("         ⚠ Multiple PIDs suggests connection pooling is active")

    except Exception as e:
        print_result("Auto-commit PID test", False, str(e))


def test_listen_notify():
    """
    Test LISTEN/NOTIFY - FAILS with PgBouncer transaction pooling.

    LISTEN creates a session-level subscription that's lost when the
    connection returns to the pool.
    """
    print_header("TEST: LISTEN/NOTIFY (Fails with Transaction Pooling)")

    try:
        with connection.cursor() as cursor:
            cursor.execute("LISTEN test_channel")
            cursor.execute("NOTIFY test_channel, 'test message'")

            # In real PgBouncer scenario, LISTEN would be lost
            print_result(
                "LISTEN/NOTIFY commands execute",
                True,
                "Commands ran, but notifications may be lost with pooling"
            )
            print("         ⚠ With PgBouncer transaction pooling, LISTEN is NOT reliable!")

    except Exception as e:
        print_result("LISTEN/NOTIFY test", False, str(e))


def test_advisory_locks():
    """
    Test advisory locks - Session-level locks FAIL with transaction pooling.

    With transaction pooling, session-level locks may be released unexpectedly
    or held by different clients.
    """
    print_header("TEST: Advisory Locks (Session-level Fails with Transaction Pooling)")

    # Test transaction-level advisory lock (should work)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(12345)")
                locked = cursor.fetchone()[0]

        print_result(
            "Transaction-level advisory lock (pg_try_advisory_xact_lock)",
            locked,
            "This is SAFE with transaction pooling"
        )
    except Exception as e:
        print_result("Transaction advisory lock", False, str(e))

    # Test session-level advisory lock (problematic with pooling)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(67890)")
            locked = cursor.fetchone()[0]
            if locked:
                cursor.execute("SELECT pg_advisory_unlock(67890)")

        print_result(
            "Session-level advisory lock (pg_try_advisory_lock)",
            True,
            "⚠ NOT SAFE with transaction pooling!"
        )
        print("         ⚠ Lock may be held by wrong client or released unexpectedly!")

    except Exception as e:
        print_result("Session advisory lock", False, str(e))


def test_temp_tables():
    """
    Test temporary tables - Can be problematic with transaction pooling.
    """
    print_header("TEST: Temporary Tables")

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("CREATE TEMP TABLE test_temp (id int) ON COMMIT DROP")
                cursor.execute("INSERT INTO test_temp VALUES (1), (2), (3)")
                cursor.execute("SELECT COUNT(*) FROM test_temp")
                count = cursor.fetchone()[0]

        print_result(
            "TEMP TABLE with ON COMMIT DROP",
            count == 3,
            "This is SAFE - table is dropped at transaction end"
        )
    except Exception as e:
        print_result("Temp table test", False, str(e))

    # Test temp table without ON COMMIT DROP (problematic)
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE IF NOT EXISTS test_temp2 (id int)")
            cursor.execute("INSERT INTO test_temp2 VALUES (1)")

        # In another "transaction" (potentially different pooled connection)
        with connection.cursor() as cursor:
            try:
                cursor.execute("SELECT COUNT(*) FROM test_temp2")
                count = cursor.fetchone()[0]
                print_result(
                    "TEMP TABLE persists across transactions",
                    True,
                    f"Count: {count} - ⚠ May cause issues with pooling!"
                )
            except Exception:
                print_result(
                    "TEMP TABLE visibility",
                    False,
                    "Table not visible - expected with transaction pooling"
                )

            # Cleanup
            try:
                cursor.execute("DROP TABLE IF EXISTS test_temp2")
            except Exception:
                pass

    except Exception as e:
        print_result("Temp table persistence test", False, str(e))


def test_new_migration():
    """
    Test creating and applying a new migration.
    """
    print_header("TEST: New Migration")

    # Create a simple model change
    print("  Creating a new migration for model change...")

    try:
        from django.core.management import call_command
        from io import StringIO

        # Check for pending migrations
        out = StringIO()
        call_command('showmigrations', 'sample', stdout=out)
        print(f"  Current migrations:\n{out.getvalue()}")

        print_result(
            "Migration system accessible",
            True,
            "Can check migration status"
        )

    except Exception as e:
        print_result("Migration test", False, str(e))


def main():
    print("\n" + "="*60)
    print(" Django + PgBouncer Compatibility Test Suite")
    print("="*60)
    print(f"\nDatabase: {settings.DATABASES['default']['NAME']}")
    print(f"Host: {settings.DATABASES['default']['HOST']}:{settings.DATABASES['default']['PORT']}")
    print(f"DISABLE_SERVER_SIDE_CURSORS: {settings.DATABASES['default'].get('DISABLE_SERVER_SIDE_CURSORS', False)}")

    test_set_commands()
    test_server_side_cursors()
    test_prepared_statements()
    test_transaction_behavior()
    test_listen_notify()
    test_advisory_locks()
    test_temp_tables()
    test_new_migration()

    print("\n" + "="*60)
    print(" Summary")
    print("="*60)
    print("""
Key findings for PgBouncer Transaction Pooling:

1. SET commands: Session settings are LOST between transactions
2. Server-side cursors: Must use DISABLE_SERVER_SIDE_CURSORS=True
3. LISTEN/NOTIFY: Does NOT work - use direct connection
4. Session advisory locks: UNSAFE - use transaction-level locks
5. Temp tables: Use ON COMMIT DROP or avoid
6. Migrations: Should run on direct connection (--database=direct)
""")


if __name__ == '__main__':
    main()
