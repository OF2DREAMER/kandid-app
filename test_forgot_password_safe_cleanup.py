import unittest
import json
import os
import sys
import tempfile
import sqlite3
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server

# D4-07: pristine globals captured at import time and restored after cleanup
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


class TestForgotPasswordSafeCleanup(unittest.TestCase):
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

        # Schema matches real database: email_otps exists, NO otps table exists
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

        # Insert test user
        self.test_password = "InitialPassword123!"
        self.pw_hash, self.salt = server.hash_password(self.test_password)
        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt, onboarding_status)
            VALUES ('u_fp_user', 'fp_user@example.com', 'fp_handle', 'Forgot Password User', ?, ?, 'active')
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
        if getattr(server, "_last_otp_dispatch_thread", None) and server._last_otp_dispatch_thread.is_alive():
            server._last_otp_dispatch_thread.join(timeout=2.0)
        return h.sent_response

    def test_01_production_missing_email_provider_fails_controlled_503(self):
        """
        Verify that in production without BREVO_API_KEY:
        - generate_secure_otp returns controlled 503 EMAIL_PROVIDER_UNCONFIGURED (never 500)
        - never raises SQLite 'no such table: otps'
        - email_otps record is marked is_used = 1 so no unusable OTP is left active
        - /api/auth/forgot-password returns uniform HTTP 200 generic response to prevent account enumeration
        """
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = ""
        server.RESEND_API_KEY = ""

        # Internal OTP generation returns controlled 503
        gen_res = server.generate_secure_otp("fp_user@example.com")
        self.assertEqual(gen_res.get("status"), 503, "generate_secure_otp must return 503 when email service is unconfigured")
        self.assertFalse(gen_res.get("success"))
        self.assertEqual(gen_res.get("error_code"), "EMAIL_PROVIDER_UNCONFIGURED")
        self.assertEqual(gen_res.get("delivery_status"), "unconfigured")

        # Endpoint returns uniform 200 to prevent account enumeration
        resp = self._call_post("/api/auth/forgot-password", {"identifier": "fp_user@example.com"})
        self.assertEqual(resp.get("status"), 200, "Endpoint must return HTTP 200 generic response")
        body = resp.get("body", {})
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("delivery_status"), "accepted")
        server.drain_otp_dispatch_queue(timeout=2.0)

        # Verify database state: no active OTP exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT is_used FROM email_otps WHERE email = 'fp_user@example.com'")
        rows = cursor.fetchall()
        self.assertTrue(len(rows) >= 1, "An OTP record was created")
        for row in rows:
            self.assertEqual(row[0], 1, "The unusable OTP must be marked is_used = 1 upon dispatch failure")
        conn.close()

    def test_02_production_delivery_failure_safe_invalidation(self):
        """
        Verify that if email provider fails with auth error in production:
        - generate_secure_otp returns controlled 503 BREVO_AUTH_FAILURE
        - no crash on legacy otps table
        - OTP record is invalidated (is_used = 1)
        - /api/auth/forgot-password returns uniform HTTP 200 generic response
        """
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = "dummy_key"

        with patch("server.send_email_resend") as mock_send:
            mock_send.return_value = {
                "success": False,
                "error_code": "BREVO_AUTH_FAILURE",
                "error": "Authentication failed with email provider",
                "status_code": 503,
                "delivery_status": "rejected"
            }

            gen_res = server.generate_secure_otp("fp_user@example.com")
            self.assertEqual(gen_res.get("status"), 503)
            self.assertFalse(gen_res.get("success"))
            self.assertEqual(gen_res.get("error_code"), "BREVO_AUTH_FAILURE")

            resp = self._call_post("/api/auth/forgot-password", {"identifier": "fp_handle"})
            self.assertEqual(resp.get("status"), 200)
            self.assertTrue(resp["body"].get("success"))
            server.drain_otp_dispatch_queue(timeout=2.0)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT is_used FROM email_otps WHERE email = 'fp_user@example.com'")
            rows = cursor.fetchall()
            for r in rows:
                self.assertEqual(r[0], 1, "Failed OTP dispatch must invalidate email_otps record")
            conn.close()

    def test_03_successful_email_provider_flow(self):
        """
        Verify that when email delivery succeeds:
        - returns HTTP 200 with generic response (no raw or masked email disclosure)
        - email_otps record is active (is_used = 0)
        """
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = "valid_key"

        with patch("server.send_email_resend") as mock_send:
            mock_send.return_value = {
                "success": True,
                "id": "msg_999",
                "status_code": 200,
                "delivery_status": "accepted"
            }

            resp = self._call_post("/api/auth/forgot-password", {"identifier": "fp_user@example.com"})

            self.assertEqual(resp.get("status"), 200)
            self.assertTrue(resp["body"].get("success"))
            self.assertEqual(resp["body"].get("delivery_status"), "accepted")
            self.assertNotIn("masked_email", resp["body"])
            self.assertNotIn("email_id", resp["body"])
            self.assertNotIn("email", resp["body"])
            server.drain_otp_dispatch_queue(timeout=2.0)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT is_used, attempts FROM email_otps WHERE email = 'fp_user@example.com'")
            row = cursor.fetchone()
            self.assertEqual(row[0], 0, "Delivered OTP must remain active (is_used = 0)")
            self.assertEqual(row[1], 0, "Attempts should start at 0")
            conn.close()

    def test_04_end_to_end_reset_password_flow(self):
        """
        Verify that the full Forgot Password -> Reset Password flow works:
        1. Request OTP via /api/auth/forgot-password
        2. Extract valid OTP
        3. Submit new password via /api/auth/reset-password
        4. Verify password hash updated and old sessions invalidated
        """
        captured_otp = []

        def mock_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                captured_otp.append(m.group(0))
            return {"success": True, "id": "msg_123", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=mock_dispatch):
            # 1. Request OTP
            resp1 = self._call_post("/api/auth/forgot-password", {"identifier": "fp_handle"})
            self.assertEqual(resp1.get("status"), 200)
            server.drain_otp_dispatch_queue(timeout=2.0)
            self.assertEqual(len(captured_otp), 1)
            valid_otp = captured_otp[0]

            # Seed an active session for the user
            conn = sqlite3.connect(self.db_path)
            conn.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES ('old_sess', 'u_fp_user', 'old_token', '2099-01-01')")
            conn.commit()
            conn.close()

            # 2. Reset password with valid OTP
            new_password = "BrandNewSecurePassword456!"
            resp2 = self._call_post("/api/auth/reset-password", {
                "identifier": "fp_handle",
                "otp": valid_otp,
                "password": new_password
            })

            self.assertEqual(resp2.get("status"), 200)
            self.assertTrue(resp2["body"].get("success"))
            self.assertTrue("token" in resp2["body"])

            # 3. Verify user password was changed in DB
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash, salt FROM users WHERE id = 'u_fp_user'")
            user_row = cursor.fetchone()
            self.assertTrue(server.verify_password(new_password, user_row["salt"], user_row["password_hash"]))

            # Verify old session was deleted
            cursor.execute("SELECT * FROM sessions WHERE token = 'old_token'")
            self.assertIsNone(cursor.fetchone(), "Old session must be revoked")

            # Verify OTP is now used
            cursor.execute("SELECT is_used FROM email_otps WHERE email = 'fp_user@example.com'")
            self.assertEqual(cursor.fetchone()[0], 1, "Used OTP must be marked is_used = 1")
            conn.close()


if __name__ == "__main__":
    unittest.main()
