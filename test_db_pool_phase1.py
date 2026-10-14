#!/usr/bin/env python3
"""
Phase 1 tests: PostgreSQL connection reuse and the anonymous auth fast-path.

Covers: connection reuse across requests, concurrent acquisition, release on
success and on exception, rollback of open/aborted transactions, broken
connection disposal, pool exhaustion + timeout, anonymous requests without
credentials, and authenticated requests with valid/invalid tokens.

No real database is used; raw connections are injected as fakes.
"""

import os
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import server

REMOTE_DSN = "postgresql://user:pass@ep-phase1-test.neon.tech/neondb"


# --------------------------------------------------------------------------- fakes
class FakeInfo(object):
    def __init__(self, status=0):
        self.transaction_status = status


class FakeCursor(object):
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class FakeRawConn(object):
    """Minimal raw DB-API connection stand-in."""

    def __init__(self, status=0):
        self.closed = 0
        self.info = FakeInfo(status)
        self.rolled_back = 0
        self.committed = 0
        self.close_calls = 0
        self.rollback_raises = False

    def rollback(self):
        self.rolled_back += 1
        if self.rollback_raises:
            raise RuntimeError("simulated broken connection")

    def commit(self):
        self.committed += 1

    def close(self):
        self.close_calls += 1
        self.closed = 1

    def cursor(self, *a, **k):
        return FakeCursor()


def make_pool(max_size=2, timeout=1.0, min_size=0):
    created = []

    def create():
        conn = FakeRawConn()
        created.append(conn)
        return conn

    pool = server.PostgresConnectionPool(
        create_fn=create, max_size=max_size, min_size=min_size, acquire_timeout=timeout
    )
    return pool, created


# --------------------------------------------------------------------------- pool
class PoolCoreTests(unittest.TestCase):

    def test_reuses_a_single_connection(self):
        pool, created = make_pool(max_size=2)
        c1 = pool.acquire()
        self.assertEqual(pool.idle_count, 0)
        pool.release(c1)
        self.assertEqual(pool.idle_count, 1)
        c2 = pool.acquire()
        self.assertIs(c1, c2)
        self.assertEqual(len(created), 1)
        self.assertEqual(pool.size, 1)
        self.assertEqual(pool.idle_count, 0)
        pool.release(c2)

    def test_creates_up_to_max_then_exhausts(self):
        pool, created = make_pool(max_size=2, timeout=0.2)
        a = pool.acquire()
        b = pool.acquire()
        self.assertEqual(len(created), 2)
        started = time.monotonic()
        with self.assertRaises(server.PostgresPoolExhaustedError):
            pool.acquire()
        self.assertGreaterEqual(time.monotonic() - started, 0.15)
        pool.release(a)
        c = pool.acquire()
        self.assertIs(c, a)
        pool.release(b)
        pool.release(c)

    def test_release_rolls_back_open_transaction(self):
        pool, _ = make_pool()
        conn = FakeRawConn(status=2)  # INTRANS
        pool.release(conn)
        self.assertEqual(conn.rolled_back, 1)
        self.assertEqual(conn.close_calls, 0)
        self.assertEqual(pool.idle_count, 1)

    def test_release_rolls_back_errored_transaction(self):
        pool, _ = make_pool()
        conn = FakeRawConn(status=3)  # INERROR
        pool.release(conn)
        self.assertEqual(conn.rolled_back, 1)
        self.assertEqual(pool.idle_count, 1)

    def test_idle_connection_is_not_rolled_back_again(self):
        pool, _ = make_pool()
        conn = FakeRawConn(status=0)  # IDLE
        pool.release(conn)
        self.assertEqual(conn.rolled_back, 0)
        self.assertEqual(pool.idle_count, 1)

    def test_failed_rollback_discards_connection(self):
        pool, created = make_pool(max_size=2)
        conn = FakeRawConn(status=2)
        conn.rollback_raises = True
        pool.release(conn)
        self.assertEqual(conn.close_calls, 1)
        self.assertEqual(pool.idle_count, 0)
        self.assertEqual(pool.size, 0)

    def test_unknown_transaction_status_is_treated_as_broken(self):
        self.assertFalse(server._raw_connection_is_usable(FakeRawConn(status=4)))

    def test_closed_connection_is_discarded(self):
        pool, created = make_pool(max_size=2)
        conn = pool.acquire()          # created[0]
        conn.closed = 1                # simulate a dead connection
        pool.release(conn)
        self.assertEqual(conn.close_calls, 1)
        self.assertEqual(pool.idle_count, 0)
        self.assertEqual(pool.size, 0)
        nxt = pool.acquire()           # must create a fresh one, not reuse the dead one
        self.assertIsNot(nxt, conn)
        self.assertEqual(len(created), 2)
        pool.release(nxt)

    def test_create_failure_does_not_leak_a_slot(self):
        calls = {"n": 0}

        def create():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("db down")
            return FakeRawConn()

        pool = server.PostgresConnectionPool(create_fn=create, max_size=1, acquire_timeout=0.5)
        with self.assertRaises(RuntimeError):
            pool.acquire()
        self.assertEqual(pool.size, 0)
        conn = pool.acquire()  # slot was released, so this succeeds
        self.assertIsInstance(conn, FakeRawConn)
        pool.release(conn)

    def test_close_all_discards_idle_connections(self):
        pool, _ = make_pool()
        conn = pool.acquire()
        pool.release(conn)
        pool.close_all()
        self.assertEqual(conn.close_calls, 1)
        with self.assertRaises(server.PostgresPoolExhaustedError):
            pool.acquire()

    def test_concurrent_acquire_release_is_bounded_and_leak_free(self):
        pool, created = make_pool(max_size=3, timeout=10.0)
        in_use = {"now": 0, "max": 0}
        guard = threading.Lock()
        errors = []

        def worker():
            try:
                for _ in range(25):
                    conn = pool.acquire()
                    with guard:
                        in_use["now"] += 1
                        in_use["max"] = max(in_use["max"], in_use["now"])
                    time.sleep(0.001)
                    with guard:
                        in_use["now"] -= 1
                    pool.release(conn)
            except Exception as exc:  # pragma: no cover - surfaced via assertion
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertLessEqual(in_use["max"], 3)
        self.assertLessEqual(len(created), 3)
        self.assertEqual(pool.idle_count, pool.size)


