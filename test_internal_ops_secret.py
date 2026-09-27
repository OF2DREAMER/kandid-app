#!/usr/bin/env python3
"""
Tests for B2-SEC-04: Harden Internal Operator Secret.

Requirements covered:
- anonymous + no header -> denied
- anonymous + wrong secret -> denied
- anonymous + correct configured secret -> passes auth gate
- former literal #1 (kandid_internal_ops_secret_2026) -> denied
- former literal #2 (kandid_ops_key) -> denied
- empty INTERNAL_OPS_SECRET -> fail closed
- admin role + no header -> allowed
- founder role + no header -> allowed
- ordinary user + wrong header -> denied
- development vs production -> no dev bypass
- source scan: no hardcoded old literals in server.py
- helper referenced by all six sites
- end-to-end HTTP tests against all six endpoints
"""

import os
import sys
import json
import shutil
import socket
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler, internal_ops_authorized

TEST_OPS_SECRET = "test_ops_secret_token_alpha_2026_xyz"
FORMER_LITERAL_1 = "kandid_internal_ops_secret_2026"
FORMER_LITERAL_2 = "kandid_ops_key"

SIX_ENDPOINTS = [
    "/api/internal/database/integrity",
    "/api/internal/community/ops",
    "/api/internal/config/status",
    "/api/internal/database/backup-readiness",
    "/api/graph/funnel",
    "/api/internal/growth/metrics",
]


class TestInternalOpsSecretUnit(unittest.TestCase):
    """Unit tests for internal_ops_authorized helper function."""

    def setUp(self):
        self._orig_secret = server.INTERNAL_OPS_SECRET
        server.INTERNAL_OPS_SECRET = TEST_OPS_SECRET

    def tearDown(self):
        server.INTERNAL_OPS_SECRET = self._orig_secret

    def test_anonymous_no_header_denied(self):
        headers = {}
        self.assertFalse(internal_ops_authorized(headers, None))

    def test_anonymous_empty_header_denied(self):
        headers = {"X-Internal-Secret": ""}
        self.assertFalse(internal_ops_authorized(headers, None))
        headers = {"X-Internal-Secret": "   "}
        self.assertFalse(internal_ops_authorized(headers, None))

    def test_anonymous_wrong_secret_denied(self):
        headers = {"X-Internal-Secret": "wrong_secret_12345"}
        self.assertFalse(internal_ops_authorized(headers, None))

    def test_former_literal_1_denied(self):
        headers = {"X-Internal-Secret": FORMER_LITERAL_1}
        self.assertFalse(internal_ops_authorized(headers, None))

    def test_former_literal_2_denied(self):
        headers = {"X-Internal-Secret": FORMER_LITERAL_2}
        self.assertFalse(internal_ops_authorized(headers, None))

    def test_anonymous_correct_configured_secret_allowed(self):
        headers = {"X-Internal-Secret": TEST_OPS_SECRET}
        self.assertTrue(internal_ops_authorized(headers, None))
        # With leading/trailing whitespace in header (should be stripped)
        headers = {"X-Internal-Secret": f"  {TEST_OPS_SECRET}  "}
        self.assertTrue(internal_ops_authorized(headers, None))

    def test_empty_configured_secret_fails_closed(self):
        server.INTERNAL_OPS_SECRET = ""
        # When secret is empty, even matching empty header or former literals fails
        self.assertFalse(internal_ops_authorized({}, None))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": ""}, None))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": TEST_OPS_SECRET}, None))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_1}, None))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_2}, None))

    def test_admin_role_no_header_allowed(self):
        admin_user = {"id": "u_admin", "role": "admin"}
        self.assertTrue(internal_ops_authorized({}, admin_user))
        self.assertTrue(internal_ops_authorized({"X-Internal-Secret": ""}, admin_user))
        self.assertTrue(internal_ops_authorized({"X-Internal-Secret": "wrong"}, admin_user))

    def test_founder_role_no_header_allowed(self):
        founder_user = {"id": "u_founder", "role": "founder"}
        self.assertTrue(internal_ops_authorized({}, founder_user))
        self.assertTrue(internal_ops_authorized({"X-Internal-Secret": ""}, founder_user))
        self.assertTrue(internal_ops_authorized({"X-Internal-Secret": "wrong"}, founder_user))

    def test_ordinary_user_wrong_header_denied(self):
        student_user = {"id": "u_student", "role": "student"}
        self.assertFalse(internal_ops_authorized({}, student_user))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": ""}, student_user))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": "wrong"}, student_user))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_1}, student_user))
        self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_2}, student_user))

    def test_ordinary_user_correct_header_allowed(self):
        student_user = {"id": "u_student", "role": "student"}
        headers = {"X-Internal-Secret": TEST_OPS_SECRET}
        self.assertTrue(internal_ops_authorized(headers, student_user))

    def test_development_vs_production_no_dev_bypass(self):
        for env in ("development", "production", "test"):
            orig_env = server.ENVIRONMENT
            try:
                server.ENVIRONMENT = env
                # Anonymous with no header or wrong header must be denied in ALL environments
                self.assertFalse(internal_ops_authorized({}, None), f"Failed in {env}")
                self.assertFalse(internal_ops_authorized({"X-Internal-Secret": "wrong"}, None), f"Failed in {env}")
                self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_1}, None), f"Failed in {env}")
                self.assertFalse(internal_ops_authorized({"X-Internal-Secret": FORMER_LITERAL_2}, None), f"Failed in {env}")
                # Correct secret must be allowed in ALL environments
                self.assertTrue(internal_ops_authorized({"X-Internal-Secret": TEST_OPS_SECRET}, None), f"Failed in {env}")
            finally:
                server.ENVIRONMENT = orig_env


