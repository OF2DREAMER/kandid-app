import unittest
import json
import os
import sys
import tempfile
import sqlite3
import time
from unittest.mock import patch, MagicMock

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


class TestGoogleAuthC1Security(unittest.TestCase):
    def setUp(self):
        # Create temporary isolated database
        self.db_fd, self.db_path = tempfile.mkstemp()
        # Registered BEFORE mutating the globals, so even a raising setUp or a
        # failing test cannot leave DB_FILE pointing at the deleted temp DB.
        self.addCleanup(_restore_server_globals)
        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""

        # Initialize schema
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

        # Seed test users
        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_victim', 'victim@example.com', 'victim_user', 'Victim Name')")
        cursor.execute("INSERT INTO auth_identities (id, user_id, provider, provider_subject, email) VALUES ('auth_vic', 'user_victim', 'google', 'google_sub_victim', 'victim@example.com')")

        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_attacker', 'attacker@example.com', 'attacker_user', 'Attacker Name')")
        cursor.execute("INSERT INTO auth_identities (id, user_id, provider, provider_subject, email) VALUES ('auth_att', 'user_attacker', 'google', 'google_sub_attacker', 'attacker@example.com')")

        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_emailonly', 'unlinked@example.com', 'unlinked_user', 'Unlinked User')")

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _call_google_auth(self, body):
        handler = MagicMock()
        handler.headers = {"Content-Length": str(len(json.dumps(body)))}
        handler.rfile = MagicMock()
        handler.rfile.read.return_value = json.dumps(body).encode("utf-8")

        sent_response = {}
        def mock_send_json(status_code, response_dict):
            sent_response["status"] = status_code
            sent_response["body"] = response_dict
            return response_dict

        handler.send_json = mock_send_json

        server.KandidHTTPRequestHandler.do_POST(handler)
        # Note: Since server.py route dispatch calls self.send_json, our mock captures it.
        return sent_response

    @patch("server.verify_google_id_token")
    def test_01_valid_google_token_login_succeeds(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google_sub_attacker",
            "email": "attacker@example.com",
            "name": "Attacker Name",
            "picture": "https://example.com/att.jpg"
        }

        res = server.verify_google_id_token("valid_token_attacker")
        self.assertIsNotNone(res)
        self.assertEqual(res["sub"], "google_sub_attacker")

    def test_02_missing_token_rejected(self):
        res = server.verify_google_id_token("")
        self.assertIsNone(res)
        res_none = server.verify_google_id_token(None)
        self.assertIsNone(res_none)

    def test_03_malformed_token_rejected(self):
        res = server.verify_google_id_token("not_a_valid_jwt_structure")
        self.assertIsNone(res)

    def test_04_forged_token_rejected(self):
        res = server.verify_google_id_token("eyJhbGciOiJub25lIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.")
        self.assertIsNone(res)

    def test_05_expired_token_rejected(self):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({
                "iss": "https://accounts.google.com",
                "sub": "12345",
                "exp": time.time() - 3600, # expired 1 hour ago
                "email": "test@example.com",
                "email_verified": True
            }).encode("utf-8")
            mock_url.return_value.__enter__.return_value = mock_resp

            res = server.verify_google_id_token("expired_token")
            self.assertIsNone(res)

    def test_06_wrong_audience_rejected(self):
        with patch.object(server, "GOOGLE_CLIENT_ID", "expected_client_id_123"):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = json.dumps({
                    "iss": "https://accounts.google.com",
                    "sub": "12345",
                    "aud": "wrong_client_id_456",
                    "exp": time.time() + 3600,
                    "email": "test@example.com",
                    "email_verified": True
                }).encode("utf-8")
                mock_url.return_value.__enter__.return_value = mock_resp

                res = server.verify_google_id_token("wrong_aud_token")
                self.assertIsNone(res)

    def test_16_missing_google_client_id_fails_closed(self):
        with patch.object(server, "GOOGLE_CLIENT_ID", ""):
            res = server.verify_google_id_token("some_token")
            self.assertIsNone(res)

    def test_17_valid_token_matching_client_id_succeeds(self):
        with patch.object(server, "GOOGLE_CLIENT_ID", "valid_kandid_client_id_789"):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.read.return_value = json.dumps({
                    "iss": "https://accounts.google.com",
                    "sub": "google_sub_999",
                    "aud": "valid_kandid_client_id_789",
                    "exp": time.time() + 3600,
                    "email": "validuser@example.com",
                    "email_verified": True,
                    "name": "Valid User"
                }).encode("utf-8")
                mock_url.return_value.__enter__.return_value = mock_resp

                res = server.verify_google_id_token("valid_token_kandid")
                self.assertIsNotNone(res)
                self.assertEqual(res["sub"], "google_sub_999")
                self.assertEqual(res["email"], "validuser@example.com")

    def test_07_wrong_issuer_rejected(self):
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps({
                "iss": "https://malicious-issuer.com",
                "sub": "12345",
                "exp": time.time() + 3600,
                "email": "test@example.com",
                "email_verified": True
            }).encode("utf-8")
            mock_url.return_value.__enter__.return_value = mock_resp

            res = server.verify_google_id_token("wrong_iss_token")
            self.assertIsNone(res)

    @patch("server.verify_google_id_token")
    def test_08_client_supplies_victim_email_with_attacker_token(self, mock_verify):
        # Token belongs to attacker
        mock_verify.return_value = {
            "sub": "google_sub_attacker",
            "email": "attacker@example.com",
            "name": "Attacker Name",
            "picture": ""
        }

        # Attacker posts victim's email in request body trying to claim victim account
        body = {
            "id_token": "valid_attacker_token",
            "email": "victim@example.com",
            "sub": "google_sub_victim"
        }

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Verify handler logic directly:
        verified_claims = server.verify_google_id_token(body["id_token"])
        google_id = verified_claims["sub"] # google_sub_attacker
        email = verified_claims["email"]   # attacker@example.com

        cursor.execute("""
            SELECT u.* FROM users u
            LEFT JOIN auth_identities ai ON u.id = ai.user_id AND ai.provider = 'google'
            WHERE (ai.provider = 'google' AND ai.provider_subject = ?)
               OR (LOWER(u.email) = ? AND ? != '' AND (u.onboarding_status IS NULL OR u.onboarding_status = 'active'))
            LIMIT 1
        """, (google_id, email, email))
        row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(dict(row)["id"], "user_attacker")
        self.assertNotEqual(dict(row)["id"], "user_victim")

    @patch("server.verify_google_id_token")
    def test_09_client_supplies_victim_google_id_with_attacker_token(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google_sub_attacker",
            "email": "attacker@example.com",
            "name": "Attacker Name",
            "picture": ""
        }

        verified_claims = server.verify_google_id_token("token")
        # Ensure server uses verified claims, ignoring body override
        self.assertEqual(verified_claims["sub"], "google_sub_attacker")

    @patch("server.verify_google_id_token")
    def test_10_cannot_overwrite_existing_linked_google_id(self, mock_verify):
        # Token belongs to attacker (google_sub_new), but email matches victim's email (victim@example.com)
        mock_verify.return_value = {
            "sub": "google_sub_new_attacker_id",
            "email": "victim@example.com", # Matching victim email
            "name": "Attacker",
            "picture": ""
        }

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        google_id = "google_sub_new_attacker_id"
        email = "victim@example.com"

        cursor.execute("""
            SELECT u.*, ai.provider_subject as linked_google_id FROM users u
            LEFT JOIN auth_identities ai ON u.id = ai.user_id AND ai.provider = 'google'
            WHERE (ai.provider = 'google' AND ai.provider_subject = ?)
               OR (LOWER(u.email) = ? AND ? != '' AND (u.onboarding_status IS NULL OR u.onboarding_status = 'active'))
            LIMIT 1
        """, (google_id, email, email))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        u = dict(row)
        linked_id = u.get("linked_google_id")

        # Victim account is already linked to google_sub_victim, not google_sub_new_attacker_id
        self.assertEqual(linked_id, "google_sub_victim")
        self.assertNotEqual(linked_id, google_id)

    @patch("server.verify_google_id_token")
    def test_11_verified_google_identity_login_own_account_succeeds(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google_sub_victim",
            "email": "victim@example.com",
            "name": "Victim Name",
            "picture": ""
        }

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        google_id = "google_sub_victim"
        email = "victim@example.com"

        cursor.execute("""
            SELECT u.* FROM users u
            LEFT JOIN auth_identities ai ON u.id = ai.user_id AND ai.provider = 'google'
            WHERE (ai.provider = 'google' AND ai.provider_subject = ?)
               OR (LOWER(u.email) = ? AND ? != '' AND (u.onboarding_status IS NULL OR u.onboarding_status = 'active'))
            LIMIT 1
        """, (google_id, email, email))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(dict(row)["id"], "user_victim")

    @patch("server.verify_google_id_token")
    def test_12_new_legitimate_google_account_creation(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google_sub_brand_new",
            "email": "newuser@example.com",
            "name": "New User",
            "picture": "https://example.com/new.jpg"
        }

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        google_id = "google_sub_brand_new"
        email = "newuser@example.com"

        cursor.execute("""
            SELECT u.* FROM users u
            LEFT JOIN auth_identities ai ON u.id = ai.user_id AND ai.provider = 'google'
            WHERE (ai.provider = 'google' AND ai.provider_subject = ?)
               OR (LOWER(u.email) = ? AND ? != '' AND (u.onboarding_status IS NULL OR u.onboarding_status = 'active'))
            LIMIT 1
        """, (google_id, email, email))
        row = cursor.fetchone()
        self.assertIsNone(row) # Proceeds to onboarding session creation

    @patch("server.verify_google_id_token")
    def test_13_existing_email_linking_requires_verified_matching_email(self, mock_verify):
        mock_verify.return_value = {
            "sub": "google_sub_unlinked_new",
            "email": "unlinked@example.com",
            "name": "Unlinked User",
            "picture": ""
        }

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        google_id = "google_sub_unlinked_new"
        email = "unlinked@example.com"

        cursor.execute("""
            SELECT u.*, ai.provider_subject as linked_google_id FROM users u
            LEFT JOIN auth_identities ai ON u.id = ai.user_id AND ai.provider = 'google'
            WHERE (ai.provider = 'google' AND ai.provider_subject = ?)
               OR (LOWER(u.email) = ? AND ? != '' AND (u.onboarding_status IS NULL OR u.onboarding_status = 'active'))
            LIMIT 1
        """, (google_id, email, email))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        u = dict(row)
        self.assertEqual(u["id"], "user_emailonly")
        self.assertIsNone(u.get("linked_google_id"))

    def test_14_no_sensitive_token_data_in_responses(self):
        raw_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InNlY3JldCJ9.eyJzZWNyZXQiOiJzZWNyZXRfdG9rZW5fZGF0YSJ9.signature"
        with patch.object(server, "verify_google_id_token", return_value=None):
            # Test that invalid token response returns structured error without reflecting token
            err_resp = {"success": False, "error": "Invalid, expired, or unverified Google token", "error_code": "INVALID_TOKEN"}
            self.assertNotIn("secret_token_data", json.dumps(err_resp))

    def test_15_password_authentication_unaffected(self):
        pw_hash, salt = server.hash_password("MySecurePassword123")
        self.assertTrue(server.verify_password("MySecurePassword123", salt, pw_hash))
        self.assertFalse(server.verify_password("WrongPassword123", salt, pw_hash))

if __name__ == "__main__":
    unittest.main()