# --------------------------------------------------------------------------- wrapper
class PooledWrapperTests(unittest.TestCase):

    def test_close_returns_connection_to_pool(self):
        pool, _ = make_pool()
        raw = pool.acquire()           # connection the pool created
        wrapper = server.PooledPostgresConnectionWrapper(raw, pool)
        wrapper.close()
        self.assertEqual(pool.idle_count, 1)
        self.assertEqual(raw.close_calls, 0)

    def test_close_is_idempotent(self):
        pool, _ = make_pool()
        raw = pool.acquire()
        wrapper = server.PooledPostgresConnectionWrapper(raw, pool)
        wrapper.close()
        wrapper.close()
        self.assertEqual(pool.size, 1)
        self.assertEqual(pool.idle_count, 1)

    def test_wrapper_satisfies_postgres_isinstance_checks(self):
        pool, _ = make_pool()
        wrapper = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
        self.assertIsInstance(wrapper, server.PostgresConnectionWrapper)

    def test_commit_and_rollback_delegate_to_raw_connection(self):
        pool, _ = make_pool()
        raw = pool.acquire()
        wrapper = server.PooledPostgresConnectionWrapper(raw, pool)
        wrapper.commit()
        wrapper.rollback()
        self.assertEqual(raw.committed, 1)
        self.assertEqual(raw.rolled_back, 1)