class TestSourceLevelRegression(unittest.TestCase):
    """Static analysis and source inspection tests."""

    def test_former_literals_do_not_exist_in_server_py(self):
        server_path = os.path.join(PROJECT_DIR, "server.py")
        with open(server_path, "r", encoding="utf-8") as f:
            src = f.read()

        self.assertNotIn(
            FORMER_LITERAL_1,
            src,
            f"Former literal '{FORMER_LITERAL_1}' must not appear in server.py",
        )
        self.assertNotIn(
            FORMER_LITERAL_2,
            src,
            f"Former literal '{FORMER_LITERAL_2}' must not appear in server.py",
        )

    def test_env_example_contains_empty_internal_ops_secret(self):
        env_example_path = os.path.join(PROJECT_DIR, ".env.example")
        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("INTERNAL_OPS_SECRET=", content)
        # Verify it has no hardcoded secret value
        lines = [line.strip() for line in content.splitlines() if line.strip().startswith("INTERNAL_OPS_SECRET=")]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "INTERNAL_OPS_SECRET=", "INTERNAL_OPS_SECRET in .env.example must be empty")

    def test_all_six_endpoints_reference_helper(self):
        server_path = os.path.join(PROJECT_DIR, "server.py")
        with open(server_path, "r", encoding="utf-8") as f:
            src = f.read()

        self.assertIn("def internal_ops_authorized", src)

        for endpoint in SIX_ENDPOINTS:
            self.assertIn(f'path == "{endpoint}"', src, f"Endpoint {endpoint} must exist in server.py")

        # Count occurrences of internal_ops_authorized calls in server.py
        occurrences = src.count("internal_ops_authorized(")
        # 1 definition + 6 call sites = at least 7
        self.assertGreaterEqual(occurrences, 7, f"Expected at least 7 occurrences of internal_ops_authorized in server.py, found {occurrences}")


