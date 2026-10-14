#!/usr/bin/env python3
"""
Phase 1 remediation - REAL PostgreSQL integration tests.

These tests exercise the connection pool against a genuine PostgreSQL server
(bundled binaries via the optional `pgserver` package) using the REAL drivers
(psycopg2 and pg8000). They are the evidence that the mocked unit tests cannot
provide: real transaction state, real socket death after a database restart,
and real rollback-on-release behaviour.

Isolation / cleanup
-------------------
This module creates its OWN disposable PostgreSQL cluster in a unique
``mkdtemp()`` directory (``cleanup_mode="delete"``) and tears it down in a
module cleanup that also runs when a test or setup step fails. It never reads,
stops, signals or deletes a shared/hardcoded path (e.g. /tmp/pgdata) and never
targets a PostgreSQL instance it did not start itself: every stop/kill it
performs uses the process recorded in the temp cluster's own postmaster.pid.

The whole module is skipped when a real PostgreSQL server cannot be started,
so it never blocks a normal test run.

Run with:  python -m unittest test_pool_safety_real_pg
"""

import os
import shutil
import signal
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import server


_TMP_BASE = None          # unique mkdtemp() parent owned by this module
_PGDATA = None            # disposable cluster directory inside _TMP_BASE
_PG = None                # pgserver handle for _PGDATA only
_PG_ERROR = None
_SOCKET = None


def _pg_dsn():
    """DSN for OUR disposable cluster, derived from its live postmaster info.

    Built from the running server's own socket directory/port, so there is no
    hardcoded host path and the value stays correct after a restart.
    """
    info = _PG.get_postmaster_info()
    return "postgresql://postgres:@/postgres?host=%s&port=%s" % (info.socket_dir, info.port)


def _socket_path():
    info = _PG.get_postmaster_info()
    return os.path.join(str(info.socket_dir), ".s.PGSQL.%s" % info.port)


def _cleanup_pg():
    """Stop and delete ONLY the disposable cluster this module created.

    Registered as a module cleanup, so it runs even when setup or a test fails.
    Idempotent: safe to call from tearDownModule, the module cleanup, and the
    pgserver atexit hook.
    """
    global _PG
    pg, _PG = _PG, None
    if pg is not None:
        try:
            # Stops the postmaster recorded in OUR pgdata and removes OUR pgdata.
            pg.cleanup()
        except Exception:
            pass
    if _TMP_BASE:
        base = os.path.abspath(_TMP_BASE)
        # Never delete anything unless it is the exact temp dir we created.
        if (os.path.isdir(base)
                and os.path.dirname(base) == os.path.realpath(tempfile.gettempdir())
                and os.path.basename(base).startswith("kandid_phase1_pg_")):
            shutil.rmtree(base, ignore_errors=True)


def tearDownModule():
    _cleanup_pg()


def setUpModule():
    global _TMP_BASE, _PGDATA, _PG, _PG_ERROR, _SOCKET
    try:
        import pgserver  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "pgserver not installed: %s" % exc
        raise unittest.SkipTest(_PG_ERROR)

    # A unique directory only we know about: co-exists with any other
    # PostgreSQL instance on the machine instead of sharing a path with it.
    try:
        _TMP_BASE = tempfile.mkdtemp(prefix="kandid_phase1_pg_")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise unittest.SkipTest("could not create a temp directory: %r" % exc)
    _PGDATA = os.path.join(_TMP_BASE, "data")

    # Registered before anything can fail, so the cluster is always torn down.
    unittest.addModuleCleanup(_cleanup_pg)

    try:
        _PG = pgserver.get_server(_PGDATA, cleanup_mode="delete")
        _PG.ensure_postgres_running()
        _SOCKET = _socket_path()
        # Verify the cluster really accepts a connection before running.
        import psycopg2
        c = psycopg2.connect(_pg_dsn())
        c.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "could not start an isolated disposable PostgreSQL: %r" % exc
        raise unittest.SkipTest(_PG_ERROR)