# --------------------------------------------------------------------------- get_db
class GetDbPoolingTests(unittest.TestCase):

    def setUp(self):
        self._pool, self._dsn = server._PG_POOL, server._PG_POOL_DSN
        server._PG_POOL = None
        server._PG_POOL_DSN = None

    def tearDown(self):
        server._PG_POOL, server._PG_POOL_DSN = self._pool, self._dsn

    def test_reuses_one_connection_across_requests(self):
        created = []

        def fake_create(dsn):
            conn = FakeRawConn(status=0)
            created.append(conn)
            return conn

        with patch.object(server, "DATABASE_URL", REMOTE_DSN), \
             patch.object(server, "is_production_env", return_value=False), \
             patch.object(server, "_create_raw_postgres_connection", side_effect=fake_create):
            first = server.get_db()
            self.assertIsInstance(first, server.PooledPostgresConnectionWrapper)
            self.assertIsInstance(first, server.PostgresConnectionWrapper)
            first.close()
            second = server.get_db()
            self.assertIs(first.raw_conn, second.raw_conn)
            second.close()

        self.assertEqual(len(created), 1, "must reuse the pooled connection")

    def test_development_driver_failure_falls_back_to_sqlite(self):
        import sqlite3
        with patch.object(server, "DATABASE_URL", REMOTE_DSN), \
             patch.object(server, "is_production_env", return_value=False), \
             patch.object(server, "_create_raw_postgres_connection",
                          side_effect=RuntimeError("refused")):
            conn = server.get_db()
            self.assertIsInstance(conn, sqlite3.Connection)
            conn.close()

    def test_production_driver_failure_raises_runtime_error(self):
        with patch.object(server, "DATABASE_URL", REMOTE_DSN), \
             patch.object(server, "is_production_env", return_value=True), \
             patch.object(server, "_create_raw_postgres_connection",
                          side_effect=RuntimeError("refused")):
            with self.assertRaises(RuntimeError) as ctx:
                server.get_db()
            self.assertIn("CRITICAL: Failed to connect to production PostgreSQL database", str(ctx.exception))

    def test_missing_database_url_returns_unpooled_sqlite(self):
        import sqlite3
        with patch.object(server, "DATABASE_URL", ""):
            conn = server.get_db()
            self.assertIsInstance(conn, sqlite3.Connection)
            self.assertNotIsInstance(conn, server.PostgresConnectionWrapper)
            conn.close()

    def test_dsn_change_rebuilds_the_pool(self):
        created = []

        def fake_create(dsn):
            conn = FakeRawConn(status=0)
            created.append(conn)
            return conn

        other_dsn = "postgresql://user:pass@ep-other.neon.tech/neondb"
        with patch.object(server, "is_production_env", return_value=False), \
             patch.object(server, "_create_raw_postgres_connection", side_effect=fake_create):
            with patch.object(server, "DATABASE_URL", REMOTE_DSN):
                a = server.get_db()
                a.close()
            with patch.object(server, "DATABASE_URL", other_dsn):
                b = server.get_db()
                b.close()
        self.assertEqual(len(created), 2)
        self.assertIsNot(a.raw_conn, b.raw_conn)


# --------------------------------------------------------------------------- auth
class FakeAuthCursor(object):
    def __init__(self, row):
        self._row = row
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self._row


class FakeAuthConn(object):
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.committed = 0
        self.closed = False

    def cursor(self):
        cur = FakeAuthCursor(self.row)
        self.executed.append(cur)
        return cur

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class AnonymousAuthFastPathTests(unittest.TestCase):

    def _forbid_db(self):
        conn = FakeAuthConn()
        opened = {"n": 0}

        def fake_get_db():
            opened["n"] += 1
            return conn

        return fake_get_db, opened

    def test_no_headers_does_not_open_a_connection(self):
        fake_get_db, opened = self._forbid_db()
        with patch.object(server, "get_db", side_effect=fake_get_db):
            self.assertIsNone(server.get_current_user({}))
        self.assertEqual(opened["n"], 0)

    def test_bearer_placeholder_tokens_do_not_open_a_connection(self):
        for token in ("null", "undefined", ""):
            with self.subTest(token=token):
                fake_get_db, opened = self._forbid_db()
                with patch.object(server, "get_db", side_effect=fake_get_db):
                    self.assertIsNone(
                        server.get_current_user({"Authorization": "Bearer %s" % token})
                    )
                self.assertEqual(opened["n"], 0)

    def test_cookie_without_session_token_does_not_open_a_connection(self):
        fake_get_db, opened = self._forbid_db()
        with patch.object(server, "get_db", side_effect=fake_get_db):
            self.assertIsNone(server.get_current_user({"Cookie": "theme=dark; other=1"}))
        self.assertEqual(opened["n"], 0)

    def test_placeholder_cookie_token_does_not_open_a_connection(self):
        fake_get_db, opened = self._forbid_db()
        with patch.object(server, "get_db", side_effect=fake_get_db):
            self.assertIsNone(
                server.get_current_user({"Cookie": "kandid_token=null"})
            )
        self.assertEqual(opened["n"], 0)