class TestInternalOpsHttpEndpoints(unittest.TestCase):
    """End-to-end HTTP tests against all six endpoints."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec04_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        cls._orig_secret = server.INTERNAL_OPS_SECRET

        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_b2sec04.db")
        server.INTERNAL_OPS_SECRET = TEST_OPS_SECRET
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        # Seed admin, founder, and student users
        cls.ADMIN_TOKEN = "token_admin_test_secret"
        cls.FOUNDER_TOKEN = "token_founder_test_secret"
        cls.STUDENT_TOKEN = "token_student_test_secret"

        cursor.execute(
            "INSERT INTO users (id, email, handle, name, role, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u_admin_sec", "admin@example.test", "admin_sec", "Admin User", "admin", "h", "s"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, role, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u_founder_sec", "founder@example.test", "founder_sec", "Founder User", "founder", "h", "s"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, role, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u_student_sec", "student@example.test", "student_sec", "Student User", "student", "h", "s"),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_adm", cls.ADMIN_TOKEN, "u_admin_sec", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_fnd", cls.FOUNDER_TOKEN, "u_founder_sec", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_stu", cls.STUDENT_TOKEN, "u_student_sec", future_iso, now_iso),
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        server.INTERNAL_OPS_SECRET = cls._orig_secret
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, token=None, ops_secret=None, method="GET", body=None):
        s1, s2 = socket.socketpair()

        class DummyServer:
            pass

        def run_handler():
            try:
                KandidHandler(s1, ("127.0.0.1", 12345), DummyServer())
            except Exception:
                pass
            finally:
                try:
                    s1.close()
                except Exception:
                    pass

        t = threading.Thread(target=run_handler)
        t.start()

        body_bytes = b""
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body_bytes = body.encode("utf-8")

        req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\n"
        if ops_secret is not None:
            req += f"X-Internal-Secret: {ops_secret}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "\r\n"

        s2.settimeout(5.0)
        s2.sendall(req.encode("utf-8") + body_bytes)
        try:
            s2.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        chunks = []
        while True:
            try:
                chunk = s2.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        s2.close()
        t.join(timeout=3.0)

        raw = b"".join(chunks).decode("utf-8", errors="replace")
        lines = raw.split("\r\n")
        status_line = lines[0] if lines else ""
        status = int(status_line.split(" ")[1]) if " " in status_line else 0
        idx = raw.find("\r\n\r\n")
        body_str = raw[idx + 4 :] if idx != -1 else ""
        try:
            data = json.loads(body_str)
        except Exception:
            data = {}
        return status, data

    def test_anonymous_no_header_denied_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint)
            if endpoint == "/api/internal/growth/metrics":
                self.assertEqual(status, 401, f"{endpoint} expected 401 when anonymous with no header")
            else:
                self.assertEqual(status, 403, f"{endpoint} expected 403 when anonymous with no header")
                self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

    def test_anonymous_wrong_header_denied_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, ops_secret="wrong_secret_xyz")
            if endpoint == "/api/internal/growth/metrics":
                self.assertEqual(status, 401, f"{endpoint} expected 401 with wrong secret")
            else:
                self.assertEqual(status, 403, f"{endpoint} expected 403 with wrong secret")
                self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

    def test_anonymous_former_literal_1_denied_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, ops_secret=FORMER_LITERAL_1)
            if endpoint == "/api/internal/growth/metrics":
                self.assertEqual(status, 401, f"{endpoint} expected 401 with former literal 1")
            else:
                self.assertEqual(status, 403, f"{endpoint} expected 403 with former literal 1")
                self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

    def test_anonymous_former_literal_2_denied_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, ops_secret=FORMER_LITERAL_2)
            if endpoint == "/api/internal/growth/metrics":
                self.assertEqual(status, 401, f"{endpoint} expected 401 with former literal 2")
            else:
                self.assertEqual(status, 403, f"{endpoint} expected 403 with former literal 2")
                self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

    def test_anonymous_correct_secret_passes_auth_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, ops_secret=TEST_OPS_SECRET)
            # The request must pass the authorization gate (status is NOT 401/403)
            self.assertNotIn(
                status,
                (401, 403),
                f"{endpoint} failed authorization gate with correct secret (status {status}: {data})",
            )
            self.assertNotEqual(data.get("code"), "AUTH_FORBIDDEN")
            # For clean endpoints without retired table dependencies, verify 200 success
            if endpoint in (
                "/api/internal/database/integrity",
                "/api/internal/config/status",
                "/api/internal/database/backup-readiness",
                "/api/graph/funnel",
            ):
                self.assertEqual(status, 200, f"{endpoint} expected 200 on authorized request")
                self.assertTrue(data.get("success"), f"{endpoint} expected success: True")

    def test_admin_token_no_header_passes_auth_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, token=self.ADMIN_TOKEN)
            self.assertNotIn(
                status,
                (401, 403),
                f"{endpoint} failed authorization for admin role without header (status {status}: {data})",
            )
            self.assertNotEqual(data.get("code"), "AUTH_FORBIDDEN")
            if endpoint in (
                "/api/internal/database/integrity",
                "/api/internal/config/status",
                "/api/internal/database/backup-readiness",
                "/api/graph/funnel",
            ):
                self.assertEqual(status, 200, f"{endpoint} expected 200 for admin user")
                self.assertTrue(data.get("success"), f"{endpoint} expected success: True")

    def test_founder_token_no_header_passes_auth_all_six(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, token=self.FOUNDER_TOKEN)
            self.assertNotIn(
                status,
                (401, 403),
                f"{endpoint} failed authorization for founder role without header (status {status}: {data})",
            )
            self.assertNotEqual(data.get("code"), "AUTH_FORBIDDEN")
            if endpoint in (
                "/api/internal/database/integrity",
                "/api/internal/config/status",
                "/api/internal/database/backup-readiness",
                "/api/graph/funnel",
            ):
                self.assertEqual(status, 200, f"{endpoint} expected 200 for founder user")
                self.assertTrue(data.get("success"), f"{endpoint} expected success: True")

    def test_student_token_wrong_header_denied_operator_privileges(self):
        for endpoint in SIX_ENDPOINTS:
            status, data = self._request(endpoint, token=self.STUDENT_TOKEN, ops_secret=FORMER_LITERAL_1)
            if endpoint == "/api/internal/growth/metrics":
                # Ordinary student does NOT get admin funnel; gets personal growth
                self.assertEqual(status, 200)
                self.assertNotIn("funnel", data)
                self.assertIn("personal_growth", data)
            else:
                self.assertEqual(status, 403, f"{endpoint} allowed student with former literal")
                self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

    def test_empty_config_fails_closed_http(self):
        server.INTERNAL_OPS_SECRET = ""
        try:
            for endpoint in SIX_ENDPOINTS:
                # Passing former literal with empty config must be rejected
                status, data = self._request(endpoint, ops_secret=FORMER_LITERAL_1)
                if endpoint == "/api/internal/growth/metrics":
                    self.assertEqual(status, 401)
                else:
                    self.assertEqual(status, 403)
                    self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")

                # Passing test secret with empty config must be rejected
                status, data = self._request(endpoint, ops_secret=TEST_OPS_SECRET)
                if endpoint == "/api/internal/growth/metrics":
                    self.assertEqual(status, 401)
                else:
                    self.assertEqual(status, 403)
                    self.assertEqual(data.get("code"), "AUTH_FORBIDDEN")
        finally:
            server.INTERNAL_OPS_SECRET = TEST_OPS_SECRET


if __name__ == "__main__":
    unittest.main()
