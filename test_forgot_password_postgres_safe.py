import unittest
import json
import os
import sys
import tempfile
import sqlite3
import threading
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server

# D4-07: Pristine globals capture & restore
_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL
_ORIGINAL_ENVIRONMENT = server.ENVIRONMENT
_ORIGINAL_BREVO_API_KEY = server.BREVO_API_KEY
_ORIGINAL_RESEND_API_KEY = server.RESEND_API_KEY


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL
    server.ENVIRONMENT = _ORIGINAL_ENVIRONMENT
    server.BREVO_API_KEY = _ORIGINAL_BREVO_API_KEY
    server.RESEND_API_KEY = _ORIGINAL_RESEND_API_KEY


class PostgresTransactionSimulationError(Exception):
    """Raised when an operation is attempted in an aborted PostgreSQL transaction."""
    pass


class PostgresSimulatedCursor:
    """
    Simulates PostgreSQL / psycopg2 transaction behavior:
    Any SQL error on a statement puts the transaction in an aborted state.
    Subsequent commands fail with InFailedSqlTransaction until rollback() is called.
    """
    def __init__(self, raw_conn, tx_state):
        self.raw_conn = raw_conn
        self.raw_cur = raw_conn.cursor()
        self.tx_state = tx_state  # dict with 'aborted': bool

    def execute(self, sql, params=None):
        if self.tx_state["aborted"]:
            raise PostgresTransactionSimulationError(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        # Intercept any query targeting 'otps' table (which does not exist in Postgres)
        normalized = sql.lower()
        if " otps " in normalized or normalized.startswith("update otps") or normalized.startswith("insert into otps"):
            self.tx_state["aborted"] = True
            raise Exception('relation "otps" does not exist')

        try:
            if params is None:
                return self.raw_cur.execute(sql)
            return self.raw_cur.execute(sql, params)
        except Exception:
            self.tx_state["aborted"] = True
            raise

    def fetchone(self):
        return self.raw_cur.fetchone()

    def fetchall(self):
        return self.raw_cur.fetchall()

    @property
    def rowcount(self):
        return self.raw_cur.rowcount


class PostgresSimulatedConnection:
    """Simulates a psycopg2 Postgres connection with transaction lifecycle."""
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn
        self.tx_state = {"aborted": False}

    def cursor(self):
        return PostgresSimulatedCursor(self.raw_conn, self.tx_state)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        if self.tx_state["aborted"]:
            raise PostgresTransactionSimulationError(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        self.raw_conn.commit()

    def rollback(self):
        self.tx_state["aborted"] = False
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()


class TestForgotPasswordPostgresSafe(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.addCleanup(_restore_server_globals)
        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""
        with server.rate_limiter.lock:
            server.rate_limiter.buckets.clear()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Database schema has email_otps only (no otps table)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                handle TEXT UNIQUE,
                name TEXT,
                email_verified INTEGER DEFAULT 0,
                password_hash TEXT,
                salt TEXT,
                streak_count INTEGER DEFAULT 1,
                onboarding_status TEXT DEFAULT 'active'
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_otps (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                otp_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 5,
                expires_at TEXT NOT NULL,
                is_used INTEGER DEFAULT 0,
                ip_address TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Seed test users
        self.test_pw = "SecureUserPassword123!"
        self.pw_hash, self.salt = server.hash_password(self.test_pw)
        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt, onboarding_status)
            VALUES ('u_valid', 'user@example.com', 'validuser', 'Valid User', ?, ?, 'active')
        """, (self.pw_hash, self.salt))

        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt, onboarding_status)
            VALUES ('u_no_email', '', 'noemailuser', 'No Email User', ?, ?, 'active')
        """, (self.pw_hash, self.salt))

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _call_post(self, path, body):
        class DummyHandler(server.KandidHandler):
            def __init__(self, req_path, req_body):
                self.path = req_path
                self.headers = {"Content-Length": str(len(json.dumps(req_body)))}
                import io
                self.rfile = io.BytesIO(json.dumps(req_body).encode("utf-8"))
                self.sent_response = {}
                self.client_address = ("127.0.0.1", 12345)

            def send_json(self, status_code, response_dict):
                self.sent_response["status"] = status_code
                self.sent_response["body"] = response_dict
                return response_dict

        h = DummyHandler(path, body)
        h.do_POST()
        return h.sent_response

    # =========================================================================
    # PART A & B: LEGACY OTP REMOVAL & POSTGRES TRANSACTION SAFETY
    # =========================================================================

    def test_A_no_sql_issued_against_legacy_otps_table(self):
        """Verify that OTP generation issues ZERO SQL statements against the legacy 'otps' table."""
        executed_sqls = []

        class InterceptingCursor:
            def __init__(self, real_cur):
                self.cur = real_cur
            def execute(self, sql, params=None):
                executed_sqls.append(sql.lower())
                if params is not None:
                    return self.cur.execute(sql, params)
                return self.cur.execute(sql)
            def fetchone(self):
                return self.cur.fetchone()
            def fetchall(self):
                return self.cur.fetchall()
            @property
            def rowcount(self):
                return self.cur.rowcount

        class InterceptingConn:
            def __init__(self, db_path):
                self.conn = sqlite3.connect(db_path)
                self.conn.row_factory = sqlite3.Row
            def cursor(self):
                return InterceptingCursor(self.conn.cursor())
            def execute(self, sql, params=None):
                cur = self.cursor()
                return cur.execute(sql, params)
            def commit(self):
                self.conn.commit()
            def close(self):
                self.conn.close()

        with patch("server.get_db", side_effect=lambda: InterceptingConn(self.db_path)), \
             patch("server.send_email_resend", return_value={"success": True, "id": "msg_1", "status_code": 200, "delivery_status": "accepted"}):
            resp = server.generate_secure_otp("user@example.com")
            self.assertTrue(resp["success"])

        for stmt in executed_sqls:
            self.assertNotIn(" otps ", stmt, f"Legacy otps table referenced: {stmt}")
            self.assertFalse(stmt.startswith("update otps"), f"Legacy otps update: {stmt}")
            self.assertFalse(stmt.startswith("insert into otps"), f"Legacy otps insert: {stmt}")

    def test_B_postgres_transaction_safety_during_generation_and_cleanup(self):
        """
        Verify that under simulated PostgreSQL transaction semantics:
        1. OTP generation executes without entering an aborted transaction.
        2. Delivery failure cleanup invalidates email_otps and commits cleanly without aborted transaction.
        """
        def postgres_mock_get_db():
            raw_c = sqlite3.connect(self.db_path)
            raw_c.row_factory = sqlite3.Row
            return PostgresSimulatedConnection(raw_c)

        # 1. Successful generation under Postgres simulation
        with patch("server.get_db", side_effect=postgres_mock_get_db), \
             patch("server.send_email_resend", return_value={"success": True, "id": "msg_pg", "status_code": 200, "delivery_status": "accepted"}):
            res = server.generate_secure_otp("user@example.com")
            self.assertTrue(res["success"])

        # Verify email_otps row was committed
        verify_conn = sqlite3.connect(self.db_path)
        cur = verify_conn.cursor()
        cur.execute("SELECT is_used FROM email_otps WHERE email = 'user@example.com' ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 0, "Delivered OTP must be active in email_otps")

        # 2. Failed delivery cleanup under Postgres simulation
        with patch("server.get_db", side_effect=postgres_mock_get_db), \
             patch("server.send_email_resend", return_value={"success": False, "error_code": "EMAIL_PROVIDER_UNAVAILABLE", "status_code": 503, "delivery_status": "failed"}):
            res_fail = server.generate_secure_otp("user@example.com")
            self.assertFalse(res_fail["success"])
            self.assertEqual(res_fail["status"], 503)

        # Verify that cleanup successfully committed is_used = 1 in email_otps
        cur.execute("SELECT is_used FROM email_otps WHERE email = 'user@example.com' ORDER BY created_at DESC LIMIT 1")
        row_fail = cur.fetchone()
        self.assertIsNotNone(row_fail)
        self.assertEqual(row_fail[0], 1, "Failed delivery must commit is_used = 1 without transaction abort")
        verify_conn.close()

    # =========================================================================
    # PART C: PLAINTEXT OTP PROTECTION
    # =========================================================================

    def test_C_raw_six_digit_otp_never_sent_to_database(self):
        """Verify that the 6-digit numeric OTP code is never passed as a SQL parameter or query string."""
        recorded_params = []
        recorded_sqls = []

        class InterceptingCursor:
            def __init__(self, real_cur):
                self.cur = real_cur
            def execute(self, sql, params=None):
                recorded_sqls.append(sql)
                if params:
                    recorded_params.extend(params)
                    return self.cur.execute(sql, params)
                return self.cur.execute(sql)
            def fetchone(self):
                return self.cur.fetchone()
            def fetchall(self):
                return self.cur.fetchall()
            @property
            def rowcount(self):
                return self.cur.rowcount

        class InterceptingConn:
            def __init__(self, db_path):
                self.conn = sqlite3.connect(db_path)
                self.conn.row_factory = sqlite3.Row
            def cursor(self):
                return InterceptingCursor(self.conn.cursor())
            def execute(self, sql, params=None):
                cur = self.cursor()
                return cur.execute(sql, params)
            def commit(self):
                self.conn.commit()
            def close(self):
                self.conn.close()

        dispatched_otp = []
        def mock_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "msg_c", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.get_db", side_effect=lambda: InterceptingConn(self.db_path)), \
             patch("server.send_email_resend", side_effect=mock_dispatch):
            server.generate_secure_otp("user@example.com")

        self.assertEqual(len(dispatched_otp), 1)
        raw_code = dispatched_otp[0]

        # Assert raw_code NEVER appears in any SQL string or parameter
        for stmt in recorded_sqls:
            self.assertNotIn(raw_code, stmt, f"Raw OTP found in SQL statement: {stmt}")
        for param in recorded_params:
            self.assertNotEqual(str(param), raw_code, f"Raw OTP passed as SQL parameter: {param}")

    # =========================================================================
    # PART D: PROVIDER FAILURE HANDLING (CONTROLLED 503)
    # =========================================================================

    def test_D1_missing_provider_configuration_returns_controlled_503(self):
        """In production without BREVO_API_KEY, generate_secure_otp returns controlled 503 EMAIL_PROVIDER_UNCONFIGURED and endpoint returns uniform 200."""
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = ""
        server.RESEND_API_KEY = ""

        # Internal generation returns controlled 503
        gen_res = server.generate_secure_otp("user@example.com")
        self.assertEqual(gen_res.get("status"), 503)
        self.assertEqual(gen_res.get("error_code"), "EMAIL_PROVIDER_UNCONFIGURED")

        # Endpoint returns uniform 200 to eliminate account enumeration oracle
        resp = self._call_post("/api/auth/forgot-password", {"identifier": "validuser"})
        self.assertEqual(resp.get("status"), 200)
        self.assertTrue(resp["body"].get("success"))

    def test_D2_provider_timeout_and_network_exception_returns_controlled_503(self):
        """Network timeouts and connection errors map to 503 EMAIL_PROVIDER_UNAVAILABLE in generate_secure_otp and 200 in endpoint."""
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = "test_key"

        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            gen_res = server.generate_secure_otp("user@example.com")
            self.assertEqual(gen_res.get("status"), 503)
            self.assertEqual(gen_res.get("error_code"), "EMAIL_PROVIDER_UNAVAILABLE")

            resp = self._call_post("/api/auth/forgot-password", {"identifier": "validuser"})
            self.assertEqual(resp.get("status"), 200)
            self.assertTrue(resp["body"].get("success"))

    def test_D3_provider_upstream_500_maps_to_503(self):
        """Upstream 500 from email provider maps to 503 EMAIL_PROVIDER_UNAVAILABLE in generate_secure_otp and 200 in endpoint."""
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = "test_key"

        with patch("server.send_email_resend", return_value={"success": False, "error_code": "EMAIL_PROVIDER_ERROR", "status_code": 500, "delivery_status": "failed"}):
            gen_res = server.generate_secure_otp("user@example.com")
            self.assertEqual(gen_res.get("status"), 503)
            self.assertEqual(gen_res.get("error_code"), "EMAIL_PROVIDER_UNAVAILABLE")

            resp = self._call_post("/api/auth/forgot-password", {"identifier": "validuser"})
            self.assertEqual(resp.get("status"), 200)
            self.assertTrue(resp["body"].get("success"))

    # =========================================================================
    # PART E: REMOVE RAW EMAIL DISCLOSURE
    # =========================================================================

    def test_E_successful_forgot_password_never_returns_raw_or_masked_email(self):
        """For a valid account, response NEVER discloses raw email, masked_email, or email_id."""
        with patch("server.send_email_resend", return_value={"success": True, "id": "msg_e", "status_code": 200, "delivery_status": "accepted"}):
            resp = self._call_post("/api/auth/forgot-password", {"identifier": "validuser"})

            self.assertEqual(resp.get("status"), 200)
            body = resp.get("body", {})
            self.assertTrue(body.get("success"))
            self.assertNotIn("masked_email", body)
            self.assertNotIn("email_id", body)
            self.assertNotIn("email", body)
            self.assertNotIn("user@example.com", json.dumps(body))

    # =========================================================================
    # PART F: ACCOUNT ENUMERATION HARDENING
    # =========================================================================

    def test_F_account_enumeration_hardened(self):
        """
        Verify that unknown handles, unknown emails, and accounts lacking an email
        all return consistent HTTP 200 generic success responses, disclosing zero existence signal.
        """
        # 1. Unknown handle
        resp_unknown_handle = self._call_post("/api/auth/forgot-password", {"identifier": "completely_unknown_user_999"})
        self.assertEqual(resp_unknown_handle.get("status"), 200)
        self.assertTrue(resp_unknown_handle["body"].get("success"))
        self.assertIn("associated with this handle or email", resp_unknown_handle["body"].get("message", ""))
        self.assertNotIn("ACCOUNT_NOT_FOUND", json.dumps(resp_unknown_handle))

        # 2. Unknown email
        resp_unknown_email = self._call_post("/api/auth/forgot-password", {"identifier": "unknown_email@example.com"})
        self.assertEqual(resp_unknown_email.get("status"), 200)
        self.assertTrue(resp_unknown_email["body"].get("success"))
        self.assertIn("associated with this handle or email", resp_unknown_email["body"].get("message", ""))

        # 3. Known account lacking an email
        resp_no_email = self._call_post("/api/auth/forgot-password", {"identifier": "noemailuser"})
        self.assertEqual(resp_no_email.get("status"), 200)
        self.assertTrue(resp_no_email["body"].get("success"))
        self.assertIn("associated with this handle or email", resp_no_email["body"].get("message", ""))
        self.assertNotIn("INVALID_ACCOUNT_EMAIL", json.dumps(resp_no_email))

    # =========================================================================
    # PART G: OTP CONCURRENCY & ATOMICITY
    # =========================================================================

    def test_G1_two_simultaneous_valid_submissions_only_one_succeeds(self):
        """Two concurrent valid verification requests: exactly one consumes the OTP, the other fails."""
        dispatched_otp = []
        def capture_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "m1", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=capture_dispatch):
            server.generate_secure_otp("user@example.com")

        self.assertEqual(len(dispatched_otp), 1)
        valid_code = dispatched_otp[0]

        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            res = server.verify_secure_otp("user@example.com", valid_code)
            results.append(res)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r.get("success") is True]
        failures = [r for r in results if r.get("success") is False]
        self.assertEqual(len(successes), 1, "Exactly one concurrent valid submission must succeed")
        self.assertEqual(len(failures), 1, "The competing valid submission must fail atomic claim")

    def test_G2_multiple_simultaneous_invalid_submissions_enforces_attempt_limit(self):
        """Concurrent invalid OTP guesses atomically increment attempts and trigger max-attempts invalidation."""
        with patch("server.send_email_resend", return_value={"success": True, "id": "m2", "status_code": 200, "delivery_status": "accepted"}):
            server.generate_secure_otp("user@example.com")

        barrier = threading.Barrier(5)
        results = []

        def worker(idx):
            barrier.wait()
            res = server.verify_secure_otp("user@example.com", f"00000{idx}")
            results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 5 guesses failed
        for r in results:
            self.assertFalse(r.get("success"))

        # Verify DB state: attempts count is exactly 5, is_used is 1
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT attempts, max_attempts, is_used FROM email_otps WHERE email = 'user@example.com' ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], 5, "All 5 concurrent attempts must be counted")
        self.assertEqual(row[2], 1, "OTP must be invalidated after 5 failed attempts")

    def test_G3_consumed_otp_cannot_be_reused(self):
        """Once consumed, an OTP cannot be verified again."""
        dispatched_otp = []
        def capture_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "m3", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=capture_dispatch):
            server.generate_secure_otp("user@example.com")

        self.assertEqual(len(dispatched_otp), 1)
        valid_code = dispatched_otp[0]

        # First verification succeeds
        res1 = server.verify_secure_otp("user@example.com", valid_code)
        self.assertTrue(res1.get("success"))

        # Second verification fails
        res2 = server.verify_secure_otp("user@example.com", valid_code)
        self.assertFalse(res2.get("success"))

    def test_G4_expired_otp_cannot_be_used(self):
        """Expired OTP is rejected and marked is_used = 1."""
        with patch("server.send_email_resend", return_value={"success": True, "id": "m4", "status_code": 200, "delivery_status": "accepted"}):
            server.generate_secure_otp("user@example.com")

        # Manually backdate expires_at
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE email_otps SET expires_at = '2000-01-01T00:00:00' WHERE email = 'user@example.com'")
        conn.commit()
        conn.close()

        res = server.verify_secure_otp("user@example.com", "123456")
        self.assertFalse(res.get("success"))
        self.assertIn("expired", res.get("error", "").lower())

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT is_used FROM email_otps WHERE email = 'user@example.com'")
        self.assertEqual(cur.fetchone()[0], 1, "Expired OTP must be marked is_used = 1")
        conn.close()


if __name__ == "__main__":
    unittest.main()
