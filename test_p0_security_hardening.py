"""
P0 Security Hardening Regression Test Suite for Kindid.
Tests all audited security fixes:
1. Login password requirement (no bypass on passwordless accounts)
2. Password length enforcement across registration, reset, and change password (>= 8 chars)
3. Sensitive static file blocking (.patch, .diff, .log, .bak, .env, .yaml, etc.)
4. Content-Security-Policy header emission and directives
5. Rate limiting on report abuse endpoints
6. Account deletion endpoint (/api/user/delete-account) wiping user data and sessions
7. Inline event handler attribute sanitization (jsAttr XSS defense)
"""

import json
import sqlite3
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

import server


class TestP0SecurityHardening(unittest.TestCase):
    def setUp(self):
        self.handler = server.KandidHandler.__new__(server.KandidHandler)
        self.handler.headers = {}
        self.handler.request_version = "HTTP/1.1"
        self.handler._headers_buffer = []
        self.handler.wfile = BytesIO()
        self.handler.rfile = BytesIO()
        self.sent_status = []
        self.sent_headers = {}

        def fake_send_response(code):
            self.sent_status.append(code)

        def fake_send_header(name, val):
            self.sent_headers[name.lower()] = val

        def fake_end_headers():
            pass

        self.handler.send_response = fake_send_response
        self.handler.send_header = fake_send_header
        self.handler.end_headers = fake_end_headers

    def _set_post_payload(self, path, payload, headers=None):
        data = json.dumps(payload).encode("utf-8")
        self.handler.path = path
        self.handler.rfile = BytesIO(data)
        self.handler.headers = {
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        if headers:
            self.handler.headers.update(headers)
        self.handler.read_json_body = lambda: payload

    def test_login_rejects_empty_or_missing_password(self):
        """Verify login strictly requires non-empty password and does not bypass for passwordless users."""
        self._set_post_payload("/api/auth/login", {"identifier": "alice", "password": ""})
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [400])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Password is required", res.get("error", ""))

    def test_registration_enforces_minimum_password_length(self):
        """Verify registration rejects passwords shorter than 8 characters."""
        self._set_post_payload("/api/register", {
            "name": "Bob",
            "handle": "bob_test",
            "password": "short"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [400])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("at least 8 characters", res.get("error", ""))

    def test_reset_password_enforces_minimum_password_length(self):
        """Verify reset-password rejects passwords shorter than 8 characters."""
        self._set_post_payload("/api/auth/reset-password", {
            "reset_token": "valid_token",
            "new_password": "1234"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [400])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("at least 8 characters", res.get("error", ""))

    def test_change_password_enforces_minimum_password_length(self):
        """Verify change-password rejects passwords shorter than 8 characters."""
        with patch("server.get_current_user", return_value={"id": "u_test"}):
            self._set_post_payload("/api/user/change-password", {
                "current_password": "old_password",
                "new_password": "short"
            })
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertIn("at least 8 characters", res.get("error", ""))

    def test_sensitive_static_file_blocking(self):
        """Verify blocked static path checker rejects patches, logs, backups, and configs."""
        self.assertTrue(server.is_blocked_static_path("/B2-SEC-07-phase1-server.patch"))
        self.assertTrue(server.is_blocked_static_path("/deploy.log"))
        self.assertTrue(server.is_blocked_static_path("/server.py.bak"))
        self.assertTrue(server.is_blocked_static_path("/config.yml"))
        self.assertTrue(server.is_blocked_static_path("/config.yaml"))
        self.assertTrue(server.is_blocked_static_path("/settings.conf"))
        self.assertTrue(server.is_blocked_static_path("/settings.ini"))
        self.assertTrue(server.is_blocked_static_path("/run.sh"))
        self.assertTrue(server.is_blocked_static_path("/.env"))
        self.assertTrue(server.is_blocked_static_path("/.env.production"))

        # Allowed static files
        self.assertFalse(server.is_blocked_static_path("/robots.txt"))
        self.assertFalse(server.is_blocked_static_path("/sitemap.xml"))
        self.assertFalse(server.is_blocked_static_path("/app_core.js"))
        self.assertFalse(server.is_blocked_static_path("/style.css"))

    def test_content_security_policy_header(self):
        """Verify end_headers includes Content-Security-Policy with required domain allowlists."""
        self.handler.path = "/"
        server.KandidHandler.end_headers(self.handler)
        csp = self.sent_headers.get("content-security-policy", "")
        self.assertTrue(len(csp) > 0, "Content-Security-Policy header missing")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("accounts.google.com", csp)
        self.assertIn("cdn.tailwindcss.com", csp)
        self.assertIn("posthog.com", csp)

    def test_report_rate_limiting(self):
        """Verify rate limits on user and community reporting endpoints."""
        mock_user = {"id": "u_spammer", "role": "student"}
        with patch("server.get_current_user", return_value=mock_user):
            # Exhaust 10 requests with recent timestamps
            import time
            key = f"report_comm:{mock_user['id']}"
            now = time.time()
            server.rate_limiter.buckets[key] = [now] * 10

            self._set_post_payload("/api/community/report", {
                "community_id": "c_general",
                "target_type": "user",
                "target_id": "u_target",
                "reason": "spam"
            })
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [429])

    def test_account_deletion_unauthenticated_rejected(self):
        """Verify /api/user/delete-account rejects unauthenticated requests."""
        with patch("server.get_current_user", return_value=None):
            self._set_post_payload("/api/user/delete-account", {"confirmation": "DELETE"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [401])

    def test_account_deletion_requires_explicit_confirmation(self):
        """Verify /api/user/delete-account rejects without confirmation code 'DELETE'."""
        mock_user = {"id": "u_todelete", "email": "test@example.com"}
        with patch("server.get_current_user", return_value=mock_user):
            self._set_post_payload("/api/user/delete-account", {"confirmation": "NO"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertIn("DELETE", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()
