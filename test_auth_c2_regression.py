import unittest
import json
import os
import sys
import tempfile
import sqlite3
from unittest.mock import MagicMock

# Add project root to sys.path
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


class TestAuthC2Regression(unittest.TestCase):
    def setUp(self):
        # Create temporary isolated database
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
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL
            );
        """)

        # Seed CEO user u_1237b86d with a specific initial password
        self.ceo_id = "u_1237b86d"
        self.ceo_initial_pw = "OriginalCeoSecretPw123!"
        self.ceo_hash, self.ceo_salt = server.hash_password(self.ceo_initial_pw)

        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt)
            VALUES (?, 'ceo@kandid.app', 'ceo_primary', 'Primary CEO', ?, ?)
        """, (self.ceo_id, self.ceo_hash, self.ceo_salt))

        # Seed normal user
        self.normal_pw = "NormalUserSecretPw123!"
        self.normal_hash, self.normal_salt = server.hash_password(self.normal_pw)
        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt)
            VALUES ('u_normal_123', 'normal@example.com', 'normal_user', 'Normal User', ?, ?)
        """, (self.normal_hash, self.normal_salt))

        # Seed another user with handle 'ceo'
        self.other_ceo_pw = "OtherCeoSecretPw456!"
        self.other_ceo_hash, self.other_ceo_salt = server.hash_password(self.other_ceo_pw)
        cursor.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt)
            VALUES ('u_other_ceo', 'other_ceo@example.com', 'ceo', 'Other CEO', ?, ?)
        """, (self.other_ceo_hash, self.other_ceo_salt))

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _call_login(self, body):
        class DummyHandler(server.KandidHandler):
            def __init__(self, req_body):
                self.path = "/api/auth/login"
                self.headers = {"Content-Length": str(len(json.dumps(req_body)))}
                import io
                self.rfile = io.BytesIO(json.dumps(req_body).encode("utf-8"))
                self.sent_response = {}

            def send_json(self, status_code, response_dict):
                self.sent_response["status"] = status_code
                self.sent_response["body"] = response_dict
                return response_dict

        h = DummyHandler(body)
        h.do_POST()
        return h.sent_response

    def test_A_ceo_password_hash_and_salt_remain_unchanged(self):
        """Verify that attempting login with handle 'ceo' or 'ceo_1' NEVER overwrites CEO password hash/salt."""
        self._call_login({"identifier": "ceo", "password": "AttackerOverwritingPassword123!"})

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM users WHERE id = ?", (self.ceo_id,))
        ceo_row = dict(cursor.fetchone())
        conn.close()

        self.assertEqual(ceo_row["password_hash"], self.ceo_hash)
        self.assertEqual(ceo_row["salt"], self.ceo_salt)

    def test_B_login_cannot_substitute_another_account_with_ceo_account(self):
        """Verify that logging in as 'ceo' using other_ceo's password does NOT grant a session for u_1237b86d."""
        resp = self._call_login({"identifier": "ceo", "password": self.other_ceo_pw})
        if resp.get("status") == 200:
            user_id_logged_in = resp["body"]["user"]["id"]
            self.assertNotEqual(user_id_logged_in, self.ceo_id)

    def test_C_correct_credentials_authenticate_only_matching_account(self):
        """Verify normal user login returns session for normal user ID."""
        resp = self._call_login({"identifier": "normal_user", "password": self.normal_pw})
        self.assertEqual(resp.get("status"), 200)
        self.assertEqual(resp["body"]["user"]["id"], "u_normal_123")

    def test_D_wrong_credentials_cannot_produce_ceo_session(self):
        """Verify wrong password for CEO account fails with 401."""
        resp = self._call_login({"identifier": "ceo_primary", "password": "WrongPassword123!"})
        self.assertEqual(resp.get("status"), 401)

    def test_E_legitimate_ceo_login_with_correct_password_works(self):
        """Verify CEO user can log in with correct CEO password."""
        resp = self._call_login({"identifier": "ceo_primary", "password": self.ceo_initial_pw})
        self.assertEqual(resp.get("status"), 200)
        self.assertEqual(resp["body"]["user"]["id"], self.ceo_id)

if __name__ == "__main__":
    unittest.main()