def _reset_pool():
    p = server._PG_POOL
    if p is not None:
        try:
            p.close_all()
        except Exception:
            pass
    server._PG_POOL = None
    server._PG_POOL_DSN = None
    server._checked_out_list()[:] = []


class RealPostgresBase(unittest.TestCase):
    def setUp(self):
        _reset_pool()
        self._url = server.DATABASE_URL
        self._env = server.ENVIRONMENT
        server.DATABASE_URL = _pg_dsn()
        server.ENVIRONMENT = "development"
        # ensure a clean table
        import psycopg2
        c = psycopg2.connect(_pg_dsn())
        try:
            cur = c.cursor()
            cur.execute("DROP TABLE IF EXISTS phase1_probe")
            cur.execute("CREATE TABLE phase1_probe (id int)")
            c.commit()
        finally:
            c.close()

    def tearDown(self):
        _reset_pool()
        server.DATABASE_URL = self._url
        server.ENVIRONMENT = self._env

    def _count_rows(self):
        import psycopg2
        c = psycopg2.connect(_pg_dsn())
        try:
            cur = c.cursor()
            cur.execute("SELECT count(*) FROM phase1_probe")
            return cur.fetchone()[0]
        finally:
            c.close()


class RealPsycopg2Tests(RealPostgresBase):

    def test_connection_is_reused_across_requests(self):
        with patch.object(server, "is_production_env", return_value=True):
            a = server.get_db()
            self.assertIsInstance(a, server.PooledPostgresConnectionWrapper)
            cur = a.cursor(); cur.execute("SELECT 1"); self.assertEqual(list(cur.fetchone())[0], 1)
            a.close()
            b = server.get_db()
            self.assertIs(a.raw_conn, b.raw_conn)          # real socket reused
            b.close()
        self.assertEqual(server._PG_POOL.size, 1)

    def test_uncommitted_transaction_is_rolled_back_before_reuse(self):
        """A connection must never be pooled with an open transaction."""
        with patch.object(server, "is_production_env", return_value=True):
            a = server.get_db()
            a.execute("INSERT INTO phase1_probe (id) VALUES (1)")   # opens a txn
            # status must now be INTRANS
            self.assertNotEqual(a.raw_conn.info.transaction_status, 0)
            a.close()                                               # no commit
            b = server.get_db()
            self.assertIs(b.raw_conn, a.raw_conn)
            self.assertEqual(b.raw_conn.info.transaction_status, 0)  # IDLE again
            b.close()
        self.assertEqual(self._count_rows(), 0, "uncommitted insert must have been rolled back")

    def test_committed_work_persists_across_reuse(self):
        with patch.object(server, "is_production_env", return_value=True):
            a = server.get_db()
            a.execute("INSERT INTO phase1_probe (id) VALUES (42)")
            a.commit()
            a.close()
            b = server.get_db()
            self.assertIs(b.raw_conn, a.raw_conn)
            cur = b.cursor(); cur.execute("SELECT count(*) FROM phase1_probe")
            self.assertEqual(list(cur.fetchone())[0], 1)
            b.close()
        self.assertEqual(self._count_rows(), 1)

    def test_stale_connection_after_real_restart_is_replaced(self):
        """Real database restart: the idle pooled connection must be discarded."""
        with patch.object(server, "is_production_env", return_value=True):
            a = server.get_db()
            a.close()
            pool = server._PG_POOL
            stale_raw = pool._idle[-1][0]
            self.assertEqual(stale_raw.info.transaction_status, 0)   # looks healthy locally

            pid = _PG.get_pid()
            os.kill(pid, signal.SIGKILL)                             # simulate restart
            time.sleep(0.5)
            _PG.ensure_postgres_running()
            time.sleep(0.5)

            # Force the validate-on-borrow path for all idle connections.
            pool._validate_idle = 0.01
            time.sleep(0.05)

            fresh = server.get_db()
            self.assertIsNot(fresh.raw_conn, stale_raw)              # dead conn discarded
            cur = fresh.cursor(); cur.execute("SELECT 1")
            self.assertEqual(list(cur.fetchone())[0], 1)             # replacement works
            fresh.close()
            self.assertEqual(pool.size, 1)                           # capacity preserved

    def test_repeated_database_restarts_recover_each_time(self):
        """Stale idle connections must be discarded on every restart, not just once."""
        with patch.object(server, "is_production_env", return_value=True):
            for attempt in range(2):
                a = server.get_db()
                a.close()
                pool = server._PG_POOL
                stale_raw = pool._idle[-1][0]

                pid = _PG.get_pid()
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
                _PG.ensure_postgres_running()
                time.sleep(0.5)
                pool._validate_idle = 0.01
                time.sleep(0.05)

                fresh = server.get_db()
                self.assertIsNot(fresh.raw_conn, stale_raw,
                                 "restart #%d reused a dead connection" % (attempt + 1))
                cur = fresh.cursor(); cur.execute("SELECT 1")
                self.assertEqual(list(cur.fetchone())[0], 1)
                fresh.close()
                self.assertEqual(pool.size, 1)

    def test_concurrent_requests_are_correct_and_bounded(self):
        errors = []
        with patch.object(server, "is_production_env", return_value=True):
            def worker():
                try:
                    for _ in range(15):
                        c = server.get_db()
                        try:
                            cur = c.cursor(); cur.execute("SELECT 1")
                            if list(cur.fetchone())[0] != 1:
                                raise AssertionError("bad result")
                        finally:
                            server._release_checked_out_pooled_connections()
                            c.close()
                except Exception as exc:  # pragma: no cover
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads: t.start()
            for t in threads: t.join()
        self.assertEqual([repr(e) for e in errors], [])
        self.assertLessEqual(server._PG_POOL.size, server.DB_POOL_MAX)


