#!/usr/bin/env python3
"""
Phase 1 remediation tests: pool-slot leak safety (B1), use-after-release guards
(H1), stale-connection recovery (H2), pool lifecycle / reporting (M1, M2, M3,
DB_POOL_MIN), and DSN-change disposal.

Run with:  python -m unittest test_pool_safety_remediation

These tests exercise the REAL pool / wrapper implementation with injected fake
raw connections (to simulate driver states and failures deterministically).
Real-driver / real-PostgreSQL behaviour is covered separately in
test_pool_safety_real_pg.py; mocked driver tests here do not claim real
compatibility on their own.
"""

import http.client
import threading
import time
import unittest
from unittest.mock import patch

import server


REMOTE_DSN = "postgresql://user:pass@ep-remediation.neon.tech/neondb"


# --------------------------------------------------------------------------- fakes
class FakeInfo(object):
    def __init__(self, status=0):
        self.transaction_status = status


class FakeCursor(object):
    def __init__(self, raise_on_execute=False):
        self.executed = []
        self._raise = raise_on_execute
        self.closed = False

    def execute(self, sql, params=None):
        if self._raise:
            raise RuntimeError("simulated stale-connection failure")
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return []

    def close(self):
        self.closed = True


class FakeRawConn(object):
    """Minimal raw DB-API connection stand-in."""

    def __init__(self, status=0, fail_probe=False):
        self.closed = 0
        self.info = FakeInfo(status)
        self.rolled_back = 0
        self.committed = 0
        self.close_calls = 0
        self.rollback_raises = False
        self.fail_probe = fail_probe
        self.cursor_calls = 0

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
        self.cursor_calls += 1
        if self.fail_probe:
            raise RuntimeError("simulated stale connection")
        return FakeCursor()


def make_pool(max_size=2, timeout=1.0, min_size=0, validate_idle=5.0, fail_after=None,
              status=0):
    created = []

    def create():
        if fail_after is not None and len(created) >= fail_after:
            raise RuntimeError("simulated create failure")
        conn = FakeRawConn(status=status)
        created.append(conn)
        return conn

    pool = server.PostgresConnectionPool(
        create_fn=create, max_size=max_size, min_size=min_size,
        acquire_timeout=timeout, validate_idle_seconds=validate_idle,
    )
    return pool, created


def acquire_wrapper(pool):
    return server.PooledPostgresConnectionWrapper(pool.acquire(), pool)


def _clear_thread_registry():
    server._checked_out_list()[:] = []


