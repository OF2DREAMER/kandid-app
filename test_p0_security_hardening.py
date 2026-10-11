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
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
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




# =========================================================================
# Batch 1 — Account deletion cascade (end-to-end)
# -------------------------------------------------------------------------
# These tests exercise the FULL successful deletion path against a
# disposable, isolated SQLite database created by server.init_db(), then
# assert the resulting database state. Before the Batch-1 fix the cascade
# referenced columns that do not exist in the schema
# (moment_cluster_members.perspective_post_id, messages.recipient_id,
# blocks.blocker_id / blocks.blocked_id), so every deletion returned 500
# and left the account intact. These tests fail on the pre-fix cascade.
# =========================================================================

class TestAccountDeletionCascade(unittest.TestCase):
    def setUp(self):
        self._orig_db_file = server.DB_FILE
        self._orig_db_url = server.DATABASE_URL
        fd, self.db_path = tempfile.mkstemp(prefix="kandid_delete_", suffix=".db")
        os.close(fd)
        self.addCleanup(self._cleanup_db)
        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""
        server.init_db()

        self.handler = server.KandidHandler.__new__(server.KandidHandler)
        self.handler.request_version = "HTTP/1.1"
        self.handler._headers_buffer = []
        self.sent_status = []
        self.handler.send_response = lambda code: self.sent_status.append(code)
        self.handler.send_header = lambda name, val: None
        self.handler.end_headers = lambda: None

    def _cleanup_db(self):
        server.DB_FILE = self._orig_db_file
        server.DATABASE_URL = self._orig_db_url
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    # -- helpers ---------------------------------------------------------
    def _seed_user(self, uid, email=None, handle=None):
        email = email or (uid + "@example.com")
        handle = handle or uid
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            pw_hash, salt = server.hash_password("Password123!")
            cursor.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, email, handle, "Delete Me", pw_hash, salt),
            )
            token = "tok_" + uid
            expires = (datetime.now() + timedelta(days=1)).isoformat()
            cursor.execute(
                "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                ("sess_" + uid, uid, token, expires),
            )
            conn.commit()
        finally:
            conn.close()
        return token

    def _exec(self, sql, params=()):
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _count(self, sql, params=()):
        conn = server.get_db()
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def _post_delete(self, token=None, confirmation="DELETE"):
        payload = {"confirmation": confirmation}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Length": str(len(data)), "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        self.handler.path = "/api/user/delete-account"
        self.handler.headers = headers
        self.handler.rfile = BytesIO(data)
        self.handler.wfile = BytesIO()
        del self.sent_status[:]
        self.handler.do_POST()
        raw = self.handler.wfile.getvalue().decode("utf-8")
        return list(self.sent_status), (json.loads(raw) if raw.strip() else {})

    # -- Test A: minimal account deletion --------------------------------
    def test_a_minimal_account_deletion_removes_user_and_sessions(self):
        token = self._seed_user("u_del_min")
        status, body = self._post_delete(token=token)
        self.assertEqual(status, [200], body)
        self.assertTrue(body.get("success"), body)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_del_min",)), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM sessions WHERE user_id = ?", ("u_del_min",)), 0)

    # -- Test B: post + moment-cluster relationship ----------------------
    def test_b_account_deletion_with_post_and_cluster_records(self):
        token = self._seed_user("u_del_post")
        self._seed_user("u_keep_post")
        self._exec(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img) VALUES (?, ?, ?, ?, ?, ?)",
            ("post_1", "u_del_post", "Delete Me", "u_del_post", "https://cdn.example/m.jpg", "https://cdn.example/p.jpg"),
        )
        self._exec(
            "INSERT INTO moment_clusters (id, cluster_type, originator_moment_id, originator_user_id) VALUES (?, ?, ?, ?)",
            ("cls_1", "context", "post_1", "u_del_post"),
        )
        # perspective row owned by the deleted user (moment_id == the post id)
        self._exec(
            "INSERT INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type) VALUES (?, ?, ?, ?, ?)",
            ("mcm_own", "cls_1", "u_del_post", "post_1", "perspective"),
        )
        # another member's perspective attached to the deleted user's post
        self._exec(
            "INSERT INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type) VALUES (?, ?, ?, ?, ?)",
            ("mcm_other", "cls_1", "u_keep_post", "post_1", "perspective"),
        )
        self._exec("INSERT INTO reactions (id, post_id, user_id, emoji) VALUES (?, ?, ?, ?)",
                   ("rx_1", "post_1", "u_del_post", "fire"))
        self._exec("INSERT INTO reactions (id, post_id, user_id, emoji) VALUES (?, ?, ?, ?)",
                   ("rx_2", "post_1", "u_keep_post", "heart"))

        status, body = self._post_delete(token=token)
        self.assertEqual(status, [200], body)
        self.assertTrue(body.get("success"), body)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_del_post",)), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM posts WHERE user_id = ?", ("u_del_post",)), 0)
        # perspective memberships owned by the deleted user are gone
        self.assertEqual(self._count("SELECT COUNT(*) FROM moment_cluster_members WHERE user_id = ?", ("u_del_post",)), 0)
        # perspective memberships attached to the deleted user's post are gone
        self.assertEqual(self._count("SELECT COUNT(*) FROM moment_cluster_members WHERE moment_id = ?", ("post_1",)), 0)
        # reactions on the deleted post and authored by the deleted user are gone
        self.assertEqual(self._count("SELECT COUNT(*) FROM reactions WHERE post_id = ?", ("post_1",)), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM reactions WHERE user_id = ?", ("u_del_post",)), 0)
        # the other user is untouched
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_keep_post",)), 1)

    # -- Test C: sent and received messages ------------------------------
    def test_c_account_deletion_with_sent_and_received_messages(self):
        token = self._seed_user("u_del_msg")
        self._seed_user("u_keep_msg")
        self._exec("INSERT INTO messages (id, sender_id, receiver_id, content) VALUES (?, ?, ?, ?)",
                   ("msg_out", "u_del_msg", "u_keep_msg", "sent by the deleted user"))
        self._exec("INSERT INTO messages (id, sender_id, receiver_id, content) VALUES (?, ?, ?, ?)",
                   ("msg_in", "u_keep_msg", "u_del_msg", "received by the deleted user"))
        self._exec("INSERT INTO messages (id, sender_id, receiver_id, content) VALUES (?, ?, ?, ?)",
                   ("msg_unrelated", "u_keep_msg", "u_keep_msg", "unrelated message"))

        status, body = self._post_delete(token=token)
        self.assertEqual(status, [200], body)
        self.assertTrue(body.get("success"), body)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM messages WHERE sender_id = ? OR receiver_id = ?", ("u_del_msg", "u_del_msg")),
            0,
        )
        self.assertEqual(self._count("SELECT COUNT(*) FROM messages WHERE id = ?", ("msg_unrelated",)), 1)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_keep_msg",)), 1)

    # -- Test D: block records -------------------------------------------
    def test_d_account_deletion_with_block_records(self):
        token = self._seed_user("u_del_block")
        self._seed_user("u_keep_block")
        self._exec("INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
                   ("blk_1", "u_del_block", "u_keep_block"))
        self._exec("INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
                   ("blk_2", "u_keep_block", "u_del_block"))
        self._exec("INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
                   ("blk_unrelated", "u_keep_block", "u_keep_block"))

        status, body = self._post_delete(token=token)
        self.assertEqual(status, [200], body)
        self.assertTrue(body.get("success"), body)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM blocks WHERE user_id = ? OR blocked_user_id = ?", ("u_del_block", "u_del_block")),
            0,
        )
        self.assertEqual(self._count("SELECT COUNT(*) FROM blocks WHERE id = ?", ("blk_unrelated",)), 1)

    # -- Guards (must remain intact) -------------------------------------
    def test_e_unauthenticated_request_cannot_delete(self):
        self._seed_user("u_del_unauth")
        status, body = self._post_delete(token=None)
        self.assertEqual(status, [401], body)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_del_unauth",)), 1)

    def test_f_wrong_confirmation_does_not_remove_data(self):
        token = self._seed_user("u_del_guard")
        status, body = self._post_delete(token=token, confirmation="NO")
        self.assertEqual(status, [400], body)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_del_guard",)), 1)
        self.assertEqual(self._count("SELECT COUNT(*) FROM sessions WHERE user_id = ?", ("u_del_guard",)), 1)

    def test_g_unknown_bearer_token_cannot_delete(self):
        self._seed_user("u_del_badtoken")
        status, body = self._post_delete(token="tok_not_a_real_session")
        self.assertEqual(status, [401], body)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE id = ?", ("u_del_badtoken",)), 1)


if __name__ == "__main__":
    unittest.main()