class RealPg8000Tests(RealPostgresBase):

    @staticmethod
    def _make_pool(max_size=2, validate_idle=0.0):
        import pg8000.dbapi

        def create():
            return pg8000.dbapi.connect(
                user="postgres", password=None, host=None, port=None,
                database="postgres", unix_sock=_SOCKET, ssl_context=None,
            )

        return server.PostgresConnectionPool(
            create_fn=create, max_size=max_size, acquire_timeout=5.0,
            validate_idle_seconds=validate_idle,
        )

    def test_pg8000_connection_is_reused(self):
        pool = self._make_pool()
        try:
            a = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            cur = a.cursor(); cur.execute("SELECT 1")
            self.assertEqual(list(cur.fetchone())[0], 1)
            a.close()
            b = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            self.assertIs(b.raw_conn, a.raw_conn)
            b.close()
            self.assertEqual(pool.size, 1)
        finally:
            pool.close_all()

    def test_pg8000_open_transaction_is_rolled_back_on_release(self):
        pool = self._make_pool()
        try:
            a = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            a.execute("INSERT INTO phase1_probe (id) VALUES (7)")
            self.assertTrue(a.raw_conn._in_transaction)
            a.close()                                   # release must roll back
            b = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            self.assertFalse(b.raw_conn._in_transaction)
            cur = b.cursor(); cur.execute("SELECT count(*) FROM phase1_probe")
            self.assertEqual(list(cur.fetchone())[0], 0)
            b.close()
        finally:
            pool.close_all()

    def test_pg8000_closed_connection_is_discarded_and_replaced(self):
        pool = self._make_pool()
        try:
            a = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            raw_a = a.raw_conn
            a.close()
            raw_a.close()                               # driver-level close while idle
            self.assertIsNone(raw_a._usock)
            b = server.PooledPostgresConnectionWrapper(pool.acquire(), pool)
            self.assertIsNot(b.raw_conn, raw_a)         # stale detected via _usock
            cur = b.cursor(); cur.execute("SELECT 1")
            self.assertEqual(list(cur.fetchone())[0], 1)
            b.close()
            self.assertEqual(pool.size, 1)
        finally:
            pool.close_all()


if __name__ == "__main__":
    unittest.main()