# --------------------------------------------------------------------------- B1
class LeakSafetyTests(unittest.TestCase):
    """B1: exceptions must not permanently leak pool slots."""

    def setUp(self):
        _clear_thread_registry()

    def tearDown(self):
        _clear_thread_registry()

    def test_repeated_route_exceptions_do_not_exhaust_pool(self):
        pool, created = make_pool(max_size=5, timeout=1.0)
        for _ in range(50):
            # A route that acquires and then raises before conn.close().
            wrapper = acquire_wrapper(pool)
            self.assertIn(wrapper, server._checked_out_list())
            try:
                raise RuntimeError("simulated route DB error")
            except RuntimeError:
                pass
            finally:
                server._release_checked_out_pooled_connections()
            self.assertEqual(pool.idle_count + 0, pool.size)  # all returned

        # Pool must remain fully usable after 50 leaked-on-exception requests.
        self.assertEqual(pool.size, 1)          # a single connection was reused
        self.assertLessEqual(len(created), 5)
        again = pool.acquire()
        self.assertIsNotNone(again)
        pool.release(again)

    def test_boundary_release_is_exactly_once(self):
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        raw = wrapper.raw_conn
        server._release_checked_out_pooled_connections()
        server._release_checked_out_pooled_connections()   # idempotent
        self.assertEqual(pool.size, 1)
        self.assertEqual(pool.idle_count, 1)
        self.assertEqual(raw.close_calls, 0)               # returned, not closed

    def test_already_closed_connection_is_not_released_twice(self):
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        wrapper.close()                                     # normal route close
        server._release_checked_out_pooled_connections()    # boundary no-op
        self.assertEqual(pool.size, 1)
        self.assertEqual(pool.idle_count, 1)

    def test_nested_close_does_not_disturb_outer_connection(self):
        """Closing a nested connection (get_current_user pattern) must not touch
        the handler's own connection; the boundary then releases it exactly once."""
        pool, created = make_pool(max_size=3, timeout=1.0)
        outer = acquire_wrapper(pool)      # handler connection
        inner = acquire_wrapper(pool)      # get_current_user() connection
        inner.close()                      # nested auth connection closed normally

        # The outer connection is untouched and still usable in-request.
        self.assertFalse(outer._released)
        outer.execute("SELECT 1")
        self.assertEqual(pool.idle_count, 1)           # only inner was returned
        self.assertEqual(pool.size, 2)
        self.assertEqual(inner.raw_conn.close_calls, 0)

        # Request end: boundary releases the still-open outer connection once.
        server._release_checked_out_pooled_connections()
        self.assertEqual(pool.idle_count, 2)
        self.assertEqual(pool.size, 2)
        outer.close()                                   # idempotent, no double release
        self.assertEqual(pool.size, 2)
        self.assertEqual(pool.idle_count, 2)

    def test_registry_is_cleared_even_if_closed_from_another_thread(self):
        """A close() from a different thread must not leave a stale registry entry."""
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        # Close from another thread (unusual, but must not corrupt the registry).
        t = threading.Thread(target=wrapper.close)
        t.start()
        t.join()
        self.assertEqual(pool.idle_count, 1)
        # The acquiring thread's boundary still clears its registry entry.
        self.assertIn(wrapper, server._checked_out_list())
        server._release_checked_out_pooled_connections()
        self.assertEqual(server._checked_out_list(), [])
        self.assertEqual(pool.size, 1)          # released exactly once, not leaked
        self.assertEqual(pool.idle_count, 1)

    def test_cleanup_is_thread_local(self):
        pool, _ = make_pool(max_size=2)
        acquire_wrapper(pool)                               # held by THIS thread
        observed = {}

        def other_thread():
            server._release_checked_out_pooled_connections()
            observed["idle"] = pool.idle_count

        t = threading.Thread(target=other_thread)
        t.start()
        t.join()
        self.assertEqual(observed["idle"], 0)               # other thread released nothing
        self.assertEqual(pool.idle_count, 0)
        server._release_checked_out_pooled_connections()
        self.assertEqual(pool.idle_count, 1)

    def test_get_current_user_session_query_failure_then_pool_reuse(self):
        """A failing session lookup must not permanently consume a slot."""
        pool, created = make_pool(max_size=2, timeout=1.0)
        fail_raw = FakeRawConn(fail_probe=True)
        wrapper = server.PooledPostgresConnectionWrapper(fail_raw, pool)

        with patch.object(server, "get_db", return_value=wrapper):
            with self.assertRaises(RuntimeError):
                server.get_current_user({"Authorization": "Bearer good-token"})

        # Request boundary cleanup runs.
        server._release_checked_out_pooled_connections()
        # The failed connection is discarded (probe/rollback failure), slot freed.
        self.assertEqual(pool.size, 0)
        healthy = pool.acquire()            # pool still usable
        self.assertIsNotNone(healthy)
        pool.release(healthy)

    def test_worker_style_loop_survives_repeated_failures(self):
        """Mirror the chat worker: acquire -> raise -> finally boundary release."""
        pool, _ = make_pool(max_size=3, timeout=1.0)
        for _ in range(20):
            try:
                acquire_wrapper(pool)
                raise RuntimeError("worker iteration failure")
            except RuntimeError:
                pass
            finally:
                server._release_checked_out_pooled_connections()
        self.assertEqual(pool.idle_count, pool.size)
        self.assertLessEqual(pool.size, 3)


