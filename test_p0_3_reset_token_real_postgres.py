#!/usr/bin/env python3
"""P0-3 regression: concurrent reset-token redemption against real PostgreSQL.

This module exercises the real ``/api/auth/reset-password`` handler and the
application's real PostgreSQL connection pool. It creates its own disposable
PostgreSQL cluster through the optional ``pgserver`` package, seeds only the
tables needed by the reset route, and synchronizes two handler invocations so
both have selected and HMAC-verified the same valid token before either can run
the atomic DELETE claim.

The module skips explicitly when ``pgserver`` or a driver is unavailable; a
skip is not evidence that the concurrency behaviour passed. It never falls back
to SQLite: the test process uses the production environment and asserts that the
route obtained a pooled PostgreSQL connection.

Isolation / cleanup
-------------------
The cluster lives in a unique ``mkdtemp()`` directory with
``cleanup_mode="delete"``. Cleanup is registered before PostgreSQL starts, so
the postmaster and directory are removed even when setup or an assertion fails.
No shared or production database is read or modified.

Run with:  python -m unittest test_p0_3_reset_token_real_postgres
"""

import io
import json
import os
import secrets
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import server


STRONG_SESSION_SECRET = secrets.token_hex(32)
TEST_EMAIL = "p0-3-reset@example.test"
TEST_HANDLE = "p03reset"
INITIAL_PASSWORD = "InitialResetPassword123!"
WINNER_PASSWORD = "WinnerResetPassword456!"
LOSER_PASSWORD = "LoserResetPassword789!"
REPLAY_PASSWORD = "ReplayResetPassword012!"

_TMP_BASE = None
_PGDATA = None
_PG = None
_PG_ERROR = None
_PG_VERSION = None
_RESTORE_STATE = None


def _pg_dsn():
    """DSN for this module's disposable cluster, derived from its socket info."""
    info = _PG.get_postmaster_info()
    return "postgresql://postgres:@/postgres?host=%s&port=%s" % (
        info.socket_dir,
        info.port,
    )


def _reset_pool():
    pool = server._PG_POOL
    if pool is not None:
        try:
            pool.close_all()
        except Exception:
            pass
    server._PG_POOL = None
    server._PG_POOL_DSN = None
    try:
        server._release_checked_out_pooled_connections()
    except Exception:
        pass


def _cleanup():
    """Restore module globals, close the pool, and delete only our cluster."""
    global _PG, _RESTORE_STATE
    _reset_pool()

    if _RESTORE_STATE is not None:
        database_url, environment, session_secret, env_values = _RESTORE_STATE
        server.DATABASE_URL = database_url
        server.ENVIRONMENT = environment
        server.SESSION_SECRET = session_secret
        for key, value in env_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _RESTORE_STATE = None

    pg, _PG = _PG, None
    if pg is not None:
        try:
            pg.cleanup()
        except Exception:
            pass

    if _TMP_BASE:
        base = os.path.abspath(_TMP_BASE)
        if (
            os.path.isdir(base)
            and os.path.dirname(base) == os.path.realpath(tempfile.gettempdir())
            and os.path.basename(base).startswith("kandid_p03_reset_pg_")
        ):
            shutil.rmtree(base, ignore_errors=True)


def tearDownModule():
    _cleanup()


def setUpModule():
    global _TMP_BASE, _PGDATA, _PG, _PG_ERROR, _PG_VERSION, _RESTORE_STATE

    try:
        import pgserver  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "pgserver not installed: %s" % exc
        raise unittest.SkipTest(_PG_ERROR)

    try:
        import psycopg2  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "psycopg2 not installed: %s" % exc
        raise unittest.SkipTest(_PG_ERROR)

    try:
        _TMP_BASE = tempfile.mkdtemp(prefix="kandid_p03_reset_pg_")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise unittest.SkipTest("could not create a temp directory: %r" % exc)
    _PGDATA = os.path.join(_TMP_BASE, "data")

    # Registered before PostgreSQL or server state can fail, so cleanup always
    # runs and never touches an instance this module did not start.
    unittest.addModuleCleanup(_cleanup)

    try:
        import pgserver
        import psycopg2

        _PG = pgserver.get_server(_PGDATA, cleanup_mode="delete")
        _PG.ensure_postgres_running()
        conn = psycopg2.connect(_pg_dsn())
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW server_version")
            _PG_VERSION = cursor.fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "could not start an isolated disposable PostgreSQL: %r" % exc
        raise unittest.SkipTest(_PG_ERROR)

    _RESTORE_STATE = (
        server.DATABASE_URL,
        server.ENVIRONMENT,
        server.SESSION_SECRET,
        {
            "ENVIRONMENT": os.environ.get("ENVIRONMENT"),
            "SESSION_SECRET": os.environ.get("SESSION_SECRET"),
        },
    )

    # The reset route must take the required-secret path. Production also makes
    # get_db() fail closed instead of silently falling back to SQLite.
    server.DATABASE_URL = _pg_dsn()
    server.ENVIRONMENT = "production"
    server.SESSION_SECRET = STRONG_SESSION_SECRET
    os.environ["ENVIRONMENT"] = "production"
    os.environ["SESSION_SECRET"] = STRONG_SESSION_SECRET
    _reset_pool()

    assert server.is_production_env(), "test must run on the production DB path"
    assert server.is_session_secret_required(), "test must require a session secret"
    assert server.SESSION_SECRET == STRONG_SESSION_SECRET


