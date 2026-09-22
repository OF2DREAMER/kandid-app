import unittest
import json
import os
import sys
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server

# D4-07: pristine globals captured at import time (all test modules are imported
# before any test runs). They are restored after every test so a fixture can
# never leak a temporary/deleted DB path into the rest of the suite.
_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


class TestOTPC3Security(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        # Registered BEFORE mutating the globals, so even a raising setUp or a
        # failing test cannot leave DB_FILE pointing at the deleted temp DB.
        self.addCleanup(_restore_server_globals)
        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                handle TEXT UNIQUE,
                name TEXT,
                email_verified INTEGER DEFAULT 0,
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
        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('u_otp_test', 'otptest@example.com', 'otp_user', 'OTP User')")
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

    @patch("server.send_email_resend")
    def test_01_send_otp_api_does_not_leak_otp_or_dev_otp(self, mock_send_email):
        mock_send_email.return_value = {"success": True, "status_code": 200, "id": "msg_123"}

        resp = self._call_post("/api/auth/send-otp", {"email": "otptest@example.com"})

        self.assertEqual(resp.get("status"), 200)
        body = resp.get("body", {})
        self.assertTrue(body.get("success"))
        self.assertNotIn("dev_otp", body)
        self.assertNotIn("otp", body)
        self.assertNotIn("code", body)

    @patch("server.send_email_resend")
    def test_02_forgot_password_api_does_not_leak_otp_or_dev_otp(self, mock_send_email):
        mock_send_email.return_value = {"success": True, "status_code": 200, "id": "msg_123"}

        resp = self._call_post("/api/auth/forgot-password", {"identifier": "otptest@example.com"})

        self.assertEqual(resp.get("status"), 200)
        body = resp.get("body", {})
        self.assertTrue(body.get("success"))
        self.assertNotIn("dev_otp", body)
        self.assertNotIn("otp", body)
        self.assertNotIn("code", body)

    @patch("server.send_email_resend")
    def test_03_otp_generation_storage_and_verification_workflow(self, mock_send_email):
        captured_otp = []
        def side_effect(email, subject, html, text):
            # Extract OTP from email HTML or text
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                captured_otp.append(m.group(0))
            return {"success": True, "status_code": 200, "id": "msg_456"}

        mock_send_email.side_effect = side_effect

        # 1. Send OTP
        send_res = self._call_post("/api/auth/send-otp", {"email": "otptest@example.com"})
        self.assertEqual(send_res.get("status"), 200)
        self.assertEqual(len(captured_otp), 1)
        actual_otp = captured_otp[0]

        # 2. Verify Wrong OTP fails
        fail_res = self._call_post("/api/auth/verify-otp", {"email": "otptest@example.com", "otp": "000000"})
        self.assertEqual(fail_res.get("status"), 400)
        self.assertFalse(fail_res["body"].get("success"))

        # 3. Verify Correct OTP succeeds
        success_res = self._call_post("/api/auth/verify-otp", {"email": "otptest@example.com", "otp": actual_otp})
        self.assertEqual(success_res.get("status"), 200)
        self.assertTrue(success_res["body"].get("success"))

if __name__ == "__main__":
    unittest.main()