# --------------------------------------------------------------------------- H1
class UseAfterReleaseTests(unittest.TestCase):
    """H1: post-release operations must not touch a reused raw connection."""

    def setUp(self):
        _clear_thread_registry()

    def tearDown(self):
        _clear_thread_registry()

    def test_account_deletion_exception_after_close_cannot_rollback_other_request(self):
        """Reproduce the account-deletion except path after close()."""
        pool, _ = make_pool(max_size=1, timeout=1.0)

        # Request A finishes its work and closes (returns conn to the pool).
        conn_a = acquire_wrapper(pool)
        raw_a = conn_a.raw_conn
        conn_a.commit()
        conn_a.close()

        # Request B now legitimately owns the same raw connection.
        conn_b = acquire_wrapper(pool)
        self.assertIs(conn_b.raw_conn, raw_a)
        conn_b.execute("INSERT INTO t VALUES (1)")   # B begins a transaction
        before_commits = raw_a.committed
        before_rollbacks = raw_a.rolled_back

        # Request A's exception handler runs late: rollback() + close() again.
        conn_a.rollback()
        conn_a.close()

        # A must NOT have rolled back or closed B's in-flight connection.
        self.assertEqual(raw_a.rolled_back, before_rollbacks)
        self.assertEqual(raw_a.committed, before_commits)
        self.assertEqual(raw_a.close_calls, 0)
        self.assertEqual(pool.size, 1)

        # B's transaction is still ours to control.
        conn_b.commit()
        conn_b.close()
        self.assertEqual(raw_a.committed, before_commits + 1)

    def test_commit_after_release_is_noop(self):
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        raw = wrapper.raw_conn
        wrapper.close()
        wrapper.commit()
        wrapper.rollback()
        self.assertEqual(raw.committed, 0)
        self.assertEqual(raw.rolled_back, 0)

    def test_cursor_and_execute_after_release_raise(self):
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        wrapper.close()
        with self.assertRaises(RuntimeError):
            wrapper.cursor()
        with self.assertRaises(RuntimeError):
            wrapper.execute("SELECT 1")
        with self.assertRaises(RuntimeError):
            wrapper.executescript("SELECT 1")

    def test_concurrent_close_is_idempotent(self):
        pool, _ = make_pool(max_size=2)
        wrapper = acquire_wrapper(pool)
        raw = wrapper.raw_conn
        errors = []

        def closer():
            try:
                wrapper.close()
            except Exception as exc:      # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=closer) for _ in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(pool.size, 1)          # released exactly once
        self.assertEqual(pool.idle_count, 1)
        self.assertEqual(raw.close_calls, 0)

    def test_commit_failure_is_not_swallowed(self):
        """A failing commit while still checked out must raise (no false success)."""
        pool, _ = make_pool(max_size=2)

        class FailingCommitRaw(FakeRawConn):
            def commit(self):
                raise RuntimeError("commit failed")

        wrapper = server.PooledPostgresConnectionWrapper(FailingCommitRaw(), pool)
        with self.assertRaises(RuntimeError):
            wrapper.commit()
        # Connection still ours until explicitly closed.
        self.assertFalse(wrapper._released)


