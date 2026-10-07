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

_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL

def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL

class TestGoogleLoginFlowSurgical(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
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
                avatar_url TEXT,
                avatar_letter TEXT DEFAULT 'K',
                bio TEXT,
                campus TEXT,
                campus_id TEXT,
                location_city TEXT,
                streak_count INTEGER DEFAULT 1,
                onboarding_status TEXT DEFAULT 'active',
                password_hash TEXT,
                salt TEXT,
                created_at TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_subject TEXT NOT NULL,
                email TEXT,
                last_login_at TEXT
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
            CREATE TABLE IF NOT EXISTS onboarding_sessions (
                id TEXT PRIMARY KEY,
                provider TEXT,
                provider_subject TEXT,
                email TEXT,
                google_name TEXT,
                google_avatar TEXT,
                step INTEGER,
                chosen_handle TEXT,
                chosen_campus_id TEXT,
                chosen_campus_name TEXT,
                chosen_city TEXT,
                expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_existing', 'existing@example.com', 'existinguser', 'Existing User')")
        cursor.execute("INSERT INTO auth_identities (id, user_id, provider, provider_subject, email) VALUES ('auth_1', 'user_existing', 'google', 'gid_12345', 'existing@example.com')")
        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _call_get(self, path):
        handler = MagicMock()
        handler.path = path
        handler.query = {}
        handler.headers = {}
        sent_response = {}

        def mock_send_json(status_code, response_dict):
            sent_response["status"] = status_code
            sent_response["body"] = response_dict
            return response_dict

        handler.send_json = mock_send_json
        req_class = getattr(server, "KandidHTTPRequestHandler", None) or getattr(server, "KandidHandler")
        req_class.do_GET(handler)
        return sent_response

    def _call_post(self, path, body):
        body_bytes = json.dumps(body).encode("utf-8")
        handler = MagicMock()
        handler.path = path
        handler.headers = {"Content-Length": str(len(body_bytes))}
        handler.read_json_body.return_value = body

        sent_response = {}
        def mock_send_json(status_code, response_dict):
            sent_response["status"] = status_code
            sent_response["body"] = response_dict
            return response_dict

        handler.send_json = mock_send_json
        req_class = getattr(server, "KandidHTTPRequestHandler", None) or getattr(server, "KandidHandler")
        req_class.do_POST(handler)
        return sent_response

    # 1. Verification of GIS Script Import & Fake Form Removal in Frontend Files
    def test_frontend_gis_integration_and_fake_form_removal(self):
        with open(os.path.join(PROJECT_ROOT, "index.html"), "r") as f:
            html = f.read()
        with open(os.path.join(PROJECT_ROOT, "app_core.js"), "r") as f:
            js = f.read()

        # Check 1: Google Identity Services client script imported in index.html
        self.assertIn("https://accounts.google.com/gsi/client", html)

        # Check 2: Continue with Google button wired to loginWithGoogle()
        self.assertIn("loginWithGoogle()", html)

        # Check 3: Fake manual form elements (customGoogleEmail, submitCustomGoogleAccount) removed
        self.assertNotIn("customGoogleEmail", html)
        self.assertNotIn("submitCustomGoogleAccount", js)

        # Check 4: Real GIS handler and container present
        self.assertIn("handleGoogleCredentialResponse", js)
        self.assertIn("googleSignInBtnContainer", html)

    # 2. GET /api/auth/google/config Endpoint Test
    def test_google_config_endpoint(self):
        with patch.object(server, "GOOGLE_CLIENT_ID", "test-client-id-xyz.apps.googleusercontent.com"):
            sent = self._call_get("/api/auth/google/config")
            self.assertEqual(sent["status"], 200)
            self.assertTrue(sent["body"]["success"])
            self.assertEqual(sent["body"]["client_id"], "test-client-id-xyz.apps.googleusercontent.com")
            self.assertTrue(sent["body"]["configured"])

    # 3. Missing Credential Rejection Test
    def test_missing_google_credential_rejected(self):
        sent = self._call_post("/api/auth/google", {})
        self.assertEqual(sent["status"], 401)
        self.assertFalse(sent["body"]["success"])
        self.assertEqual(sent["body"]["error_code"], "MISSING_TOKEN")

    # 4. Invalid Token Rejection Test
    def test_invalid_google_token_rejected(self):
        with patch.object(server, "GOOGLE_CLIENT_ID", "valid_client_id"):
            with patch.object(server, "verify_google_id_token", return_value=None):
                sent = self._call_post("/api/auth/google", {"id_token": "invalid_fake_token_999"})
                self.assertEqual(sent["status"], 401)
                self.assertFalse(sent["body"]["success"])
                self.assertEqual(sent["body"]["error_code"], "INVALID_TOKEN")

    # 5. Verified Active User Login Test
    def test_verified_google_login_existing_user(self):
        mock_claims = {
            "sub": "gid_12345",
            "email": "existing@example.com",
            "name": "Existing User",
            "picture": "https://lh3.googleusercontent.com/a/photo.png"
        }

        with patch.object(server, "GOOGLE_CLIENT_ID", "valid_client_id"):
            with patch.object(server, "verify_google_id_token", return_value=mock_claims):
                sent = self._call_post("/api/auth/google", {"credential": "valid_signed_google_id_token"})
                self.assertEqual(sent["status"], 200)
                self.assertTrue(sent["body"]["success"])
                self.assertEqual(sent["body"]["status"], "ACTIVE_USER")
                self.assertIn("token", sent["body"])
                self.assertEqual(sent["body"]["user"]["handle"], "existinguser")

    # 6. Verified New User Login Onboarding Flow Test
    def test_verified_google_login_new_user_onboarding(self):
        mock_claims = {
            "sub": "gid_new_999",
            "email": "newuser@example.com",
            "name": "New Person",
            "picture": "https://lh3.googleusercontent.com/a/new.png"
        }

        with patch.object(server, "GOOGLE_CLIENT_ID", "valid_client_id"):
            with patch.object(server, "verify_google_id_token", return_value=mock_claims):
                sent = self._call_post("/api/auth/google", {"id_token": "valid_signed_new_user_token"})
                self.assertEqual(sent["status"], 200)
                self.assertTrue(sent["body"]["success"])
                self.assertEqual(sent["body"]["status"], "NEW_ONBOARDING")
                self.assertIn("session_id", sent["body"])
                self.assertEqual(sent["body"]["google_profile"]["email"], "newuser@example.com")

if __name__ == "__main__":
    unittest.main()