class _ResetPasswordRequest(server.KandidHandler):
    """Real KandidHandler route invocation with a captured JSON response.

    Only the HTTP transport and response writer are replaced. The request still
    runs KandidHandler.do_POST for /api/auth/reset-password, including rate
    limiting, token lookup, HMAC verification, the atomic DELETE claim, password
    update, session replacement, and commit.
    """

    def __init__(self, payload, client_ip):
        raw = json.dumps(payload).encode("utf-8")
        self.path = "/api/auth/reset-password"
        self.headers = {
            "Content-Length": str(len(raw)),
            "Content-Type": "application/json",
        }
        self.rfile = io.BytesIO(raw)
        self.client_address = (client_ip, 12345)
        self.response = None
        self.close_connection = False

    def send_json(self, status, data):
        self.response = {"status": status, "body": data}
        return data


class ResetTokenRealPostgresTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        _reset_pool()
        import psycopg2

        conn = psycopg2.connect(_pg_dsn())
        try:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS sessions")
            cursor.execute("DROP TABLE IF EXISTS password_resets")
            cursor.execute("DROP TABLE IF EXISTS users")
            cursor.execute(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    handle TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    avatar_url TEXT DEFAULT '',
                    campus TEXT DEFAULT 'Test Campus',
                    streak_count INTEGER DEFAULT 0,
                    email_verified INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE password_resets (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            password_hash, salt = server.hash_password(INITIAL_PASSWORD)
            cursor.execute(
                """
                INSERT INTO users (
                    id, email, handle, name, password_hash, salt, email_verified
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "user_p0_3_reset",
                    TEST_EMAIL,
                    TEST_HANDLE,
                    "P0-3 Reset",
                    password_hash,
                    salt,
                    0,
                ),
            )

            self.raw_token = "prt_" + secrets.token_hex(24)
            self.token_verifier = server.hash_reset_token(self.raw_token)
            self.assertNotEqual(self.token_verifier, self.raw_token)
            self.assertTrue(
                self.token_verifier.startswith("v1$hmac_sha256$"),
                self.token_verifier,
            )
            expires_at = (
                server.datetime.now() + server.timedelta(minutes=10)
            ).isoformat()
            cursor.execute(
                """
                INSERT INTO password_resets (id, email, token, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "pr_p0_3_concurrent",
                    TEST_EMAIL,
                    self.token_verifier,
                    expires_at,
                    server.datetime.now().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        _reset_pool()
        import psycopg2

        try:
            conn = psycopg2.connect(_pg_dsn())
            try:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS sessions")
                cursor.execute("DROP TABLE IF EXISTS password_resets")
                cursor.execute("DROP TABLE IF EXISTS users")
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def _invoke(self, password, client_ip="198.51.100.23"):
        request = _ResetPasswordRequest(
            {"reset_token": self.raw_token, "new_password": password},
            client_ip,
        )
        request.do_POST()
        self.assertIsNotNone(request.response, "handler produced no response")
        return request.response

    def _user_state(self):
        import psycopg2

        conn = psycopg2.connect(_pg_dsn())
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_hash, salt, email_verified FROM users WHERE id = %s",
                ("user_p0_3_reset",),
            )
            return cursor.fetchone()
        finally:
            conn.close()

    def _reset_count(self):
        import psycopg2

        conn = psycopg2.connect(_pg_dsn())
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM password_resets WHERE id = %s",
                ("pr_p0_3_concurrent",),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def _session_tokens(self):
        import psycopg2

        conn = psycopg2.connect(_pg_dsn())
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT token FROM sessions WHERE user_id = %s ORDER BY token",
                ("user_p0_3_reset",),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def test_concurrent_redemption_claims_the_token_exactly_once(self):
        barrier = threading.Barrier(2, timeout=15)
        verified = []
        original_verify = server.verify_reset_token_hash

        def synchronized_verify(raw_token, stored_verifier):
            result = original_verify(raw_token, stored_verifier)
            verified.append(result)
            # Both requests have now selected the same unexpired row and passed
            # HMAC verification. Release them together into the real DELETE.
            barrier.wait()
            return result

        results = []
        errors = []
        start = threading.Barrier(3, timeout=10)

        def redeem(password, label):
            try:
                start.wait()
                response = self._invoke(password, client_ip="198.51.100.23")
                results.append({"label": label, "password": password, **response})
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append((label, repr(exc)))
            finally:
                # The direct handler invocation bypasses handle_one_request's
                # boundary release, so release this thread's pool slot here.
                try:
                    server._release_checked_out_pooled_connections()
                except Exception:
                    pass

        threads = [
            threading.Thread(target=redeem, args=(WINNER_PASSWORD, "request-a")),
            threading.Thread(target=redeem, args=(LOSER_PASSWORD, "request-b")),
        ]
        with patch.object(
            server,
            "verify_reset_token_hash",
            side_effect=synchronized_verify,
        ):
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join(timeout=30)

        self.assertEqual(
            [thread.is_alive() for thread in threads],
            [False, False],
            "a concurrent reset request did not finish",
        )
        self.assertEqual(errors, [], "reset handler raised: %r" % (errors,))
        self.assertEqual(verified, [True, True], "both requests must HMAC-verify")
        self.assertEqual(
            sorted(result["status"] for result in results),
            [200, 400],
            results,
        )

        winner = next(result for result in results if result["status"] == 200)
        loser = next(result for result in results if result["status"] == 400)
        self.assertTrue(winner["body"].get("success"), winner)
        self.assertEqual(
            loser["body"].get("error_code"),
            "INVALID_RESET_TOKEN",
            loser,
        )

        # The claim is committed, so the token record is gone permanently.
        self.assertEqual(self._reset_count(), 0)

        password_hash, salt, email_verified = self._user_state()
        self.assertEqual(email_verified, 1)
        self.assertTrue(
            server.verify_password(winner["password"], salt, password_hash),
            "the winning request's password must be persisted",
        )
        self.assertFalse(
            server.verify_password(loser["password"], salt, password_hash),
            "the rejected request must not change the password",
        )
        session_tokens = self._session_tokens()
        self.assertEqual(session_tokens, [winner["body"]["token"]])

        # Confirm the route used the real PostgreSQL pool and driver.
        self.assertIsNotNone(server._PG_POOL, "no PostgreSQL pool was created")
        self.assertIsNotNone(server._PG_POOL_DSN, "no PostgreSQL DSN was pooled")
        self.assertGreaterEqual(server._PG_POOL.size, 2)
        conn = server.get_db()
        try:
            self.assertIsInstance(conn, server.PooledPostgresConnectionWrapper)
            driver_module = conn.raw_conn.__class__.__module__
            self.assertTrue(
                driver_module.startswith("psycopg2"),
                "expected psycopg2 driver, got %s" % driver_module,
            )
            cursor = conn.execute(
                "SELECT current_setting('server_version') AS version"
            )
            row = cursor.fetchone()
            self.assertEqual(row["version"], _PG_VERSION)
        finally:
            conn.close()

        # A later redemption of the same token is rejected too.
        replay = self._invoke(REPLAY_PASSWORD, client_ip="198.51.100.24")
        self.assertEqual(replay["status"], 400, replay)
        self.assertEqual(
            replay["body"].get("error_code"),
            "INVALID_RESET_TOKEN",
            replay,
        )
        password_hash, salt, _email_verified = self._user_state()
        self.assertTrue(
            server.verify_password(winner["password"], salt, password_hash),
            "a replay must not change the already-reset password",
        )
        self.assertFalse(server.verify_password(REPLAY_PASSWORD, salt, password_hash))
        self.assertEqual(self._reset_count(), 0)
        self.assertEqual(self._session_tokens(), [winner["body"]["token"]])


if __name__ == "__main__":
    unittest.main()