# --------------------------------------------------------------------------- H2
class StaleConnectionTests(unittest.TestCase):
    """H2: idle dead connections must be discarded and replaced."""

    def setUp(self):
        _clear_thread_registry()

    def tearDown(self):
        _clear_thread_registry()

    def test_recently_used_connection_is_not_probed(self):
        pool, created = make_pool(max_size=2, validate_idle=5.0)
        wrapper = acquire_wrapper(pool)
        wrapper.close()
        reused = acquire_wrapper(pool)
        self.assertIs(reused.raw_conn, created[0])   # same connection reused
        self.assertEqual(created[0].cursor_calls, 0)  # and NO validation round trip
        reused.close()

    def test_idle_connection_past_ttl_is_probed_and_validated(self):
        pool, created = make_pool(max_size=2, validate_idle=0.05)
        wrapper = acquire_wrapper(pool)
        wrapper.close()
        time.sleep(0.08)
        reused = acquire_wrapper(pool)
        self.assertIs(reused.raw_conn, created[0])        # healthy -> reused
        self.assertGreaterEqual(created[0].cursor_calls, 1)  # probe DID run
        self.assertGreaterEqual(created[0].rolled_back, 1)  # probe transaction ended
        reused.close()

    def test_stale_after_database_restart_is_replaced(self):
        """A psycopg2-style connection that died silently must be discarded."""
        pool, created = make_pool(max_size=2, validate_idle=0.05)
        wrapper = acquire_wrapper(pool)
        raw = wrapper.raw_conn
        wrapper.close()

        # Simulate a database restart: the idle connection's socket is dead.
        raw.fail_probe = True
        time.sleep(0.08)

        replacement = acquire_wrapper(pool)
        self.assertIsNot(replacement.raw_conn, raw)      # stale one discarded
        self.assertEqual(raw.close_calls, 1)
        self.assertEqual(len(created), 2)                # a fresh one was made
        self.assertEqual(pool.size, 1)
        replacement.close()

    def test_stale_discard_preserves_pool_capacity(self):
        """Replacement after staleness must not shrink the pool permanently."""
        pool, created = make_pool(max_size=1, validate_idle=0.05)
        wrapper = acquire_wrapper(pool)
        raw = wrapper.raw_conn
        wrapper.close()
        raw.fail_probe = True
        time.sleep(0.08)
        a = acquire_wrapper(pool)
        a.close()
        self.assertEqual(pool.size, 1)                   # capacity restored, not leaked
        self.assertEqual(pool.idle_count, 1)

    def test_pg8000_closed_connection_detected_by_cheap_probe(self):
        """pg8000 has no .closed; it clears _usock on close()."""

        class Pg8000LikeConn(object):
            def __init__(self):
                self._usock = object()
                self._sock = object()

            def rollback(self):
                pass

            def close(self):
                self._usock = None
                self._sock = None

            def cursor(self, *a, **k):
                return FakeCursor()

        conn = Pg8000LikeConn()
        self.assertTrue(server._raw_connection_is_usable(conn))
        conn.close()
        self.assertFalse(server._raw_connection_is_usable(conn))

    def test_pg8000_closed_idle_connection_is_discarded_and_replaced(self):
        class Pg8000LikeConn(object):
            def __init__(self):
                self._usock = object()
                self.close_calls = 0

            def rollback(self):
                pass

            def close(self):
                self.close_calls += 1
                self._usock = None

            def cursor(self, *a, **k):
                return FakeCursor()

        created = []

        def create():
            c = Pg8000LikeConn()
            created.append(c)
            return c

        pool = server.PostgresConnectionPool(create_fn=create, max_size=1,
                                             acquire_timeout=1.0, validate_idle_seconds=0.05)
        wrapper = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
        wrapper.close()
        created[0].close()                    # simulate driver-level close while idle
        time.sleep(0.08)
        replacement = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
        self.assertIsNot(replacement.raw_conn, created[0])
        self.assertEqual(len(created), 2)
        replacement.close()

    def test_pool_recovers_after_exhaustion_and_release(self):
        pool, _ = make_pool(max_size=1, timeout=5.0)
        held = pool.acquire()
        result = {}

        def waiter():
            result["conn"] = pool.acquire()

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.2)
        pool.release(held)                    # free the only slot
        t.join(timeout=2)
        self.assertFalse(t.is_alive())
        self.assertIs(result["conn"], held)   # released slot reused
        pool.release(result["conn"])


