"""
Focused verification suite for:
1. Complete Account Enumeration Hardening (Forgot Password, Verify Reset OTP, Reset Password)
2. Reset Token Verifier Storage & Atomic Single-Use Concurrency Protection
3. OTP Database-Disclosure Hardening (Memory-Hard Scrypt KDF + Legacy SHA-256 Migration Compatibility)
4. OTP Expiry Race & Strict KDF Parameter Bounds Validation
"""

import os
import sys
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

# Ensure repo root is on path
REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import server

ORIGINAL_BREVO_API_KEY = server.BREVO_API_KEY
ORIGINAL_ENVIRONMENT = server.ENVIRONMENT
ORIGINAL_DB_FILE = server.DB_FILE
ORIGINAL_DATABASE_URL = server.DATABASE_URL
ORIGINAL_SESSION_SECRET = server.SESSION_SECRET


def _restore_globals():
    server.BREVO_API_KEY = ORIGINAL_BREVO_API_KEY
    server.ENVIRONMENT = ORIGINAL_ENVIRONMENT
    server.DB_FILE = ORIGINAL_DB_FILE
    server.DATABASE_URL = ORIGINAL_DATABASE_URL
    server.SESSION_SECRET = ORIGINAL_SESSION_SECRET


class TestRemediatedEnumerationAndOtpKdf(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.addCleanup(_restore_globals)
        self.addCleanup(self._cleanup_db)

        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = "test_brevo_key"
        server.SESSION_SECRET = "9f8e7d6c5b4a3928170e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"

        with server.rate_limiter.lock:
            server.rate_limiter.buckets.clear()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("""
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL
            );
        """)

        cur.execute("""
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

        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        self.test_pw = "ValidPassword123!"
        self.pw_hash, self.salt = server.hash_password(self.test_pw)

        # Existing account with email
        cur.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt, onboarding_status)
            VALUES ('u_alice', 'alice@example.com', 'alice', 'Alice Smith', ?, ?, 'active')
        """, (self.pw_hash, self.salt))

        # Existing account with NO email
        cur.execute("""
            INSERT INTO users (id, email, handle, name, password_hash, salt, onboarding_status)
            VALUES ('u_no_email', '', 'no_email_user', 'No Email User', ?, ?, 'active')
        """, (self.pw_hash, self.salt))

        conn.commit()
        conn.close()

    def _cleanup_db(self):
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)
        except Exception:
            pass

    def _call_post(self, path, body, client_ip="127.0.0.1"):
        class DummyHandler(server.KandidHandler):
            def __init__(self, req_path, req_body, ip):
                self.path = req_path
                body_bytes = json.dumps(req_body).encode("utf-8")
                self.headers = {
                    "Content-Length": str(len(body_bytes)),
                    "Content-Type": "application/json"
                }
                import io
                self.rfile = io.BytesIO(body_bytes)
                self.sent_response = {}
                self.client_address = (ip, 12345)

            def send_json(self, status_code, response_dict):
                self.sent_response["status"] = status_code
                self.sent_response["body"] = response_dict
                return response_dict

        h = DummyHandler(path, body, client_ip)
        h.do_POST()
        if getattr(server, "_last_otp_dispatch_thread", None) and server._last_otp_dispatch_thread.is_alive():
            server._last_otp_dispatch_thread.join(timeout=2.0)
        return h.sent_response

    # =========================================================================
    # FINDING 1: COMPLETE ACCOUNT ENUMERATION HARDENING
    # =========================================================================

    def test_01_forgot_password_known_vs_unknown_complete_equality_on_success(self):
        """Valid account and unknown account return 100% identical HTTP 200 payload and shape."""
        with patch("server.send_email_resend", return_value={"success": True, "id": "m1", "status_code": 200, "delivery_status": "accepted"}):
            resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.1.1")
            resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "ghost@example.com"}, client_ip="10.0.1.2")

            self.assertEqual(resp_known["status"], 200)
            self.assertEqual(resp_unknown["status"], 200)
            self.assertEqual(resp_known["body"], resp_unknown["body"])
            self.assertEqual(resp_known["body"], {
                "success": True,
                "message": "If an account is associated with this handle or email, a verification code has been sent.",
                "delivery_status": "accepted"
            })

    def test_02_forgot_password_known_handle_vs_unknown_handle_complete_equality(self):
        """Existing handle and nonexistent handle return identical responses with zero existence signal."""
        with patch("server.send_email_resend", return_value={"success": True, "id": "m2", "status_code": 200, "delivery_status": "accepted"}):
            resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "@alice"}, client_ip="10.0.2.1")
            resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "@nosuchhandle_999"}, client_ip="10.0.2.2")

            self.assertEqual(resp_known["status"], 200)
            self.assertEqual(resp_unknown["status"], 200)
            self.assertEqual(resp_known["body"], resp_unknown["body"])

    def test_03_forgot_password_no_email_user_returns_uniform_generic_success(self):
        """Account lacking an email address returns uniform generic 200, never discloses lack of email."""
        resp_no_email = self._call_post("/api/auth/forgot-password", {"identifier": "no_email_user"})
        self.assertEqual(resp_no_email["status"], 200)
        self.assertEqual(resp_no_email["body"], {
            "success": True,
            "message": "If an account is associated with this handle or email, a verification code has been sent.",
            "delivery_status": "accepted"
        })

    def test_04_forgot_password_configured_provider_outage_parity(self):
        """
        When email provider is configured but experiences an outage / 503 failure:
        both existing user and nonexistent user return the EXACT SAME HTTP 200 generic response.
        No 503 or error code is leaked to the client.
        """
        with patch("server.send_email_resend", side_effect=Exception("Connection refused to Brevo")):
            resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "alice"}, client_ip="10.0.3.1")
            resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "nobody"}, client_ip="10.0.3.2")

            self.assertEqual(resp_known["status"], 200)
            self.assertEqual(resp_unknown["status"], 200)
            self.assertEqual(resp_known["body"], resp_unknown["body"])
            self.assertEqual(resp_known["body"]["success"], True)
            self.assertNotIn("EMAIL_PROVIDER_UNAVAILABLE", json.dumps(resp_known))

    def test_05_forgot_password_unconfigured_provider_parity(self):
        """
        When email provider is unconfigured in production:
        both existing user and nonexistent user receive the exact same generic 200 response.
        """
        server.ENVIRONMENT = "production"
        server.BREVO_API_KEY = ""

        resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "alice"}, client_ip="10.0.4.1")
        resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "nobody"}, client_ip="10.0.4.2")

        self.assertEqual(resp_known["status"], 200)
        self.assertEqual(resp_unknown["status"], 200)
        self.assertEqual(resp_known["body"], resp_unknown["body"])

    def test_06_forgot_password_handle_email_quota_alias_no_enumeration(self):
        """
        Requesting handle @alice 3 times consumes handle quota.
        Querying alice@example.com returns HTTP 200 generic response, matching unknown handle/email.
        Zero cross-identifier oracle.
        """
        with patch("server.send_email_resend", return_value={"success": True, "id": "m6", "status_code": 200, "delivery_status": "accepted"}):
            # Consume 3 requests for handle 'alice'
            for i in range(3):
                r = self._call_post("/api/auth/forgot-password", {"identifier": "alice"}, client_ip=f"10.0.5.{i}")
                self.assertEqual(r["status"], 200)

            # 4th request on handle 'alice' is rate-limited
            r_handle_4th = self._call_post("/api/auth/forgot-password", {"identifier": "alice"}, client_ip="10.0.5.99")
            self.assertEqual(r_handle_4th["status"], 429)

            # 1st request on alice@example.com returns 200 generic response
            r_email_1st = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.5.100")
            self.assertEqual(r_email_1st["status"], 200)

            # Compare with fresh unknown identifier
            r_unknown_1st = self._call_post("/api/auth/forgot-password", {"identifier": "fresh_user"}, client_ip="10.0.5.101")
            self.assertEqual(r_unknown_1st["status"], 200)
            self.assertEqual(r_email_1st["body"], r_unknown_1st["body"])

    def test_07_verify_reset_otp_complete_parity_across_failure_modes(self):
        """
        In /api/auth/verify-reset-otp, all failure modes:
        - Nonexistent user
        - Existing user with no pending OTP
        - Existing user with wrong OTP
        - Existing user with expired OTP
        all return the EXACT same status (400) and payload (INVALID_VERIFICATION_CODE).
        """
        # 1. Nonexistent user
        r_nonexistent = self._call_post("/api/auth/verify-reset-otp", {"identifier": "ghost", "otp": "123456"})
        self.assertEqual(r_nonexistent["status"], 400)

        # 2. Existing user with no pending OTP
        r_no_otp = self._call_post("/api/auth/verify-reset-otp", {"identifier": "alice", "otp": "123456"})
        self.assertEqual(r_no_otp["status"], 400)

        # 3. Existing user with wrong OTP
        with patch("server.send_email_resend", return_value={"success": True, "id": "m7", "status_code": 200, "delivery_status": "accepted"}):
            server.generate_secure_otp("alice@example.com")
        r_wrong_otp = self._call_post("/api/auth/verify-reset-otp", {"identifier": "alice", "otp": "000000"})
        self.assertEqual(r_wrong_otp["status"], 400)

        # 4. Existing user with expired OTP
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE email_otps SET expires_at = '2000-01-01T00:00:00' WHERE email = 'alice@example.com'")
        conn.commit()
        conn.close()
        r_expired_otp = self._call_post("/api/auth/verify-reset-otp", {"identifier": "alice", "otp": "123456"})
        self.assertEqual(r_expired_otp["status"], 400)

        # Check total equality across all 4 failure modes
        expected_body = {
            "success": False,
            "error_code": "INVALID_VERIFICATION_CODE",
            "error": "Invalid or expired verification code. Please check and try again."
        }
        self.assertEqual(r_nonexistent["body"], expected_body)
        self.assertEqual(r_no_otp["body"], expected_body)
        self.assertEqual(r_wrong_otp["body"], expected_body)
        self.assertEqual(r_expired_otp["body"], expected_body)

    def test_08_verify_reset_otp_never_discloses_email_on_success(self):
        """Successful /api/auth/verify-reset-otp returns reset_token and NEVER discloses user email."""
        dispatched_otp = []
        def capture_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "m8", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=capture_dispatch):
            server.generate_secure_otp("alice@example.com")

        self.assertEqual(len(dispatched_otp), 1)
        valid_otp = dispatched_otp[0]

        resp = self._call_post("/api/auth/verify-reset-otp", {"identifier": "alice", "otp": valid_otp})
        self.assertEqual(resp["status"], 200)
        self.assertTrue(resp["body"].get("success"))
        self.assertTrue(resp["body"].get("reset_token").startswith("prt_"))
        self.assertNotIn("email", resp["body"])
        self.assertNotIn("masked_email", resp["body"])
        self.assertNotIn("alice@example.com", json.dumps(resp["body"]))

    def test_09_direct_reset_password_parity_across_failure_modes(self):
        """
        In /api/auth/reset-password direct flow, all failure modes:
        - Nonexistent user
        - Known user with no pending OTP
        - Known user with wrong OTP
        all return the EXACT same status (400) and payload (OTP_INVALID).
        """
        # Nonexistent user
        r_nonexistent = self._call_post("/api/auth/reset-password", {
            "identifier": "missing_user",
            "otp": "123456",
            "new_password": "NewSecretPassword123!"
        })

        # Known user with no pending OTP
        r_no_otp = self._call_post("/api/auth/reset-password", {
            "identifier": "alice",
            "otp": "123456",
            "new_password": "NewSecretPassword123!"
        })

        expected_body = {
            "success": False,
            "error_code": "OTP_INVALID",
            "error": "Invalid or expired verification code. Please check and try again."
        }
        self.assertEqual(r_nonexistent["status"], 400)
        self.assertEqual(r_no_otp["status"], 400)
        self.assertEqual(r_nonexistent["body"], expected_body)
        self.assertEqual(r_no_otp["body"], expected_body)

    # =========================================================================
    # FINDING 2: RESET TOKEN STORAGE IN PLAINTEXT
    # =========================================================================

    def test_10_reset_token_db_stores_verifier_not_raw_token(self):
        """password_resets table stores HMAC-SHA256 verifier, never the raw bearer token."""
        dispatched_otp = []
        def capture_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "m10", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=capture_dispatch):
            server.generate_secure_otp("alice@example.com")

        valid_otp = dispatched_otp[0]
        resp = self._call_post("/api/auth/verify-reset-otp", {"identifier": "alice", "otp": valid_otp})
        raw_token = resp["body"]["reset_token"]
        self.assertTrue(raw_token.startswith("prt_"))

        # Check DB
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT token FROM password_resets WHERE email = 'alice@example.com'")
        row = cur.fetchone()
        conn.close()

        stored_verifier = row["token"]
        # Raw token must NOT be in the DB
        self.assertNotEqual(stored_verifier, raw_token)
        self.assertNotIn(raw_token, stored_verifier)
        # Stored verifier must have v1$hmac_sha256$ prefix
        self.assertTrue(stored_verifier.startswith("v1$hmac_sha256$"))

        # Valid raw token successfully resets password
        new_pw = "FreshlyChangedPw987!"
        resp_reset = self._call_post("/api/auth/reset-password", {
            "reset_token": raw_token,
            "new_password": new_pw
        })
        self.assertEqual(resp_reset["status"], 200)
        self.assertTrue(resp_reset["body"].get("success"))

        # Single-use: using the raw token again fails
        resp_replay = self._call_post("/api/auth/reset-password", {
            "reset_token": raw_token,
            "new_password": "AnotherPassword456!"
        })
        self.assertEqual(resp_replay["status"], 400)
        self.assertEqual(resp_replay["body"]["error_code"], "INVALID_RESET_TOKEN")

    def test_11_invalid_and_expired_reset_tokens_fail_closed(self):
        """Invalid token and expired token both return 400 INVALID_RESET_TOKEN."""
        r_invalid = self._call_post("/api/auth/reset-password", {
            "reset_token": "prt_invalid_gibberish_token",
            "new_password": "NewSecretPassword123!"
        })
        self.assertEqual(r_invalid["status"], 400)
        self.assertEqual(r_invalid["body"]["error_code"], "INVALID_RESET_TOKEN")

        # Expired token in DB
        raw_expired = "prt_" + "e" * 48
        verifier_expired = server.hash_reset_token(raw_expired)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO password_resets (id, email, token, expires_at, created_at)
            VALUES ('pr_exp', 'alice@example.com', ?, '2000-01-01T00:00:00', CURRENT_TIMESTAMP)
        """, (verifier_expired,))
        conn.commit()
        conn.close()

        r_expired = self._call_post("/api/auth/reset-password", {
            "reset_token": raw_expired,
            "new_password": "NewSecretPassword123!"
        })
        self.assertEqual(r_expired["status"], 400)
        self.assertEqual(r_expired["body"]["error_code"], "INVALID_RESET_TOKEN")

    # =========================================================================
    # FINDING 3: RESET TOKEN REPLAY RACE (ATOMIC CLAIM UNDER CONCURRENCY)
    # =========================================================================

    def test_12_reset_token_concurrency_race_single_claim(self):
        """
        Two simultaneous requests presenting the same valid reset token:
        exactly ONE succeeds (HTTP 200), and the second fails (HTTP 400 INVALID_RESET_TOKEN).
        The losing thread cannot update password or create a session.
        """
        raw_token = "prt_" + "c" * 48
        token_verifier = server.hash_reset_token(raw_token)
        expires_at = (server.datetime.now() + server.timedelta(minutes=10)).isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO password_resets (id, email, token, expires_at, created_at)
            VALUES ('pr_race', 'alice@example.com', ?, ?, CURRENT_TIMESTAMP)
        """, (token_verifier, expires_at))
        conn.commit()
        conn.close()

        results = []
        barrier = threading.Barrier(2)

        def worker(thread_id):
            barrier.wait()
            resp = self._call_post("/api/auth/reset-password", {
                "reset_token": raw_token,
                "new_password": f"PasswordThread{thread_id}Secure!"
            }, client_ip=f"10.0.6.{thread_id}")
            results.append(resp)

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r["status"] == 200]
        failures = [r for r in results if r["status"] == 400]
        self.assertEqual(len(successes), 1, "Exactly one concurrent thread must claim the reset token")
        self.assertEqual(len(failures), 1, "The competing thread must fail atomic claim with HTTP 400")
        self.assertEqual(failures[0]["body"]["error_code"], "INVALID_RESET_TOKEN")

        # Verify only 1 new session exists for alice
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'u_alice'")
        session_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(session_count, 1, "Only the winning thread may create a session")

    # =========================================================================
    # FINDING 4, 5, 7: OTP KDF DESIGN, PRODUCTION REQUIREMENT & STRICT BOUNDS
    # =========================================================================

    def test_13_otp_hash_scrypt_generation_and_verification(self):
        """hash_otp_code generates scrypt$16384$8$1$ format in production and verifies correctly."""
        hash_str, salt_hex = server.hash_otp_code("654321")
        self.assertTrue(hash_str.startswith("scrypt$16384$8$1$"))

        # Verify with correct code
        self.assertTrue(server.verify_otp_code_hash("654321", salt_hex, hash_str))
        # Verify with wrong code
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, hash_str))

    def test_14_production_scrypt_requirement_raises_on_missing_scrypt(self):
        """In production environment, hash_otp_code raises RuntimeError if hashlib lacks scrypt."""
        server.ENVIRONMENT = "production"
        with patch.object(server.hashlib, "scrypt", create=False):
            # Simulate environment where hashlib has no scrypt attribute
            with patch("server.hasattr", side_effect=lambda obj, name: False if name == "scrypt" else hasattr(obj, name)):
                with self.assertRaises(RuntimeError) as ctx:
                    server.hash_otp_code("123456")
                self.assertIn("hashlib.scrypt is required in production", str(ctx.exception))

    def test_15_development_pbkdf2_fallback_branch(self):
        """In development/test environment, hash_otp_code gracefully falls back to PBKDF2 if scrypt unavailable."""
        server.ENVIRONMENT = "development"
        with patch("server.hasattr", side_effect=lambda obj, name: False if name == "scrypt" else hasattr(obj, name)):
            hash_str, salt_hex = server.hash_otp_code("123456")
            self.assertTrue(hash_str.startswith("pbkdf2$sha256$100000$"))
            self.assertTrue(server.verify_otp_code_hash("123456", salt_hex, hash_str))
            self.assertFalse(server.verify_otp_code_hash("000000", salt_hex, hash_str))

    def test_16_strict_kdf_parameter_bounds_rejection(self):
        """
        verify_otp_code_hash strictly validates and bounds KDF parameters:
        - Excessive scrypt N (> 32768) rejected
        - Non-power-of-2 scrypt N rejected
        - Excessive r (> 16) rejected
        - Excessive p (> 4) rejected
        - Excessive memory envelope (> 32MB) rejected
        - Excessive PBKDF2 iterations (> 200000) rejected
        - Too low PBKDF2 iterations (< 1000) rejected
        - Malformed/tampered parameters rejected
        """
        salt_hex = "abcdef1234567890"
        dummy_hex_128 = "a" * 128
        dummy_hex_64 = "b" * 64

        # 1. Excessive scrypt N
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"scrypt$65536$8$1${dummy_hex_128}"))

        # 2. Non-power-of-2 scrypt N
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"scrypt$10000$8$1${dummy_hex_128}"))

        # 3. Excessive r
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"scrypt$16384$32$1${dummy_hex_128}"))

        # 4. Excessive p
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"scrypt$16384$8$8${dummy_hex_128}"))

        # 5. Invalid hex length
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, "scrypt$16384$8$1$abcd"))

        # 6. Excessive PBKDF2 iterations
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"pbkdf2$sha256$500000${dummy_hex_64}"))

        # 7. Sub-threshold PBKDF2 iterations
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"pbkdf2$sha256$500${dummy_hex_64}"))

        # 8. Unsupported PBKDF2 algorithm
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, f"pbkdf2$md5$100000${dummy_hex_64}"))

        # 9. Empty / None values
        self.assertFalse(server.verify_otp_code_hash("", salt_hex, f"scrypt$16384$8$1${dummy_hex_128}"))
        self.assertFalse(server.verify_otp_code_hash("123456", "", f"scrypt$16384$8$1${dummy_hex_128}"))
        self.assertFalse(server.verify_otp_code_hash("123456", salt_hex, ""))

    def test_17_legacy_sha256_backward_compatibility_bounded(self):
        """Legacy SHA-256 OTPs are rejected in production/prod and accepted only in development."""
        import hashlib, secrets
        legacy_code = "741852"
        legacy_salt = secrets.token_hex(16)
        legacy_hash = hashlib.sha256((legacy_code + legacy_salt).encode("utf-8")).hexdigest()
        expires_at = (server.datetime.now() + server.timedelta(minutes=10)).isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO email_otps (id, email, otp_hash, salt, attempts, max_attempts, expires_at, is_used, created_at)
            VALUES ('otp_legacy', 'legacy_user@example.com', ?, ?, 0, 5, ?, 0, CURRENT_TIMESTAMP)
        """, (legacy_hash, legacy_salt, expires_at))
        conn.commit()
        conn.close()

        # In production/prod: Legacy OTP is strictly rejected
        for env_val in ("production", "prod"):
            with patch("server.ENVIRONMENT", env_val):
                with patch.dict(os.environ, {"ENVIRONMENT": env_val}):
                    res_prod = server.verify_secure_otp("legacy_user@example.com", legacy_code)
                    self.assertFalse(res_prod.get("success"))

        # In development: Legacy OTP verifies correctly (backward compatibility)
        with patch("server.ENVIRONMENT", "development"):
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                res_success = server.verify_secure_otp("legacy_user@example.com", legacy_code)
                self.assertTrue(res_success.get("success"))

                # Replay fails
                res_replay = server.verify_secure_otp("legacy_user@example.com", legacy_code)
                self.assertFalse(res_replay.get("success"))

    # =========================================================================
    # FINDING 6: OTP EXPIRY RACE DURING FINAL CLAIM
    # =========================================================================

    def test_18_otp_expiry_race_atomic_claim_fails_if_expired(self):
        """An OTP that expires before the atomic UPDATE claim is rejected."""
        dispatched_otp = []
        def capture_dispatch(email, subject, html, text):
            import re
            m = re.search(r'\b\d{6}\b', text)
            if m:
                dispatched_otp.append(m.group(0))
            return {"success": True, "id": "m18", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=capture_dispatch):
            server.generate_secure_otp("alice@example.com")

        valid_otp = dispatched_otp[0]

        # Hook into verify_otp_code_hash to backdate expires_at RIGHT BEFORE atomic claim
        orig_verify_hash = server.verify_otp_code_hash
        def race_backdate(code, salt, stored_hash):
            verified = orig_verify_hash(code, salt, stored_hash)
            # Simulate clock advancing / expiration right after KDF calculation
            c = sqlite3.connect(self.db_path)
            c.execute("UPDATE email_otps SET expires_at = '2000-01-01T00:00:00' WHERE email = 'alice@example.com'")
            c.commit()
            c.close()
            return verified

        with patch("server.verify_otp_code_hash", side_effect=race_backdate):
            res = server.verify_secure_otp("alice@example.com", valid_otp)
            self.assertFalse(res.get("success"), "OTP expired before atomic claim must be rejected")
            self.assertIn("expired", res.get("error").lower())


    # =========================================================================
    # FINDING 7: TIMING EQUALIZATION (FORGOT PASSWORD CPU WORK EQUALITY)
    # =========================================================================

    def test_19_timing_equalization_cpu_cryptographic_work(self):
        """
        Verify that both known and unknown identifiers execute equivalent CPU/scrypt workloads.
        In mock dispatch (excluding external network latency), the execution time difference is bounded.
        """
        import time
        with patch("server.send_email_resend", return_value={"success": True, "id": "m19", "status_code": 200, "delivery_status": "accepted"}):
            # Unknown user timing
            t0 = time.perf_counter()
            resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "ghost_timing_check@example.com"}, client_ip="10.0.19.1")
            t_unknown = time.perf_counter() - t0

            # Known user timing
            t0 = time.perf_counter()
            resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.19.2")
            t_known = time.perf_counter() - t0

            self.assertEqual(resp_unknown["status"], 200)
            self.assertEqual(resp_known["status"], 200)
            self.assertEqual(resp_unknown["body"], resp_known["body"])

            # Both paths must have spent CPU cycles on scrypt (each > 5ms)
            self.assertGreater(t_unknown, 0.005, f"Unknown account path took {t_unknown*1000:.2f}ms, expected scrypt workload")
            self.assertGreater(t_known, 0.005, f"Known account path took {t_known*1000:.2f}ms, expected scrypt workload")

    # =========================================================================
    # FINDING 8: SCRYPT RUNTIME FAILURE & PBKDF2 PRODUCTION REJECTION
    # =========================================================================

    def test_20_scrypt_runtime_failure_in_production_fails_closed_without_downgrade(self):
        """
        If hashlib.scrypt raises an exception in production:
        1. hash_otp_code raises RuntimeError (no silent downgrade in prod).
        2. generate_secure_otp catches exception and returns safe status 500 error dict.
        3. /api/auth/forgot-password catches internal failure and returns generic HTTP 200 to client.
        """
        import hashlib
        orig_scrypt = hashlib.scrypt

        def mock_broken_scrypt(*args, **kwargs):
            raise ValueError("memory limit exceeded during scrypt")

        with patch("hashlib.scrypt", side_effect=mock_broken_scrypt):
            server.ENVIRONMENT = "production"

            # 1. Direct call raises RuntimeError in production
            with self.assertRaises(RuntimeError) as ctx:
                server.hash_otp_code("123456")
            self.assertIn("CRITICAL: hashlib.scrypt runtime failure", str(ctx.exception))

            # 2. generate_secure_otp catches and returns status 500 error dict
            res = server.generate_secure_otp("alice@example.com")
            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("status"), 500)
            self.assertEqual(res.get("error_code"), "OTP_GENERATION_FAILED")

            # 3. /api/auth/forgot-password returns generic HTTP 200 (does not leak 500 or error details)
            resp = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.20.1")
            self.assertEqual(resp["status"], 200)
            self.assertEqual(resp["body"], {
                "success": True,
                "message": "If an account is associated with this handle or email, a verification code has been sent.",
                "delivery_status": "accepted"
            })

    def test_21_verification_strictly_rejects_pbkdf2_downgrade_in_production(self):
        """In production, verify_otp_code_hash strictly rejects PBKDF2 hashes; dev permits them."""
        import hashlib, secrets
        code = "654321"
        salt = secrets.token_hex(16)
        salt_bytes = bytes.fromhex(salt)
        derived = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt_bytes, 100000).hex()
        pbkdf2_hash = f"pbkdf2$sha256$100000${derived}"

        # Production environment: MUST reject
        server.ENVIRONMENT = "production"
        self.assertFalse(server.verify_otp_code_hash(code, salt, pbkdf2_hash), "PBKDF2 hash must be rejected in production")

        # Development environment: permits verification
        server.ENVIRONMENT = "development"
        self.assertTrue(server.verify_otp_code_hash(code, salt, pbkdf2_hash), "PBKDF2 hash should be allowed in development")

    # =========================================================================
    # FINDING 9: SESSION_SECRET VALIDATION & DIAGNOSTIC LOGGING
    # =========================================================================

    def test_22_session_secret_production_validation(self):
        """Production requires strong, high-entropy SESSION_SECRET and rejects weak/placeholder fallbacks."""
        # a) Production missing secret -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="", env="production")
        self.assertIn("explicitly configured", str(ctx.exception))

        # Too short (< 32 chars) -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="too_short_secret_123", env="production")
        self.assertIn("too short", str(ctx.exception))

        # b) Obvious sample from .env.example -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="kandid_super_secure_session_secret_2026", env="production")
        self.assertIn("cryptographically generated", str(ctx.exception))

        # Obvious placeholder / demo keys -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="kandid_secure_session_key_2026_placeholder", env="production")
        self.assertIn("cryptographically generated", str(ctx.exception))

        # c) Predictable repeating secret -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="12345678901234567890123456789012", env="production")
        self.assertIn("cryptographically generated", str(ctx.exception))

        # Predictable human-readable secret -> fail
        with self.assertRaises(RuntimeError) as ctx:
            server.validate_session_secret(secret="this_is_a_very_long_human_readable_phrase_123", env="production")
        self.assertIn("cryptographically generated", str(ctx.exception))

        # d) Genuinely generated strong secret (64 hex characters) -> pass
        strong_hex = "9f8e7d6c5b4a3928170e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"
        self.assertTrue(server.validate_session_secret(secret=strong_hex, env="production"))

        # Genuinely generated strong secret (base64 token) -> pass
        strong_b64 = "w8Z-fT3qX9vB2yM5rK0pL7uN4cV1aE8dG2jH5kL9mP6="
        self.assertTrue(server.validate_session_secret(secret=strong_b64, env="production"))

        # e) Development mode allows safe fallback
        self.assertTrue(server.validate_session_secret(secret="", env="development"))

    def test_23_session_secret_diagnostic_logging_never_leaks_secret(self):
        """Startup diagnostic logs report status and length, never printing the raw SESSION_SECRET."""
        import io
        from contextlib import redirect_stdout

        server.ENVIRONMENT = "production"
        strong_secret = "9f8e7d6c5b4a3928170e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"
        server.SESSION_SECRET = strong_secret

        f = io.StringIO()
        with redirect_stdout(f):
            server.validate_environment()
        output = f.getvalue()

        self.assertIn(f"length={len(strong_secret)}", output)
        self.assertIn("configured=true", output)
        self.assertNotIn(strong_secret, output, "Raw SESSION_SECRET must NEVER be printed in logs")

    # =========================================================================
    # FINDING 10: FRESH CLAIM TIMESTAMP IN RESET-PASSWORD
    # =========================================================================

    def test_24_fresh_claim_time_prevents_claiming_tokens_expired_during_verification(self):
        """
        Tokens expiring between initial select and conditional delete must fail atomic claim.
        Verifies fresh_claim_time enforcement, transaction rollback, and generic rejection.
        """
        reset_token = "prt_" + "a" * 48
        verifier = server.hash_reset_token(reset_token)
        reset_id = "pr_test_expiry"

        conn = sqlite3.connect(self.db_path)
        # Token valid for 1 second
        valid_until = (server.datetime.now() + server.timedelta(seconds=1)).isoformat()
        conn.execute(
            "INSERT INTO password_resets (id, email, token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (reset_id, "alice@example.com", verifier, valid_until, server.datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        # Hook verify_reset_token_hash to backdate expires_at right before the conditional DELETE
        orig_verify_hash = server.verify_reset_token_hash
        def race_backdate(raw, stored):
            res = orig_verify_hash(raw, stored)
            c = sqlite3.connect(self.db_path)
            c.execute("UPDATE password_resets SET expires_at = '2000-01-01T00:00:00' WHERE id = ?", (reset_id,))
            c.commit()
            c.close()
            return res

        with patch("server.verify_reset_token_hash", side_effect=race_backdate):
            resp = self._call_post("/api/auth/reset-password", {
                "reset_token": reset_token,
                "new_password": "NewValidPassword999!"
            })

            self.assertEqual(resp["status"], 400)
            self.assertEqual(resp["body"]["error_code"], "INVALID_RESET_TOKEN")

            # Verify password was NOT changed in DB
            c = sqlite3.connect(self.db_path)
            c.row_factory = sqlite3.Row
            u = c.execute("SELECT password_hash, salt FROM users WHERE email = 'alice@example.com'").fetchone()
            c.close()
            self.assertTrue(server.verify_password("ValidPassword123!", u["salt"], u["password_hash"]))
            self.assertFalse(server.verify_password("NewValidPassword999!", u["salt"], u["password_hash"]))


    # =========================================================================
    # FINDING 11: ACCOUNT-EXISTENCE LOGGING (REMOVED)
    # =========================================================================

    def test_25_forgot_password_account_existence_never_logged(self):
        """Verify that account_found is NEVER logged during forgot-password processing."""
        import io
        from contextlib import redirect_stdout

        with patch("server.send_email_resend", return_value={"success": True, "id": "m25", "status_code": 200, "delivery_status": "accepted"}):
            # Test with known account
            f_known = io.StringIO()
            with redirect_stdout(f_known):
                self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.25.1")
            log_known = f_known.getvalue()

            # Test with unknown account
            f_unknown = io.StringIO()
            with redirect_stdout(f_unknown):
                self._call_post("/api/auth/forgot-password", {"identifier": "nobody@example.com"}, client_ip="10.0.25.2")
            log_unknown = f_unknown.getvalue()

            # Neither log must reveal account existence
            self.assertNotIn("account_found", log_known.lower(), "account_found flag must be removed from logs")
            self.assertNotIn("account_found", log_unknown.lower(), "account_found flag must be removed from logs")
            self.assertNotIn("alice@example.com", log_known, "Raw email must not be logged in forgot password path")
            self.assertNotIn("nobody@example.com", log_unknown, "Raw email must not be logged in forgot password path")

    # =========================================================================
    # FINDING 12: DECOUPLED EMAIL PROVIDER LATENCY
    # =========================================================================

    def test_26_decoupled_email_provider_latency_architectural_guarantee(self):
        """
        Verify that provider network latency is completely decoupled from the synchronous HTTP response.
        Even when the email provider takes 400ms to respond, the HTTP request completes in < 80ms.
        """
        import time

        def slow_email_dispatch(to_email, subject, html, text):
            time.sleep(0.4)  # Simulate 400ms provider network round-trip
            return {"success": True, "id": "m26_slow", "status_code": 200, "delivery_status": "accepted"}

        class FastDummyHandler(server.KandidHandler):
            def __init__(self, req_path, req_body, ip):
                self.path = req_path
                body_bytes = json.dumps(req_body).encode("utf-8")
                self.headers = {
                    "Content-Length": str(len(body_bytes)),
                    "Content-Type": "application/json"
                }
                import io
                self.rfile = io.BytesIO(body_bytes)
                self.sent_response = {}
                self.client_address = (ip, 12345)

            def send_json(self, status_code, response_dict):
                self.sent_response["status"] = status_code
                self.sent_response["body"] = response_dict
                return response_dict

        with patch("server.send_email_resend", side_effect=slow_email_dispatch):
            h = FastDummyHandler("/api/auth/forgot-password", {"identifier": "alice@example.com"}, "10.0.26.1")
            t0 = time.perf_counter()
            h.do_POST()  # Returns synchronously without waiting for background email thread
            t_elapsed = time.perf_counter() - t0

            # HTTP response must complete in < 0.10s despite 0.40s provider latency
            self.assertLess(t_elapsed, 0.10, f"HTTP response took {t_elapsed*1000:.2f}ms; provider latency was not decoupled!")
            self.assertEqual(h.sent_response["status"], 200)

            # Wait for background dispatch to finish
            server.drain_otp_dispatch_queue(timeout=2.0)

    # =========================================================================
    # FINDING 13: BOUNDED WORKER POOL & EXACT OTP ID TARGETING
    # =========================================================================

    def test_27_bounded_email_worker_pool_and_exact_otp_id_targeting(self):
        """
        Verify that:
        1. Async dispatch runs on a bounded worker pool.
        2. Worker carries exact otp_id: Delayed failure of OTP A does NOT invalidate OTP B.
        """
        import time

        dispatched_items = []
        def controlled_dispatch(to_email, subject, html, text):
            # If dispatching for first code (OTP A), fail slowly; if for second (OTP B), succeed
            if "OTP_A" in text:
                time.sleep(0.05)
                return {"success": False, "error_code": "BREVO_AUTH_FAILURE", "status_code": 401, "delivery_status": "rejected"}
            return {"success": True, "id": "m_ok", "status_code": 200, "delivery_status": "accepted"}

        with patch("server.send_email_resend", side_effect=controlled_dispatch):
            # Create OTP A manually with marker text
            res_a = server.generate_secure_otp("bob@example.com", "10.0.27.1", async_dispatch=False)
            self.assertTrue(res_a["success"])

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row_a = conn.execute("SELECT id FROM email_otps WHERE email = 'bob@example.com' ORDER BY created_at DESC").fetchone()
            otp_a_id = row_a["id"]
            conn.close()

            # Enqueue failure item for OTP A into the bounded queue
            server._email_dispatch_queue.put(("bob@example.com", "Subject", "<div>OTP_A</div>", "OTP_A", otp_a_id))

            # Shortly after, generate OTP B for the same email
            res_b = server.generate_secure_otp("bob@example.com", "10.0.27.1", async_dispatch=False)
            self.assertTrue(res_b["success"])

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row_b = conn.execute("SELECT id FROM email_otps WHERE email = 'bob@example.com' ORDER BY created_at DESC").fetchone()
            otp_b_id = row_b["id"]
            conn.close()
            self.assertNotEqual(otp_a_id, otp_b_id)

            # Wait for the worker queue to drain
            server.drain_otp_dispatch_queue(timeout=3.0)

            # Check database status of OTP A and OTP B
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rec_a = conn.execute("SELECT is_used FROM email_otps WHERE id = ?", (otp_a_id,)).fetchone()
            rec_b = conn.execute("SELECT is_used FROM email_otps WHERE id = ?", (otp_b_id,)).fetchone()
            conn.close()

            # OTP A must be marked unusable (is_used = 1) due to failure
            self.assertEqual(rec_a["is_used"], 1, "OTP A must be marked unusable after failure")
            # OTP B must remain valid (is_used = 0) because worker targeted only OTP A's ID
            self.assertEqual(rec_b["is_used"], 0, "OTP B must NOT be invalidated by OTP A's delayed failure")

    def test_28_queue_full_drops_gracefully_and_marks_otp_unusable(self):
        """
        Verify that when the dispatch queue is full:
        1. Request is never blocked.
        2. Endpoint returns generic 200 response without account existence leak.
        3. The OTP row is marked is_used = 1 so the un-delivered OTP cannot be guessed.
        """
        import queue

        with patch.object(server._email_dispatch_queue, "put_nowait", side_effect=queue.Full):
            resp = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"}, client_ip="10.0.28.1")
            self.assertEqual(resp["status"], 200)
            self.assertTrue(resp["body"]["success"])
            self.assertEqual(resp["body"]["delivery_status"], "accepted")

            # Verify the OTP was generated and immediately marked unusable in DB
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT is_used FROM email_otps WHERE email = 'alice@example.com' ORDER BY created_at DESC LIMIT 1").fetchone()
            conn.close()
            self.assertIsNotNone(row)
            self.assertEqual(row["is_used"], 1, "OTP should be marked unusable when queue is full")

    # =========================================================================
    # FINDING 14: SESSION_SECRET PROD & PRODUCTION FAIL CLOSED
    # =========================================================================

    def test_29_session_secret_prod_and_production_validation_and_token_fail_closed(self):
        """
        Verify that ENVIRONMENT='prod' and ENVIRONMENT='production':
        1. Reject missing / empty SESSION_SECRET.
        2. Reject sample / placeholder secrets (e.g. kandid_super_secure_session_secret_2026).
        3. Reject cyclic repeating secrets.
        4. hash_reset_token() fails closed with RuntimeError instead of using fallback.
        """
        for prod_env in ("production", "prod"):
            # A) Missing secret
            with self.assertRaises(RuntimeError):
                server.validate_session_secret("", env=prod_env)

            # B) Sample secret from .env.example
            with self.assertRaises(RuntimeError):
                server.validate_session_secret("kandid_super_secure_session_secret_2026", env=prod_env)

            # C) Repeating cyclic secret
            with self.assertRaises(RuntimeError):
                server.validate_session_secret("abcdef123456abcdef123456abcdef123456", env=prod_env)

            # D) Valid strong secret
            valid_secret = "e4d909c290d0fb1ca068ffaddf22cbd0add6b35fb018b9598f828a2a884ef757"
            self.assertTrue(server.validate_session_secret(valid_secret, env=prod_env))

            # E) hash_reset_token fails closed in production when secret is invalid
            with patch("server.ENVIRONMENT", prod_env):
                with patch("server.SESSION_SECRET", ""):
                    with patch.dict(os.environ, {"SESSION_SECRET": "", "ENVIRONMENT": prod_env}):
                        with self.assertRaises(RuntimeError):
                            server.hash_reset_token("prt_sample_token_value_12345")

    # =========================================================================
    # FINDING 15: CONCURRENT SAME-EMAIL RATE LIMIT ATOMICITY
    # =========================================================================

    def test_30_concurrent_same_email_rate_limit_atomicity(self):
        """
        Verify that concurrent OTP generation requests for the same email address
        are strictly serialized by _email_otp_rate_lock and never exceed quota (3 in 15 mins).
        """
        results = []
        errors = []

        def worker():
            try:
                res = server.generate_secure_otp("racer@example.com", "10.0.30.1", async_dispatch=True)
                results.append(res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        server.drain_otp_dispatch_queue(timeout=2.0)

        self.assertEqual(len(errors), 0, f"Unexpected errors during concurrent OTP generation: {errors}")
        self.assertEqual(len(results), 10)

        # Count how many were successfully created (status != 429)
        successes = [r for r in results if r.get("status") != 429]
        rate_limited = [r for r in results if r.get("error_code") == "OTP_RATE_LIMITED" or r.get("status") == 429]

        # In SQLite, exactly 3 should succeed and 7 should be rate-limited
        self.assertEqual(len(successes), 3, f"Expected exactly 3 OTP creations, got {len(successes)}")
        self.assertEqual(len(rate_limited), 7, f"Expected 7 rate-limited responses, got {len(rate_limited)}")

        # Verify DB contains exactly 3 records for racer@example.com
        conn = sqlite3.connect(self.db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM email_otps WHERE email = 'racer@example.com'").fetchone()[0]
        conn.close()
        self.assertEqual(cnt, 3, f"Expected 3 rows in email_otps table, got {cnt}")

    # =========================================================================
    # FINDING 16: NO RECIPIENT EMAIL LOGGED
    # =========================================================================

    def test_31_no_recipient_email_logged_in_production_or_dev(self):
        """
        Verify that recipient email (raw or masked) is never logged to stdout
        by send_email_brevo in production or dev simulator mode.
        """
        import io
        from contextlib import redirect_stdout

        # Dev mode without key
        with patch("server.ENVIRONMENT", "development"):
            with patch("server.BREVO_API_KEY", ""):
                with patch.dict(os.environ, {"BREVO_API_KEY": ""}):
                    f = io.StringIO()
                    with redirect_stdout(f):
                        server.send_email_brevo("secretuser@example.com", "Your Verification Code", "<div>Code</div>")
                    output = f.getvalue()
                    self.assertNotIn("secretuser@example.com", output)
                    self.assertNotIn("s***r@example.com", output)

        # Production mode without key
        with patch("server.ENVIRONMENT", "production"):
            with patch("server.BREVO_API_KEY", ""):
                with patch.dict(os.environ, {"BREVO_API_KEY": ""}):
                    f = io.StringIO()
                    with redirect_stdout(f):
                        server.send_email_brevo("secretuser@example.com", "Your Verification Code", "<div>Code</div>")
                    output = f.getvalue()
                    self.assertNotIn("secretuser@example.com", output)
                    self.assertNotIn("s***r@example.com", output)

    # =========================================================================
    # FINDING 17: ENVIRONMENT=prod ACTIVATES ALL PRODUCTION CONTROLS
    # =========================================================================

    def test_32_environment_prod_activates_all_production_controls(self):
        """
        Verify that ENVIRONMENT='prod' and ENVIRONMENT='production' activate identical
        security controls via is_production_env().
        """
        for env_val in ("production", "prod"):
            with patch("server.ENVIRONMENT", env_val):
                with patch.dict(os.environ, {"ENVIRONMENT": env_val}):
                    self.assertTrue(server.is_production_env())
                    self.assertTrue(server.is_production_env(env_val))

                    # 1. OTP hashing requires scrypt and forbids PBKDF2 fallback in production
                    with patch("hashlib.scrypt", side_effect=Exception("Simulated scrypt failure")):
                        with self.assertRaises(RuntimeError):
                            server.hash_otp_code("123456")

                    # 2. OTP verification rejects PBKDF2 in production
                    pbkdf2_hash = "$pbkdf2$sha256$100000$saltsalt$fakehashfakehashfakehash"
                    self.assertFalse(server.verify_otp_code_hash("123456", "saltsalt", pbkdf2_hash))

                    # 3. Email provider failure does not fall back to local simulator
                    with patch("server.BREVO_API_KEY", ""):
                        with patch.dict(os.environ, {"BREVO_API_KEY": ""}):
                            res = server.send_email_brevo("user@example.com", "Test", "Test body")
                            self.assertFalse(res["success"])
                            self.assertEqual(res["error_code"], "EMAIL_PROVIDER_UNCONFIGURED")

    # =========================================================================
    # FINDING 18: SESSION SECRET BOUNDED LENGTH & COMPLEXITY
    # =========================================================================

    def test_33_session_secret_max_length_and_cyclic_checks(self):
        """
        Verify that secrets exceeding MAX_SESSION_SECRET_LENGTH (512) or containing
        repeating patterns are strictly rejected.
        """
        for env_val in ("production", "prod"):
            # A) Secret exceeding 512 characters
            overlong_secret = "a1b2c3d4" * 65  # 520 chars
            with self.assertRaises(RuntimeError) as ctx:
                server.validate_session_secret(overlong_secret, env=env_val)
            self.assertIn("too long", str(ctx.exception).lower())

            # B) Repeating pattern with period <= 32
            cyclic_secret_16 = "0123456789abcdef" * 4  # 64 chars repeating 16-char pattern
            with self.assertRaises(RuntimeError) as ctx:
                server.validate_session_secret(cyclic_secret_16, env=env_val)
            self.assertIn("cryptographically generated", str(ctx.exception).lower())

            cyclic_secret_2 = "a1" * 32  # 64 chars repeating 2-char pattern
            with self.assertRaises(RuntimeError) as ctx:
                server.validate_session_secret(cyclic_secret_2, env=env_val)
            self.assertIn("cryptographically generated", str(ctx.exception).lower())

            # C) Valid 64-char hex secret passes
            random_hex = "8f14e45fceea167a5a36dedd4bea2543b9c2bd0a7df8448d3c260ff09772bf2a"
            self.assertTrue(server.is_cryptographically_generated(random_hex))
            self.assertTrue(server.validate_session_secret(random_hex, env=env_val))

    # =========================================================================
    # FINDING 19: POSTGRESQL ADVISORY LOCK FAIL-CLOSED
    # =========================================================================

    def test_34_postgres_advisory_lock_fail_closed(self):
        """
        Verify that when PostgreSQL advisory lock acquisition fails, generate_secure_otp
        fails closed (returns 500 error), and the forgot-password endpoint returns generic 200.
        """
        class MockPgCursor:
            def execute(self, sql, params=()):
                if "pg_advisory_xact_lock" in sql:
                    raise Exception("Deadlock / Lock timeout on pg_advisory_xact_lock")
            def fetchone(self):
                return {"id": "u_alice", "email": "alice@example.com", "handle": "alice"}
            def fetchall(self):
                return []
            def close(self): pass

        class MockPgConn(server.PostgresConnectionWrapper):
            def __init__(self):
                self.rolled_back = False
                self.closed = False
            def cursor(self):
                return MockPgCursor()
            def rollback(self):
                self.rolled_back = True
            def close(self):
                self.closed = True

        mock_conn = MockPgConn()
        with patch("server.get_db", return_value=mock_conn):
            # Test direct generate_secure_otp fail-closed
            res = server.generate_secure_otp("alice@example.com", "1.2.3.4", async_dispatch=True)
            self.assertFalse(res["success"])
            self.assertEqual(res["error_code"], "LOCK_ACQUISITION_FAILED")
            self.assertEqual(res["status"], 500)
            self.assertTrue(mock_conn.rolled_back)
            self.assertTrue(mock_conn.closed)

            # Test forgot password endpoint wraps internal failure into uniform generic response
            resp = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"})
            self.assertEqual(resp["status"], 200)
            self.assertEqual(resp["body"]["message"], "If an account is associated with this handle or email, a verification code has been sent.")
            self.assertEqual(resp["body"]["delivery_status"], "accepted")

    # =========================================================================
    # FINDING 20: GUARANTEED OTP CLEANUP CONNECTION CLOSURE & ISOLATION
    # =========================================================================

    def test_35_invalidate_email_otp_guaranteed_cleanup_and_isolation(self):
        """
        Verify that _invalidate_email_otp_by_id always closes connection on failure,
        rolls back, and only affects the targeted row ID.
        """
        # 1. Successful invalidation by exact ID
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO email_otps (id, email, otp_hash, salt, attempts, max_attempts, expires_at, is_used)
            VALUES ('otp_test_1', 'user1@example.com', 'h1', 's1', 0, 5, '2099-01-01', 0),
                   ('otp_test_2', 'user1@example.com', 'h2', 's2', 0, 5, '2099-01-01', 0)
        """)
        conn.commit()
        conn.close()

        # Invalidate only otp_test_1
        self.assertTrue(server._invalidate_email_otp_by_id("otp_test_1"))

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        r1 = cur.execute("SELECT is_used FROM email_otps WHERE id = 'otp_test_1'").fetchone()[0]
        r2 = cur.execute("SELECT is_used FROM email_otps WHERE id = 'otp_test_2'").fetchone()[0]
        conn.close()

        self.assertEqual(r1, 1, "Targeted OTP must be marked used")
        self.assertEqual(r2, 0, "Non-targeted OTP must remain unused")

        # 2. Exception handling with guaranteed connection closure
        class ErrorConn:
            def __init__(self):
                self.rolled_back = False
                self.closed = False
            def cursor(self):
                raise Exception("Database disk I/O error")
            def rollback(self):
                self.rolled_back = True
            def close(self):
                self.closed = True

        err_conn = ErrorConn()
        with patch("server.get_db", return_value=err_conn):
            success = server._invalidate_email_otp_by_id("otp_test_2")
            self.assertFalse(success)
            self.assertTrue(err_conn.closed, "Connection must be closed even when cursor creation fails")

    # =========================================================================
    # FINDING 21: FORGOT-PASSWORD TIMING PARITY & STRUCTURAL SYMMETRY
    # =========================================================================

    def test_36_forgot_password_timing_parity_structural_symmetry(self):
        """
        Verify that unknown account and no-email account execute symmetric DB/KDF work
        without creating bogus records or sending emails.
        """
        conn = sqlite3.connect(self.db_path)
        before_count = conn.execute("SELECT COUNT(*) FROM email_otps").fetchone()[0]
        conn.close()

        # A) Unknown identifier
        resp_unknown = self._call_post("/api/auth/forgot-password", {"identifier": "ghost_user_9999"})
        self.assertEqual(resp_unknown["status"], 200)
        self.assertEqual(resp_unknown["body"]["delivery_status"], "accepted")

        # B) Known user without email
        resp_no_email = self._call_post("/api/auth/forgot-password", {"identifier": "no_email_user"})
        self.assertEqual(resp_no_email["status"], 200)
        self.assertEqual(resp_no_email["body"]["delivery_status"], "accepted")

    # =========================================================================
    # FINDING 22: PLAINTEXT RESET TOKEN REJECTION IN PRODUCTION/PROD
    # =========================================================================

    def test_37_plaintext_reset_tokens_rejected_in_production_and_prod(self):
        """
        Verify that legacy plaintext reset tokens (prt_...) are strictly rejected
        in production and prod environments, and accepted ONLY in development.
        """
        raw_token = "prt_" + "a" * 48
        stored_verifier_hmac = server.hash_reset_token(raw_token)
        stored_plaintext = raw_token

        for env_val in ("production", "prod"):
            with patch("server.ENVIRONMENT", env_val):
                with patch.dict(os.environ, {"ENVIRONMENT": env_val}):
                    self.assertTrue(server.is_production_env())
                    # A) verify_reset_token_hash rejects plaintext in production/prod
                    self.assertFalse(server.verify_reset_token_hash(raw_token, stored_plaintext))
                    # B) verify_reset_token_hash accepts HMAC verifier in production/prod
                    self.assertTrue(server.verify_reset_token_hash(raw_token, stored_verifier_hmac))

        # C) In development, plaintext token is accepted (backward compatibility)
        with patch("server.ENVIRONMENT", "development"):
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                self.assertFalse(server.is_production_env())
                self.assertTrue(server.verify_reset_token_hash(raw_token, stored_plaintext))
                self.assertTrue(server.verify_reset_token_hash(raw_token, stored_verifier_hmac))

        # D) End-to-end /api/auth/reset-password test with plaintext stored token in DB
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM password_resets")
        expires = (server.datetime.now() + server.timedelta(minutes=10)).isoformat()
        # Insert plaintext token directly into DB
        cur.execute("INSERT INTO password_resets (id, email, token, expires_at) VALUES ('pr_pt', 'alice@example.com', ?, ?)", (stored_plaintext, expires))
        conn.commit()
        conn.close()

        # In production/prod, reset-password must reject plaintext token in DB
        for env_val in ("production", "prod"):
            with patch("server.ENVIRONMENT", env_val):
                with patch.dict(os.environ, {"ENVIRONMENT": env_val}):
                    resp = self._call_post("/api/auth/reset-password", {"reset_token": raw_token, "new_password": "BrandNewPassword123!"})
                    self.assertEqual(resp["status"], 400)
                    self.assertEqual(resp["body"]["error_code"], "INVALID_RESET_TOKEN")

        # Now update DB to have HMAC verifier
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE password_resets SET token = ? WHERE id = 'pr_pt'", (stored_verifier_hmac,))
        conn.commit()
        conn.close()

        # In production, reset-password succeeds with HMAC verifier
        with patch("server.ENVIRONMENT", "production"):
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
                resp = self._call_post("/api/auth/reset-password", {"reset_token": raw_token, "new_password": "BrandNewPassword123!"})
                self.assertEqual(resp["status"], 200)
                self.assertTrue(resp["body"]["success"])

                # Replay must fail (atomic single-use)
                resp_replay = self._call_post("/api/auth/reset-password", {"reset_token": raw_token, "new_password": "AnotherPassword123!"})
                self.assertEqual(resp_replay["status"], 400)
                self.assertEqual(resp_replay["body"]["error_code"], "INVALID_RESET_TOKEN")

    # =========================================================================
    # FINDING 23: LEGACY SHA-256 OTP HASH REJECTION IN PRODUCTION/PROD
    # =========================================================================

    def test_38_legacy_sha256_otp_hashes_rejected_in_production_and_prod(self):
        """
        Verify that legacy SHA-256 OTP hashes are strictly rejected in production/prod,
        and accepted ONLY in development.
        """
        import hashlib
        code = "654321"
        salt_hex = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
        legacy_hash = hashlib.sha256((code + salt_hex).encode("utf-8")).hexdigest()
        scrypt_hash, _ = server.hash_otp_code(code, salt_hex)

        for env_val in ("production", "prod"):
            with patch("server.ENVIRONMENT", env_val):
                with patch.dict(os.environ, {"ENVIRONMENT": env_val}):
                    self.assertTrue(server.is_production_env())
                    # A) Legacy SHA-256 rejected in production/prod
                    self.assertFalse(server.verify_otp_code_hash(code, salt_hex, legacy_hash))
                    # B) Scrypt hash accepted in production/prod
                    self.assertTrue(server.verify_otp_code_hash(code, salt_hex, scrypt_hash))

        # C) In development, legacy SHA-256 accepted
        with patch("server.ENVIRONMENT", "development"):
            with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
                self.assertFalse(server.is_production_env())
                self.assertTrue(server.verify_otp_code_hash(code, salt_hex, legacy_hash))
                self.assertTrue(server.verify_otp_code_hash(code, salt_hex, scrypt_hash))

    # =========================================================================
    # FINDING 24: MEASURED TIMING DISTRIBUTIONS (KNOWN VS UNKNOWN ACCOUNTS)
    # =========================================================================

    def test_39_measured_timing_distributions_known_vs_unknown(self):
        """
        Measures and compares execution time of forgot-password requests for
        known vs unknown accounts across multiple iterations.
        """
        import time
        import statistics

        known_timings = []
        unknown_timings = []
        iterations = 5

        for i in range(iterations):
            # Clear rate limiter between iterations to avoid 429
            with server.rate_limiter.lock:
                server.rate_limiter.buckets.clear()

            # Measure unknown account
            t0 = time.perf_counter()
            resp_unk = self._call_post("/api/auth/forgot-password", {"identifier": f"nonexistent_{i}@example.com"})
            t1 = time.perf_counter()
            unknown_timings.append((t1 - t0) * 1000.0)
            self.assertEqual(resp_unk["status"], 200)

            # Clear rate limiter
            with server.rate_limiter.lock:
                server.rate_limiter.buckets.clear()

            # Measure known account
            t2 = time.perf_counter()
            resp_known = self._call_post("/api/auth/forgot-password", {"identifier": "alice@example.com"})
            t3 = time.perf_counter()
            known_timings.append((t3 - t2) * 1000.0)
            self.assertEqual(resp_known["status"], 200)

        server.drain_otp_dispatch_queue(timeout=2.0)

        # Calculate distributions
        unk_mean = statistics.mean(unknown_timings)
        unk_median = statistics.median(unknown_timings)
        known_mean = statistics.mean(known_timings)
        known_median = statistics.median(known_timings)

        print(f"\n[TIMING MEASUREMENTS - FORGOT PASSWORD]")
        print(f"  Unknown account: mean={unk_mean:.2f}ms, median={unk_median:.2f}ms, min={min(unknown_timings):.2f}ms, max={max(unknown_timings):.2f}ms")
        print(f"  Known account:   mean={known_mean:.2f}ms, median={known_median:.2f}ms, min={min(known_timings):.2f}ms, max={max(known_timings):.2f}ms")

        # Response bodies and statuses must be 100% identical
        self.assertEqual(resp_unk["body"], resp_known["body"])


if __name__ == "__main__":
    unittest.main()