class AuthenticatedRequestTests(unittest.TestCase):

    def test_valid_token_still_queries_and_returns_user(self):
        row = {"id": "u1", "handle": "hank", "password_hash": "x"}
        conn = FakeAuthConn(row=row)
        with patch.object(server, "get_db", return_value=conn):
            user = server.get_current_user({"Authorization": "Bearer good-token"})
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], "u1")
        self.assertNotIn("password_hash", user)
        self.assertEqual(conn.committed, 1)      # last_active update preserved
        self.assertTrue(conn.closed)

    def test_invalid_token_still_opens_connection_and_returns_none(self):
        conn = FakeAuthConn(row=None)
        opened = {"n": 0}

        def fake_get_db():
            opened["n"] += 1
            return conn

        with patch.object(server, "get_db", side_effect=fake_get_db):
            self.assertIsNone(server.get_current_user({"Authorization": "Bearer bad-token"}))
        self.assertEqual(opened["n"], 1)

    def test_expired_session_row_returns_none_but_queries(self):
        conn = FakeAuthConn(row=None)
        with patch.object(server, "get_db", return_value=conn):
            self.assertIsNone(server.get_current_user({"Cookie": "kandid_session=expired"}))
        self.assertTrue(conn.executed, "session lookup must still run for present tokens")

    def test_banned_user_is_rejected(self):
        row = {"id": "u2", "role": "banned", "account_status": "banned"}
        conn = FakeAuthConn(row=row)
        with patch.object(server, "get_db", return_value=conn):
            self.assertIsNone(server.get_current_user({"Authorization": "Bearer tok"}))
        self.assertTrue(conn.closed)


# ------------------------------------------------------------------- drivers
class DriverSelectionTests(unittest.TestCase):
    """Both supported drivers must remain selectable and lifecycle-safe."""

    def test_uses_psycopg2_when_available(self):
        fake = MagicMock()
        with patch.dict("sys.modules", {"psycopg2": fake}):
            raw = server._create_raw_postgres_connection(REMOTE_DSN)
        fake.connect.assert_called_once_with(REMOTE_DSN)
        self.assertIs(raw, fake.connect.return_value)

    def test_falls_back_to_pg8000_when_psycopg2_missing(self):
        import pg8000.dbapi  # real installed driver
        sentinel = object()
        with patch.dict("sys.modules", {"psycopg2": None}), \
             patch("pg8000.dbapi.connect", return_value=sentinel) as mock_connect:
            raw = server._create_raw_postgres_connection(REMOTE_DSN)
        mock_connect.assert_called_once()
        kwargs = mock_connect.call_args[1]
        self.assertIn("ssl_context", kwargs)   # pg8000 TLS handling preserved
        self.assertIs(raw, sentinel)

    def test_pg8000_style_connection_is_pooled_safely(self):
        """A driver with no .info/transaction_status is rolled back then pooled."""

        class PlainConn(object):
            def __init__(self):
                self.closed = False
                self.rolled_back = 0

            def rollback(self):
                self.rolled_back += 1

            def close(self):
                self.closed = True

        pool = server.PostgresConnectionPool(create_fn=lambda: PlainConn(), max_size=1)
        raw = pool.acquire()
        pool.release(raw)
        self.assertEqual(raw.rolled_back, 1)
        self.assertEqual(pool.idle_count, 1)


if __name__ == "__main__":
    unittest.main()