# --------------------------------------------------------------------------- M1/M3/min
class LifecycleAndReportingTests(unittest.TestCase):

    def setUp(self):
        self._pool, self._dsn = server._PG_POOL, server._PG_POOL_DSN
        server._PG_POOL, server._PG_POOL_DSN = None, None
        _clear_thread_registry()

    def tearDown(self):
        server._PG_POOL, server._PG_POOL_DSN = self._pool, self._dsn
        _clear_thread_registry()

    def test_dsn_change_disposes_old_idle_connections_only(self):
        created = []

        def fake_create(dsn):
            c = FakeRawConn()
            created.append(c)
            return c

        dsn_a = "postgresql://u:p@ep-a.neon.tech/db"
        dsn_b = "postgresql://u:p@ep-b.neon.tech/db"

        with patch.object(server, "is_production_env", return_value=False), \
             patch.object(server, "_create_raw_postgres_connection", side_effect=fake_create):
            with patch.object(server, "DATABASE_URL", dsn_a):
                checked_out = server.get_db()          # in-flight request
                idle = server.get_db()
                idle.close()                           # returned to pool
                old_pool = server._PG_POOL
                old_raw_checked_out = checked_out.raw_conn
                old_raw_idle = idle.raw_conn
            with patch.object(server, "DATABASE_URL", dsn_b):
                fresh = server.get_db()
                new_pool = server._PG_POOL

        self.assertIsNot(old_pool, new_pool)
        self.assertTrue(old_pool._closed)
        self.assertEqual(old_raw_idle.close_calls, 1)          # idle disposed
        self.assertEqual(old_raw_checked_out.close_calls, 0)   # NOT invalidated mid-flight
        self.assertNotEqual(fresh.raw_conn, old_raw_checked_out)

        # The in-flight old connection is closed when its request releases it.
        checked_out.close()
        self.assertEqual(old_raw_checked_out.close_calls, 1)
        self.assertEqual(old_pool.size, 0)
        fresh.close()

    def test_exhaustion_reported_distinctly_from_connect_failure(self):
        pool, _ = make_pool(max_size=1, timeout=0.1)
        held = pool.acquire()
        secure = "normalized-dsn"
        with patch.object(server, "DATABASE_URL", REMOTE_DSN), \
             patch.object(server, "_ensure_secure_sslmode", return_value=secure), \
             patch.object(server, "_PG_POOL", pool), \
             patch.object(server, "_PG_POOL_DSN", secure):
            with self.assertRaises(RuntimeError) as ctx:
                server.get_db()
        msg = str(ctx.exception)
        self.assertIn("pool exhausted", msg.lower())
        self.assertNotIn("Failed to connect", msg)
        pool.release(held)

    def test_connect_failure_still_reported_as_connect_failure(self):
        with patch.object(server, "DATABASE_URL", REMOTE_DSN), \
             patch.object(server, "is_production_env", return_value=True), \
             patch.object(server, "_create_raw_postgres_connection",
                          side_effect=RuntimeError("refused")):
            with self.assertRaises(RuntimeError) as ctx:
                server.get_db()
        self.assertIn("Failed to connect to production PostgreSQL database", str(ctx.exception))

    def test_db_pool_min_warms_up_connections(self):
        created = []

        def create():
            c = FakeRawConn()
            created.append(c)
            return c

        pool = server.PostgresConnectionPool(create_fn=create, max_size=5, min_size=3,
                                             acquire_timeout=1.0)
        self.assertEqual(pool.size, 3)
        self.assertEqual(pool.idle_count, 3)
        self.assertEqual(len(created), 3)

    def test_db_pool_min_partial_failure_keeps_accounting_consistent(self):
        calls = {"n": 0}

        def create():
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("db unavailable")
            return FakeRawConn()

        pool = server.PostgresConnectionPool(create_fn=create, max_size=5, min_size=3,
                                             acquire_timeout=0.5)
        self.assertEqual(pool.size, 1)            # only the first succeeded
        self.assertEqual(pool.idle_count, 1)
        # No negative/over-counted accounting; the pool is still usable.
        conn = pool.acquire()
        pool.release(conn)
        self.assertEqual(pool.size, 1)

    def test_min_size_clamped_by_max(self):
        pool = server.PostgresConnectionPool(create_fn=lambda: FakeRawConn(),
                                             max_size=2, min_size=10,
                                             acquire_timeout=1.0)
        self.assertEqual(pool.size, 2)

    def test_pool_respects_max_under_concurrent_creation(self):
        created = []
        lock = threading.Lock()

        def create():
            c = FakeRawConn()
            with lock:
                created.append(c)
            time.sleep(0.001)
            return c

        pool = server.PostgresConnectionPool(create_fn=create, max_size=3,
                                             acquire_timeout=10.0)
        held = []
        guard = threading.Lock()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    c = pool.acquire()
                    with guard:
                        held.append(c)
                    time.sleep(0.001)
                    with guard:
                        held.remove(c)
                    pool.release(c)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertLessEqual(len(created), 3)
        self.assertLessEqual(pool.size, 3)



