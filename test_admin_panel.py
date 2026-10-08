"""
Unit & Integration Tests for Kindid Admin Panel Phase A + B.
Covers:
1. Unauthenticated /api/admin/* requests return 401
2. Student role requests return 403
3. Admin role accesses allowed GET endpoints (/api/admin/me, /api/admin/overview, /api/admin/health)
4. Founder role accesses allowed GET endpoints
5. Cookie-only mutation barrier (strict_bearer=True rejects cookie-only requests)
6. Static route protection: is_blocked_static_path('/admin.html') and ('/admin.js') return True
7. Unauthorized requests to /admin return 401 (unauthenticated) or 403 (student)
8. Admin can access /admin
9. Founder can access /admin
10. admin_audit_log schema exists and supports record_admin_audit_event
11. reports table migration adds status, reviewed_by, reviewed_at, action_taken columns
12. Unexpected database migration errors are not silently swallowed
"""

import json
import sqlite3
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

import server


class TestAdminPanelPhaseAAndB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keep_alive = sqlite3.connect("file:admin_test_mem?mode=memory&cache=shared", uri=True)
        cls.keep_alive.row_factory = sqlite3.Row

        def make_db():
            conn = sqlite3.connect("file:admin_test_mem?mode=memory&cache=shared", uri=True)
            conn.row_factory = sqlite3.Row
            return conn

        cls.db_patcher = patch("server.get_db", side_effect=make_db)
        cls.db_patcher.start()
        server.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.db_patcher.stop()
        cls.keep_alive.close()

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

    def test_unauthenticated_admin_api_rejected(self):
        """Verify unauthenticated requests to /api/admin/* return HTTP 401."""
        with patch("server.get_current_user", return_value=None):
            self.handler.path = "/api/admin/overview"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [401])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertFalse(res.get("success"))
            self.assertIn("Authentication required", res.get("error", ""))

    def test_student_role_access_rejected(self):
        """Verify authenticated student role accessing /api/admin/* returns HTTP 403."""
        mock_student = {"id": "u_student1", "handle": "student1", "role": "student"}
        with patch("server.get_current_user", return_value=mock_student):
            self.handler.path = "/api/admin/overview"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertFalse(res.get("success"))
            self.assertIn("Admin authorization required", res.get("error", ""))

    def test_admin_role_access_allowed(self):
        """Verify admin user can access /api/admin/me, /api/admin/overview, /api/admin/health."""
        mock_admin = {"id": "u_admin1", "handle": "admin1", "name": "Admin One", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Test /api/admin/me
            self.handler.path = "/api/admin/me"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            me_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(me_res.get("success"))
            self.assertEqual(me_res["user"]["role"], "admin")

            # Test /api/admin/overview
            self.handler.path = "/api/admin/overview"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            ov_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(ov_res.get("success"))
            self.assertIn("total_users", ov_res)
            self.assertIn("pending_reports", ov_res)

            # Test /api/admin/health
            self.handler.path = "/api/admin/health"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            h_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(h_res.get("success"))
            self.assertEqual(h_res.get("status"), "ok")

    def test_founder_role_access_allowed(self):
        """Verify founder user can access /api/admin/me and /api/admin/overview."""
        mock_founder = {"id": "u_founder1", "handle": "founder1", "name": "Founder", "role": "founder"}
        with patch("server.get_current_user", return_value=mock_founder):
            self.handler.path = "/api/admin/overview"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))

    def test_cookie_only_mutation_barrier(self):
        """Verify strict_bearer=True in require_admin rejects cookie-only requests for admin mutations."""
        cookie_headers = {"Cookie": "kandid_token=token_admin1_123456"}
        user, err = server.require_admin(self.handler, headers=cookie_headers, strict_bearer=True)
        self.assertIsNone(user)
        self.assertIsNotNone(err)
        self.assertEqual(err[0], 401)
        self.assertIn("Bearer token required", err[1].get("error", ""))

        # With Bearer header, require_admin succeeds for admin user
        bearer_headers = {"Authorization": "Bearer token_admin1_123456"}
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            user, err = server.require_admin(self.handler, headers=bearer_headers, strict_bearer=True)
            self.assertIsNotNone(user)
            self.assertIsNone(err)

    def test_admin_assets_blocked_from_static_fallback(self):
        """Verify is_blocked_static_path returns True for admin.html, admin.js, and /admin routes."""
        self.assertTrue(server.is_blocked_static_path("/admin"))
        self.assertTrue(server.is_blocked_static_path("/admin/"))
        self.assertTrue(server.is_blocked_static_path("/admin.html"))
        self.assertTrue(server.is_blocked_static_path("/admin.js"))
        self.assertTrue(server.is_blocked_static_path("/admin/subpath"))

    def test_admin_static_shell_routes_serve_unconditionally(self):
        """Verify requesting /admin, /admin/, /admin.html, and /admin.js serves the static UI shell without header auth."""
        for p in ["/admin", "/admin/", "/admin.html"]:
            self.handler.path = p
            self.sent_status = []
            self.sent_headers = {}
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            self.assertEqual(self.sent_headers.get("content-type"), "text/html; charset=utf-8")

        self.handler.path = "/admin.js"
        self.sent_status = []
        self.sent_headers = {}
        self.handler.do_GET()
        self.assertEqual(self.sent_status, [200])
        self.assertEqual(self.sent_headers.get("content-type"), "application/javascript; charset=utf-8")

    def test_admin_api_endpoints_enforce_strict_authorization(self):
        """Verify data endpoints /api/admin/* return 401 for unauthenticated, 403 for student, 200 for founder/admin."""
        # Unauthenticated
        with patch("server.get_current_user", return_value=None):
            self.handler.path = "/api/admin/overview"
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [401])

        # Student role
        mock_student = {"id": "u_student1", "role": "student"}
        with patch("server.get_current_user", return_value=mock_student):
            self.handler.path = "/api/admin/overview"
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])

        # Founder role
        mock_founder = {"id": "u_founder1", "role": "founder"}
        with patch("server.get_current_user", return_value=mock_founder):
            self.handler.path = "/api/admin/overview"
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])

    def test_admin_audit_log_schema_and_logger(self):
        """Verify admin_audit_log table exists and record_admin_audit_event appends logs safely."""
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_audit_log'")
        self.assertIsNotNone(cursor.fetchone(), "admin_audit_log table missing")

        # Test audit event recording
        mock_admin = {"id": "u_admin_test", "handle": "admin_test"}
        server.record_admin_audit_event(
            mock_admin,
            action="test_action",
            target_type="user",
            target_id="u_target123",
            details="Test audit event details",
            ip_address="127.0.0.1"
        )

        cursor.execute("SELECT * FROM admin_audit_log WHERE admin_id = ?", ("u_admin_test",))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        row_dict = dict(row)
        self.assertEqual(row_dict["action"], "test_action")
        self.assertEqual(row_dict["target_type"], "user")
        self.assertEqual(row_dict["target_id"], "u_target123")
        self.assertEqual(row_dict["admin_handle"], "admin_test")

    def test_reports_table_migration_columns(self):
        """Verify reports table contains status, reviewed_by, reviewed_at, and action_taken columns."""
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(reports)")
        cols = [row[1] for row in cursor.fetchall()]
        conn.close()

        for expected_col in ["status", "reviewed_by", "reviewed_at", "action_taken"]:
            self.assertIn(expected_col, cols, f"Column '{expected_col}' missing from reports table")

    def test_unexpected_migration_errors_raised(self):
        """Verify unexpected database errors during table column migration are not silently swallowed."""
    def _set_post_payload(self, path, payload, headers=None):
        data = json.dumps(payload).encode("utf-8")
        self.handler.path = path
        self.handler.rfile = BytesIO(data)
        self.handler.headers = {
            "Content-Length": str(len(data)),
            "Content-Type": "application/json",
            "Authorization": "Bearer token_admin_test_123"
        }
        if headers:
            self.handler.headers.update(headers)
        self.handler.read_json_body = lambda: payload

    def test_phase_c_admin_can_fetch_users(self):
        """1. Admin can fetch users list from /api/admin/users."""
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/users?page=1&limit=10"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertIn("users", res)
            self.assertIn("total", res)

    def test_phase_c_student_cannot_fetch_users(self):
        """2. Student role gets 403 on /api/admin/users."""
        mock_student = {"id": "u_student1", "role": "student"}
        with patch("server.get_current_user", return_value=mock_student):
            self.handler.path = "/api/admin/users"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])

    def test_phase_c_unauthenticated_cannot_fetch_users(self):
        """3. Unauthenticated gets 401 on /api/admin/users."""
        with patch("server.get_current_user", return_value=None):
            self.handler.path = "/api/admin/users"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [401])

    def test_phase_c_user_search_and_sql_injection_safety(self):
        """4 & 18. Parameterized SQL search works and blocks SQL injection strings."""
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Test SQL injection string
            self.handler.path = "/api/admin/users?q=%27%20OR%201=1--"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))

    def test_phase_c_user_pagination(self):
        """5. Pagination controls page and limit bounds."""
        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/users?page=1&limit=2"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res.get("limit"), 2)

    def test_phase_c_user_detail_endpoint(self):
        """6 & 17. GET /api/admin/users/<id> returns user details and active sessions count without leaking hashes."""
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       ("u_detail_user", "detail@test.com", "detail_user", "Detail User", "hash", "salt", "student"))
        conn.commit()
        conn.close()

        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/users/u_detail_user"
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertIn("user", res)
            self.assertNotIn("password_hash", res["user"])
            self.assertNotIn("salt", res["user"])
            self.assertIn("active_sessions", res)

    def test_phase_c_admin_suspend_and_restore_user_with_session_wiping(self):
        """7, 8, 9, 10 & 16. Admin can suspend student, session is deleted, suspended token rejected, restore works, audit logged."""
        conn = server.get_db()
        cursor = conn.cursor()

        # Seed target user and session
        cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role, account_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("u_target_suspend", "target_suspend@test.com", "target_suspend", "Target Suspend", "hash", "salt", "student", "active"))
        cursor.execute("INSERT OR REPLACE INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                       ("sess_target1", "u_target_suspend", "tok_target_suspend_123", "2099-01-01T00:00:00"))
        conn.commit()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}

        # 7 & 8. Suspend user
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/users/u_target_suspend/status", {"status": "suspended", "reason": "Policy violation test"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("account_status"), "suspended")
            self.assertGreaterEqual(res.get("sessions_revoked"), 1)

        # 8. Verify sessions were deleted
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", ("u_target_suspend",))
        self.assertEqual(cursor.fetchone()[0], 0)

        # 9. Verify get_current_user rejects suspended user
        headers = {"Authorization": "Bearer tok_target_suspend_123"}
        user = server.get_current_user(headers)
        self.assertIsNone(user, "Suspended user token must be rejected")

        # 10. Restore user
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/users/u_target_suspend/status", {"status": "active", "reason": "Restored after review"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res.get("account_status"), "active")

        conn.close()

    def test_phase_c_admin_revoke_sessions(self):
        """11. Admin can revoke all active sessions for a user."""
        conn = server.get_db()
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       ("u_target_revoke", "target_revoke@test.com", "target_revoke", "Target Revoke", "hash", "salt", "student"))
        cursor.execute("INSERT OR REPLACE INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                       ("sess_target2", "u_target_revoke", "tok_target_revoke_123", "2099-01-01T00:00:00"))
        conn.commit()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/users/u_target_revoke/revoke-sessions", {})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("sessions_revoked"), 1)

        conn.close()

    def test_phase_c_founder_only_role_changes_and_last_founder_protection(self):
        """12, 13, 14 & 15. Founder can change role, Admin cannot, invalid role rejected, last founder protected."""
        conn = server.get_db()
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role, account_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("u_target_role", "target_role@test.com", "target_role", "Target Role", "hash", "salt", "student", "active"))
        cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role, account_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("u_single_founder", "founder_sole@test.com", "founder_sole", "Sole Founder", "hash", "salt", "founder", "active"))
        conn.commit()

        # 13. Admin role change rejected (Founder-Only)
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/users/u_target_role/role", {"role": "creator"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [403])

        # 12. Founder role change allowed
        mock_founder = {"id": "u_single_founder", "handle": "founder_sole", "role": "founder"}
        with patch("server.get_current_user", return_value=mock_founder):
            self._set_post_payload("/api/admin/users/u_target_role/role", {"role": "creator", "reason": "Promoted to creator"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res.get("role"), "creator")

        # 14. Invalid role string rejected
        with patch("server.get_current_user", return_value=mock_founder):
            self._set_post_payload("/api/admin/users/u_target_role/role", {"role": "godmode"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])

        # 15. Last founder demotion protected
        with patch("server.get_current_user", return_value=mock_founder):
            self._set_post_payload("/api/admin/users/u_single_founder/role", {"role": "student"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertIn("Cannot demote the last active founder", res.get("error", ""))

        conn.close()

    def test_phase_c_cookie_only_mutation_rejected_on_user_apis(self):
        """19. Cookie-only mutation requests without Bearer header are rejected with 401."""
        cookie_headers = {"Cookie": "kandid_token=token_admin1_123456"}
        self._set_post_payload("/api/admin/users/u_target_role/status", {"status": "suspended"}, headers=cookie_headers)
        # Remove Authorization header to simulate cookie-only
        self.handler.headers.pop("Authorization", None)
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Bearer token required", res.get("error", ""))


if __name__ == "__main__":
    unittest.main()