# --------------------------------------------------------------------------- B1 (HTTP boundary wiring)
class HttpBoundaryReleaseTests(unittest.TestCase):
    """B1 wiring: the *real* KandidHandler.handle_one_request boundary must
    release pooled connections that a route checked out but never closed.

    The LeakSafetyTests above call _release_checked_out_pooled_connections()
    directly, so they do not prove that handle_one_request actually invokes it
    on every exit path. These tests drive a real ThreadingMixIn HTTP server and
    a handler whose "route" raises after checking out a pooled connection, so
    the release has to happen inside the production boundary itself.

    Note: the boundary writes the 500 response before its finally block runs,
    so the client can observe the reply while the request thread is still
    finishing. Assertions therefore await the expected pool state (bounded)
    instead of reading it immediately.
    """

    def setUp(self):
        _clear_thread_registry()
        self._srv = None
        self._thread = None

    def tearDown(self):
        if self._srv is not None:
            try:
                self._srv.shutdown()
            finally:
                self._srv.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        _clear_thread_registry()

    # -- helpers ----------------------------------------------------------
    def _serve(self, pool, route):
        """Start a real HTTP server whose do_POST runs `route`; return the port."""
        def get_db_stub():
            return server.PooledPostgresConnectionWrapper(pool.acquire(), pool)

        class _RouteHandler(server.KandidHandler):
            def do_POST(self):                      # a "route" that may raise
                route(self, get_db_stub)

        srv = server.KandidThreadingServer(("127.0.0.1", 0), _RouteHandler)
        self._srv = srv
        self._thread = threading.Thread(
            target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self._thread.start()
        return srv.server_address[1]

    def _post(self, port, path="/api/phase1-boundary-probe"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("POST", path, body=b"{}", headers={
                "Content-Type": "application/json", "Connection": "close"})
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def _await_idle(self, pool, expected, timeout=5.0):
        """Wait (bounded) for the request thread's boundary cleanup to land."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pool.idle_count == expected:
                return pool.idle_count
            time.sleep(0.005)
        return pool.idle_count

    # -- pool backed by fakes whose cursors expose a result description ------
    @staticmethod
    def _probe_pool(max_size=1, timeout=0.5):
        class _DescribingCursor(FakeCursor):
            description = [("probe",)]

        class _DescribingRawConn(FakeRawConn):
            def cursor(self, *a, **k):
                self.cursor_calls += 1
                return _DescribingCursor()

        return server.PostgresConnectionPool(
            create_fn=_DescribingRawConn, max_size=max_size, acquire_timeout=timeout)

    # -- tests ------------------------------------------------------------
    def test_route_exception_releases_pooled_connection(self):
        """A route that raises must not leak the connection it checked out."""
        pool, created = make_pool(max_size=1, timeout=0.5)

        def route(handler, get_db):
            get_db()                       # checked out, never closed
            raise RuntimeError("simulated route failure after get_db()")

        port = self._serve(pool, route)
        status, _body = self._post(port)

        self.assertEqual(status, 500)                       # generic JSON 500
        self.assertEqual(self._await_idle(pool, 1), 1,
                         "boundary did not release the checked-out slot")
        self.assertEqual(pool.size, 1)
        self.assertEqual(created[0].closed, 0)              # handed back, not destroyed

    def test_repeated_route_exceptions_do_not_exhaust_pool(self):
        """With max=1, repeated failures must still allow the next request."""
        pool, _created = make_pool(max_size=1, timeout=0.5)

        def route(handler, get_db):
            get_db()
            raise RuntimeError("simulated repeated route failure")

        port = self._serve(pool, route)
        for attempt in range(5):
            status, _body = self._post(port)
            self.assertEqual(status, 500)
            self.assertEqual(self._await_idle(pool, 1), 1,
                             "request %d lost a pool slot" % (attempt + 1))

        # ...and the pool is still usable afterwards.
        probe_pool = self._probe_pool(max_size=1)
        conn = acquire_wrapper(probe_pool)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        self.assertEqual(cur.fetchone(), (1,))
        conn.close()
        self.assertEqual(probe_pool.idle_count, 1)

    def test_route_that_closed_before_raising_releases_exactly_once(self):
        """The boundary must not double-release a connection a route already closed."""
        pool, created = make_pool(max_size=1, timeout=0.5)

        def route(handler, get_db):
            get_db().close()
            raise RuntimeError("simulated failure after conn.close()")

        port = self._serve(pool, route)
        status, _body = self._post(port)

        self.assertEqual(status, 500)
        self.assertEqual(self._await_idle(pool, 1), 1)
        # Exactly one live connection: a second release would drop size to 0.
        self.assertEqual(pool.size, 1, "connection released more than once")
        self.assertEqual(created[0].close_calls, 0,
                         "the raw connection was destroyed instead of pooled")

    def test_all_nested_acquisitions_are_released(self):
        """Every connection the request thread checked out is released."""
        pool, _created = make_pool(max_size=2, timeout=0.5)

        def route(handler, get_db):
            get_db()
            get_db()
            raise RuntimeError("simulated failure holding two connections")

        port = self._serve(pool, route)
        status, _body = self._post(port)

        self.assertEqual(status, 500)
        self.assertEqual(self._await_idle(pool, 2), 2)
        self.assertEqual(pool.size, 2)

    def test_successful_request_releases_pooled_connection(self):
        """The boundary releases on the normal path too."""
        pool, _created = make_pool(max_size=1, timeout=0.5)

        def route(handler, get_db):
            conn = get_db()
            conn.cursor().execute("SELECT 1")
            conn.close()
            handler.send_json(200, {"success": True})

        port = self._serve(pool, route)
        status, body = self._post(port)

        self.assertEqual(status, 200)
        self.assertIn(b"true", body.lower())
        self.assertEqual(self._await_idle(pool, 1), 1)
        self.assertEqual(pool.size, 1)



if __name__ == "__main__":
    unittest.main()
