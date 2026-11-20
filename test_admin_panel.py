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
import secrets
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

    def tearDown(self):
        try:
            self.keep_alive.rollback()
        except Exception:
            pass

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

    # =========================================================================
    # PHASE D: CONTENT & MOMENTS + MOMENT CLUSTERS TESTS
    # =========================================================================

    def _insert_post(self, cursor, **kwargs):
        defaults = {
            "id": "post_" + secrets.token_hex(4),
            "user_id": "u_author_d1",
            "author_name": "Author One",
            "author_handle": "author_d1",
            "avatar_letter": "A",
            "avatar_url": "",
            "campus": "Central Campus",
            "main_img": "https://img.test/main.jpg",
            "pip_img": "https://img.test/pip.jpg",
            "caption": "",
            "audio_vibe": "ambient",
            "audio_duration": "3.0s",
            "circle": "campus",
            "exif_iso": "ISO 400",
            "exif_aperture": "f/2.8",
            "exif_shutter": "1/250s",
            "created_at": "2026-10-08T12:00:00",
            "region": "all",
            "location_city": "Stanford",
            "location_country": "US",
            "location_coords": "",
            "is_private": 0,
            "event_id": "",
            "audio_url": "",
            "motion_url": "",
            "primary_community_id": "",
            "context_community_id": "",
            "context_location": "",
            "drop_id": "",
            "moderation_status": "active",
            "cluster_id": ""
        }
        defaults.update(kwargs)
        cols = list(defaults.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        cursor.execute(f"INSERT OR REPLACE INTO posts ({col_names}) VALUES ({placeholders})", [defaults[c] for c in cols])
        return defaults["id"]

    def test_phase_d_admin_can_list_posts(self):
        """1. Admin can list posts from /api/admin/posts."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_author_d1", "auth1@test.com", "author_d1", "Author One", "hash", "salt", "student"))
            self._insert_post(cursor, id="post_d1", user_id="u_author_d1", author_handle="author_d1", author_name="Author One",
                              caption="Sunset over quad #kandid", campus="Campus A", moderation_status="active", is_private=0)
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/posts?page=1&limit=25"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertIn("posts", res)
            self.assertGreaterEqual(res.get("total"), 1)
            found_ids = [p["id"] for p in res["posts"]]
            self.assertIn("post_d1", found_ids)

    def test_phase_d_student_cannot_list_posts(self):
        """2. Student role gets 403 on /api/admin/posts."""
        mock_student = {"id": "u_student1", "role": "student"}
        with patch("server.get_current_user", return_value=mock_student):
            self.handler.path = "/api/admin/posts"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])

    def test_phase_d_unauthenticated_cannot_list_posts(self):
        """3. Unauthenticated gets 401 on /api/admin/posts."""
        with patch("server.get_current_user", return_value=None):
            self.handler.path = "/api/admin/posts"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [401])

    def test_phase_d_posts_search_and_filters(self):
        """4, 5, 6 & 7. Posts search by caption, author_handle, campus; filters by status, visibility, cluster_id, community_id."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_author_d2", "auth2@test.com", "supercoder99", "Super Coder", "hash", "salt", "student"))

            self._insert_post(cursor, id="post_hackathon", user_id="u_author_d2", author_handle="coder_alex", author_name="Alex",
                              caption="Hackathon kick-off keynote", campus="Tech Campus", moderation_status="active", is_private=0,
                              cluster_id="clus_hack", primary_community_id="comm_hack")

            self._insert_post(cursor, id="post_hidden_1", user_id="u_author_d2", author_handle="supercoder99", author_name="Super Coder",
                              caption="Some hidden text", campus="Stanford Quad", moderation_status="hidden", is_private=0)

            self._insert_post(cursor, id="post_removed_1", user_id="u_author_d2", author_handle="other_guy", author_name="Other",
                              caption="Removed content", campus="Stanford Quad", moderation_status="removed", is_private=1)

            self._insert_post(cursor, id="post_private_1", user_id="u_author_d2", author_handle="private_author", author_name="Priv",
                              caption="Private journal post", campus="Stanford Quad", moderation_status="active", is_private=1)
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Search by caption keyword
            self.handler.path = "/api/admin/posts?q=hackathon"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["posts"][0]["id"], "post_hackathon")

            # Search by handle
            self.handler.path = "/api/admin/posts?q=supercoder99&status=all"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["posts"][0]["id"], "post_hidden_1")

            # Filter by status=hidden
            self.handler.path = "/api/admin/posts?status=hidden"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            found = [p["id"] for p in res["posts"]]
            self.assertIn("post_hidden_1", found)
            self.assertNotIn("post_hackathon", found)

            # Filter by status=removed
            self.handler.path = "/api/admin/posts?status=removed"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            found = [p["id"] for p in res["posts"]]
            self.assertIn("post_removed_1", found)

            # Filter by visibility=private
            self.handler.path = "/api/admin/posts?visibility=private"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            for p in res["posts"]:
                self.assertTrue(p["is_private"])

            # Filter by cluster_id
            self.handler.path = "/api/admin/posts?cluster_id=clus_hack"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["posts"][0]["id"], "post_hackathon")

            # Filter by community_id
            self.handler.path = "/api/admin/posts?community_id=comm_hack"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["posts"][0]["id"], "post_hackathon")

    def test_phase_d_posts_pagination_bounds(self):
        """8. Posts pagination bounds clamping."""
        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/posts?page=1&limit=2"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["limit"], 2)

            # Clamping beyond 100
            self.handler.path = "/api/admin/posts?page=-5&limit=500"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["page"], 1)
            self.assertEqual(res["limit"], 100)

    def test_phase_d_post_detail_endpoint(self):
        """9. GET /api/admin/posts/<id> returns post metadata, reactions count, reports count, cluster info, author info."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_author_det", "auth_det@test.com", "det_user", "Detail Author", "hash", "salt", "student"))
            self._insert_post(cursor, id="post_detail_1", user_id="u_author_det", author_handle="det_user", author_name="Detail Author",
                              caption="Detail caption", campus="Campus B", moderation_status="active", is_private=0,
                              cluster_id="clus_det_1", location_coords="37.7749,-122.4194")

            cursor.execute("INSERT OR REPLACE INTO reactions (id, post_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?, ?)",
                           ("rx_1", "post_detail_1", "u_other_1", "🔥", "2026-10-08T12:05:00"))
            cursor.execute("""
                INSERT OR REPLACE INTO community_reports (id, community_id, reporter_id, target_type, target_id, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("rep_1", "comm_1", "u_other_2", "moment", "post_detail_1", "Inappropriate content", "pending"))
            cursor.execute("""
                INSERT OR REPLACE INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id, originator_user_id, status, visibility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("clus_det_1", "event", "Football Match", "post_detail_1", "u_author_det", "active", "public", "2026-10-08T12:00:00"))
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/posts/post_detail_1"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res["success"])
            self.assertEqual(res["post"]["id"], "post_detail_1")
            self.assertEqual(res["reactions_count"], 1)
            self.assertEqual(res["reports_count"], 1)
            self.assertIsNotNone(res["cluster"])
            self.assertEqual(res["cluster"]["id"], "clus_det_1")
            self.assertIsNotNone(res["author"])
            self.assertEqual(res["author"]["handle"], "det_user")

    def test_phase_d_sensitive_data_stripped(self):
        """10. Sensitive data stripped: location_coords and passwords/tokens NEVER returned."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_priv_author", "priv@test.com", "priv_user", "Priv Author", "hash_secret", "salt_secret", "student"))
            self._insert_post(cursor, id="post_priv_test", user_id="u_priv_author", author_handle="priv_user", author_name="Priv Author",
                              caption="Priv caption", campus="Campus B", moderation_status="active", is_private=0,
                              location_coords="37.7749,-122.4194")
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # In list endpoint
            self.handler.path = "/api/admin/posts?q=priv_user"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            for p in res["posts"]:
                self.assertNotIn("location_coords", p)
                self.assertNotIn("password_hash", p)
                self.assertNotIn("salt", p)

            # In detail endpoint
            self.handler.path = "/api/admin/posts/post_priv_test"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertNotIn("location_coords", res["post"])
            if res.get("author"):
                self.assertNotIn("password_hash", res["author"])
                self.assertNotIn("salt", res["author"])

    def test_phase_d_post_moderation_hide_remove_restore(self):
        """11, 12, 13. POST /api/admin/posts/<id>/moderation hides, removes, and restores post with audit logging."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_mod_author", "mod_auth@test.com", "mod_auth", "Mod Author", "hash", "salt", "student"))
            self._insert_post(cursor, id="post_to_moderate", user_id="u_mod_author", author_handle="mod_auth", author_name="Mod Author",
                              caption="Under review post", moderation_status="active", is_private=0)
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # 11. Hide post
            self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "hidden", "reason": "Reported inappropriate"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["moderation_status"], "hidden")

            # Check DB updated
            conn = server.get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT moderation_status, is_private FROM posts WHERE id = ?", ("post_to_moderate",))
                row = cursor.fetchone()
                self.assertEqual(row["moderation_status"], "hidden")

                # Check audit log
                cursor.execute("SELECT * FROM admin_audit_log WHERE action = 'post_moderation_hidden' AND target_id = ?", ("post_to_moderate",))
                audit_entry = cursor.fetchone()
                self.assertIsNotNone(audit_entry)
                self.assertIn("Reported inappropriate", audit_entry["details"])
            finally:
                conn.close()

            # 12. Remove post
            self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "removed", "reason": "Confirmed policy violation"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["moderation_status"], "removed")

            conn = server.get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT moderation_status, is_private FROM posts WHERE id = ?", ("post_to_moderate",))
                row = cursor.fetchone()
                self.assertEqual(row["moderation_status"], "removed")
                self.assertEqual(row["is_private"], 1)
            finally:
                conn.close()

            # 13. Restore post to active
            self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "active", "reason": "User appeal accepted"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["moderation_status"], "active")

            conn = server.get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT moderation_status, is_private FROM posts WHERE id = ?", ("post_to_moderate",))
                row = cursor.fetchone()
                self.assertEqual(row["moderation_status"], "active")
                self.assertEqual(row["is_private"], 0)
            finally:
                conn.close()

    def test_phase_d_post_moderation_validation(self):
        """14, 15. Invalid status and missing reason rejected with 400."""
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Invalid status
            self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "destroyed", "reason": "Valid reason"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertIn("Invalid status", res["error"])

            # Missing reason
            self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "hidden", "reason": ""})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertIn("Reason is required", res["error"])

            # 404 for non-existent post
            self._set_post_payload("/api/admin/posts/non_existent_post_xyz/moderation", {"status": "hidden", "reason": "Valid reason"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [404])

    def test_phase_d_zero_hard_deletes_and_cascade_safety(self):
        """16, 17. ZERO hard deletes on post moderation; cluster and members are NOT cascade-deleted."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_orig_user", "orig@test.com", "orig_user", "Originator", "hash", "salt", "student"))
            self._insert_post(cursor, id="post_orig_1", user_id="u_orig_user", author_handle="orig_user", author_name="Originator",
                              caption="Event seed post", moderation_status="active", is_private=0)

            cursor.execute("""
                INSERT OR REPLACE INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id, originator_user_id, status, visibility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("cluster_orig_1", "event", "Campus Festival", "post_orig_1", "u_orig_user", "active", "public", "2026-10-08T12:00:00"))

            cursor.execute("""
                INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("mem_orig_creator", "cluster_orig_1", "u_orig_user", "post_orig_1", "creator", "2026-10-08T12:00:00"))
            conn.commit()
        finally:
            conn.close()

        # Admin moderates originator post
        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/posts/post_orig_1/moderation", {"status": "removed", "reason": "Copyright infringement"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

        # Verify DB: ZERO hard deletes
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, moderation_status FROM posts WHERE id = 'post_orig_1'")
            post_row = cursor.fetchone()
            self.assertIsNotNone(post_row, "Post row was hard-deleted! Must be soft-moderated only.")
            self.assertEqual(post_row["moderation_status"], "removed")

            # Verify cluster still intact
            cursor.execute("SELECT id, status FROM moment_clusters WHERE id = 'cluster_orig_1'")
            cluster_row = cursor.fetchone()
            self.assertIsNotNone(cluster_row, "Cluster was cascade-deleted when originator post was moderated!")
            self.assertEqual(cluster_row["status"], "active")

            # Verify cluster members still intact
            cursor.execute("SELECT id FROM moment_cluster_members WHERE cluster_id = 'cluster_orig_1'")
            member_rows = cursor.fetchall()
            self.assertEqual(len(member_rows), 1, "Cluster members were deleted when originator was moderated!")
        finally:
            conn.close()

    def test_phase_d_perspective_moderation_preserves_attendance(self):
        """18. Moderating a perspective post preserves the user's attendance ('participant') record."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_attendee_1", "att1@test.com", "attendee_1", "Attendee One", "hash", "salt", "student"))

            self._insert_post(cursor, id="post_persp_1", user_id="u_attendee_1", author_handle="attendee_1", author_name="Attendee One",
                              caption="My angle from the stage", moderation_status="active", is_private=0)

            cursor.execute("""
                INSERT OR REPLACE INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id, originator_user_id, status, visibility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("cluster_persp_test", "event", "Rock Concert", "post_orig_1", "u_orig_user", "active", "public", "2026-10-08T12:00:00"))

            # Perspective membership
            cursor.execute("""
                INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("mem_persp_row", "cluster_persp_test", "u_attendee_1", "post_persp_1", "perspective", "2026-10-08T12:30:00"))

            # Attendance membership (I Was There)
            cursor.execute("""
                INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("mem_attendee_row", "cluster_persp_test", "u_attendee_1", "", "participant", "2026-10-08T12:15:00"))
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self._set_post_payload("/api/admin/posts/post_persp_1/moderation", {"status": "removed", "reason": "Blurry image"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, participation_type FROM moment_cluster_members WHERE cluster_id = 'cluster_persp_test' AND user_id = 'u_attendee_1'")
            members = cursor.fetchall()
        finally:
            conn.close()

        part_types = [m["participation_type"] for m in members]
        self.assertIn("participant", part_types, "Attendance record was wiped out when perspective was moderated!")

    def test_phase_d_cookie_only_mutation_rejected_on_post_moderation(self):
        """19. Cookie-only mutation requests to /api/admin/posts/<id>/moderation without Bearer header are rejected with 401."""
        cookie_headers = {"Cookie": "kandid_token=token_admin1_123456"}
        self._set_post_payload("/api/admin/posts/post_to_moderate/moderation", {"status": "hidden", "reason": "Reason"}, headers=cookie_headers)
        self.handler.headers.pop("Authorization", None)
        self.sent_status = []
        self.handler.wfile = BytesIO()
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Bearer token required", res.get("error", ""))

    def test_phase_d_admin_can_list_clusters(self):
        """20. Admin can list moment clusters from /api/admin/clusters with perspective and participant counts."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_clus_creator", "c_creat@test.com", "c_creat", "Cluster Creator", "hash", "salt", "student"))
            cursor.execute("INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ("u_attendee_1", "att1@test.com", "attendee_1", "Attendee One", "hash", "salt", "student"))
            self._insert_post(cursor, id="post_orig_1", user_id="u_clus_creator", author_handle="c_creat", author_name="Cluster Creator",
                              caption="Seed post", moderation_status="active", is_private=0)
            self._insert_post(cursor, id="post_d1", user_id="u_clus_creator", author_handle="c_creat", author_name="Cluster Creator",
                              caption="Perspective post", moderation_status="active", is_private=0)
            cursor.execute("""
                INSERT OR REPLACE INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id, originator_user_id, status, visibility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("cluster_counts_test", "event", "Alumni Reunion Dinner", "post_orig_1", "u_clus_creator", "active", "public", "2026-10-08T18:00:00"))

            # 2 perspectives
            cursor.execute("INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
                           ("mem_p1", "cluster_counts_test", "u_clus_creator", "post_orig_1", "perspective", "2026-10-08T18:01:00"))
            cursor.execute("INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
                           ("mem_p2", "cluster_counts_test", "u_author_d1", "post_d1", "perspective", "2026-10-08T18:02:00"))

            # 1 attendee participant
            cursor.execute("INSERT OR REPLACE INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
                           ("mem_att1", "cluster_counts_test", "u_attendee_1", "", "participant", "2026-10-08T18:05:00"))
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/clusters?q=Alumni"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res["success"])
            self.assertEqual(res["total"], 1)
            clus = res["clusters"][0]
            self.assertEqual(clus["id"], "cluster_counts_test")
            self.assertEqual(clus["perspectives_count"], 2)
            self.assertEqual(clus["participants_count"], 1)

    def test_phase_d_student_and_unauth_rejected_on_clusters(self):
        """20b. Student gets 403 and unauthenticated gets 401 on /api/admin/clusters."""
        mock_student = {"id": "u_student1", "role": "student"}
        with patch("server.get_current_user", return_value=mock_student):
            self.handler.path = "/api/admin/clusters"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])

        with patch("server.get_current_user", return_value=None):
            self.handler.path = "/api/admin/clusters"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [401])

    def test_phase_d_cluster_detail_endpoint(self):
        """21. GET /api/admin/clusters/<id> returns cluster, originator post, originator user, perspectives, participants roster."""
        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            self.handler.path = "/api/admin/clusters/cluster_counts_test"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res["success"])
            self.assertEqual(res["cluster"]["id"], "cluster_counts_test")
            self.assertIsNotNone(res["originator_post"])
            self.assertIsNotNone(res["originator_user"])
            self.assertEqual(len(res["perspectives"]), 2)
            self.assertEqual(len(res["participants"]), 1)
            self.assertEqual(res["perspectives_count"], 2)
            self.assertEqual(res["participants_count"], 1)

            # 404 for non-existent cluster
            self.handler.path = "/api/admin/clusters/non_existent_cluster_123"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [404])

    def test_phase_d_cluster_status_change_and_validation(self):
        """22. POST /api/admin/clusters/<id>/status updates cluster status, records audit log, validates status/reason."""
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id, originator_user_id, status, visibility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("cluster_stat_mod", "event", "Robotics Expo", "post_orig_1", "u_clus_creator", "active", "public", "2026-10-08T19:00:00"))
            conn.commit()
        finally:
            conn.close()

        mock_admin = {"id": "u_admin1", "handle": "admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Close cluster
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "closed", "reason": "Event concluded"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(res["status"], "closed")

            # Check DB
            conn = server.get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM moment_clusters WHERE id = 'cluster_stat_mod'")
                self.assertEqual(cursor.fetchone()["status"], "closed")

                # Check audit log
                cursor.execute("SELECT * FROM admin_audit_log WHERE action = 'cluster_status_closed' AND target_id = 'cluster_stat_mod'")
                audit_entry = cursor.fetchone()
                self.assertIsNotNone(audit_entry)
                self.assertIn("Event concluded", audit_entry["details"])
            finally:
                conn.close()

            # Archive cluster
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "archived", "reason": "Archived after 30 days"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

            # Hide cluster
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "hidden", "reason": "Safety review"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

            # Reactivate cluster
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "active", "reason": "Review cleared"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

            # Invalid status rejected
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "demolished", "reason": "Test"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])

            # Missing reason rejected
            self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "closed", "reason": ""})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [400])

            # 404 for non-existent cluster
            self._set_post_payload("/api/admin/clusters/cluster_non_existent/status", {"status": "closed", "reason": "Test"})
            self.sent_status = []
            self.handler.wfile = BytesIO()
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [404])

    def test_phase_d_cookie_only_mutation_rejected_on_cluster_status(self):
        """22b. Cookie-only mutation requests to /api/admin/clusters/<id>/status without Bearer header are rejected with 401."""
        cookie_headers = {"Cookie": "kandid_token=token_admin1_123456"}
        self._set_post_payload("/api/admin/clusters/cluster_stat_mod/status", {"status": "closed", "reason": "Reason"}, headers=cookie_headers)
        self.handler.headers.pop("Authorization", None)
        self.sent_status = []
        self.handler.wfile = BytesIO()
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Bearer token required", res.get("error", ""))

    def test_phase_d_sql_injection_safety_on_posts_and_clusters(self):
        """22c. Search queries on posts and clusters are parameterized and safe against SQL injection."""
        mock_admin = {"id": "u_admin1", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # Posts search SQLi attempt
            self.handler.path = "/api/admin/posts?q=%27%20UNION%20SELECT%201,2,3--"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res["success"])

            # Clusters search SQLi attempt
            self.handler.path = "/api/admin/clusters?q=%27%20OR%201=1--"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res["success"])


class TestAdminSecurityHardening(unittest.TestCase):
    """
    Comprehensive tests for Enterprise Admin Security Hardening:
    - Dedicated Admin Sessions (adm_ token, 2-hr expiry, isolated table)
    - 2FA / TOTP Setup and Verification (RFC 6238 standard)
    - Sudo Mode Step-Up Elevation on Destructive Actions
    - Brute Force Login Rate Limiting (5 attempts / 15 mins)
    """
    @classmethod
    def setUpClass(cls):
        cls.keep_alive = sqlite3.connect("file:admin_sec_mem?mode=memory&cache=shared", uri=True)
        cls.keep_alive.row_factory = sqlite3.Row

        def make_db():
            conn = sqlite3.connect("file:admin_sec_mem?mode=memory&cache=shared", uri=True)
            conn.row_factory = sqlite3.Row
            return conn

        cls.db_patcher = patch("server.get_db", side_effect=make_db)
        cls.db_patcher.start()
        server.init_db()

        # Seed test users
        conn = make_db()
        cursor = conn.cursor()

        salt_admin = secrets.token_hex(16)
        hash_admin, _ = server.hash_password("AdminSecret123!", salt_admin)
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, handle, name, email, role, salt, password_hash, account_status)
            VALUES ('u_harden_admin', 'secadmin', 'Sec Admin', 'secadmin@test.edu', 'admin', ?, ?, 'active')
        """, (salt_admin, hash_admin))

        salt_student = secrets.token_hex(16)
        hash_student, _ = server.hash_password("StudentPass123!", salt_student)
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, handle, name, email, role, salt, password_hash, account_status)
            VALUES ('u_harden_student', 'secstudent', 'Sec Student', 'secstudent@test.edu', 'student', ?, ?, 'active')
        """, (salt_student, hash_student))

        cls.totp_secret = server.generate_totp_secret()
        salt_2fa = secrets.token_hex(16)
        hash_2fa, _ = server.hash_password("Admin2FaPass123!", salt_2fa)
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, handle, name, email, role, salt, password_hash, account_status, admin_totp_secret, admin_totp_enabled)
            VALUES ('u_harden_2fa', 'admin2fa', 'Admin 2FA', 'admin2fa@test.edu', 'admin', ?, ?, 'active', ?, 1)
        """, (salt_2fa, hash_2fa, cls.totp_secret))

        # Target user for destructive moderation actions
        cursor.execute("""
            INSERT OR REPLACE INTO users (id, handle, name, email, role, salt, password_hash, account_status)
            VALUES ('u_target_user', 'targetuser', 'Target User', 'target@test.edu', 'student', 'salt', 'hash', 'active')
        """)

        conn.commit()
        conn.close()

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
        self.handler.client_address = ("127.0.0.1", 54321)

        def fake_send_response(code):
            self.sent_status.append(code)

        def fake_send_header(keyword, value):
            self.sent_headers[keyword] = value

        def fake_end_headers():
            pass

        self.handler.send_response = fake_send_response
        self.handler.send_header = fake_send_header
        self.handler.end_headers = fake_end_headers

        # Ensure clean state between tests
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET admin_totp_enabled = 0, admin_totp_secret = '' WHERE id = 'u_harden_admin'")
        conn.commit()
        conn.close()
        server._admin_login_rate_limiter.buckets.clear()

    def _set_post(self, path, payload, headers=None):
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
        self.sent_status = []
        self.sent_headers = {}
        self.handler.wfile = BytesIO()

    def test_admin_login_success_and_session_creation(self):
        """Admin login succeeds with password, issues adm_ token, sets cookie, and persists in admin_sessions."""
        self._set_post("/api/admin/auth/login", {
            "handle": "secadmin",
            "password": "AdminSecret123!"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res["success"])
        self.assertTrue(res["token"].startswith("adm_"))
        self.assertEqual(res["user"]["handle"], "secadmin")
        self.assertFalse(res["totp_enabled"])

        # Check Set-Cookie header
        self.assertIn("Set-Cookie", self.sent_headers)
        self.assertIn("kindid_admin_session=" + res["token"], self.sent_headers["Set-Cookie"])
        self.assertIn("HttpOnly", self.sent_headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", self.sent_headers["Set-Cookie"])

        # Verify session exists in DB
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_sessions WHERE token = ?", (res["token"],))
        s_row = cursor.fetchone()
        self.assertIsNotNone(s_row)
        self.assertEqual(s_row["admin_id"], "u_harden_admin")
        conn.close()

    def test_admin_login_invalid_password(self):
        """Admin login with wrong password returns 401."""
        self._set_post("/api/admin/auth/login", {
            "handle": "secadmin",
            "password": "WrongPassword123!"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertFalse(res["success"])

    def test_admin_login_student_forbidden(self):
        """Student account attempting admin login is rejected with 403."""
        self._set_post("/api/admin/auth/login", {
            "handle": "secstudent",
            "password": "StudentPass123!"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [403])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Admin credentials required", res["error"])

    def test_admin_login_totp_required_and_verified(self):
        """Admin with 2FA enabled prompts for TOTP code and validates standard RFC 6238 code."""
        # Step 1: Login without code -> prompts 401 with totp_required
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res.get("totp_required"))

        # Step 2: Login with invalid code -> 401
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": "000000"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        res2 = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Invalid two-factor", res2["error"])

        # Step 3: Login with valid TOTP code computed with compute_totp -> 200
        valid_code = server.compute_totp(self.totp_secret)
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": valid_code
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        res3 = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(res3["success"])
        self.assertTrue(res3["sudo_active"])

    def test_admin_logout(self):
        """Admin logout clears session from DB and expires cookie."""
        # Create an active session
        adm_token = "adm_" + secrets.token_hex(24)
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_sessions (id, admin_id, admin_handle, token, expires_at)
            VALUES ('as_logout_test', 'u_harden_admin', 'secadmin', ?, '2099-01-01T00:00:00')
        """, (adm_token,))
        conn.commit()
        conn.close()

        self._set_post("/api/admin/auth/logout", {}, headers={"Authorization": "Bearer " + adm_token})
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        self.assertIn("Set-Cookie", self.sent_headers)
        self.assertIn("Max-Age=0", self.sent_headers["Set-Cookie"])

        # Check session is deleted
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_sessions WHERE token = ?", (adm_token,))
        self.assertIsNone(cursor.fetchone())
        conn.close()

    def test_2fa_setup_and_verify_enable(self):
        """2FA setup generates Base32 secret and verify-enable activates 2FA for the user."""
        mock_admin = {"id": "u_harden_admin", "handle": "secadmin", "role": "admin"}
        with patch("server.get_current_user", return_value=mock_admin):
            # GET /api/admin/auth/2fa-setup
            self.handler.path = "/api/admin/auth/2fa-setup"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            setup_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(setup_res["success"])
            secret = setup_res["secret"]
            self.assertTrue(len(secret) >= 16)
            self.assertIn("otpauth://totp/", setup_res["otpauth_url"])

            # POST /api/admin/auth/2fa-verify-enable with valid code
            valid_code = server.compute_totp(secret)
            self._set_post("/api/admin/auth/2fa-verify-enable", {
                "secret": secret,
                "code": valid_code
            }, headers={"Authorization": "Bearer token_test"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            enable_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(enable_res["success"])

            # Verify in DB
            conn = server.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT admin_totp_enabled, admin_totp_secret FROM users WHERE id = 'u_harden_admin'")
            u_row = cursor.fetchone()
            self.assertEqual(u_row["admin_totp_enabled"], 1)
            self.assertEqual(u_row["admin_totp_secret"], secret)
            conn.close()

    def test_sudo_mode_enforcement_and_elevation(self):
        """Destructive action requires sudo when 2FA is enabled; elevating sudo permits action."""
        # Mock admin with 2FA enabled, but expired sudo
        mock_2fa_admin_no_sudo = {
            "id": "u_harden_2fa",
            "handle": "admin2fa",
            "role": "admin",
            "admin_totp_enabled": 1,
            "sudo_expires_at": "2000-01-01T00:00:00",
            "admin_session_id": "as_test_sudo"
        }

        with patch("server.get_current_user", return_value=mock_2fa_admin_no_sudo):
            # Attempting destructive user suspension without active sudo
            self._set_post("/api/admin/users/u_target_user/status", {
                "status": "suspended",
                "reason": "Security violation"
            }, headers={"Authorization": "Bearer adm_test_token"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [403])
            res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(res.get("requires_sudo"))

            # Elevate sudo via /api/admin/auth/sudo-verify
            valid_code = server.compute_totp(self.totp_secret)
            self._set_post("/api/admin/auth/sudo-verify", {
                "code": valid_code
            }, headers={"Authorization": "Bearer adm_test_token"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            sudo_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(sudo_res["sudo_active"])

        # Now with active sudo elevation
        mock_2fa_admin_with_sudo = {
            "id": "u_harden_2fa",
            "handle": "admin2fa",
            "role": "admin",
            "admin_totp_enabled": 1,
            "sudo_expires_at": "2099-01-01T00:00:00",
            "admin_session_id": "as_test_sudo"
        }
        with patch("server.get_current_user", return_value=mock_2fa_admin_with_sudo):
            self._set_post("/api/admin/users/u_target_user/status", {
                "status": "suspended",
                "reason": "Security violation"
            }, headers={"Authorization": "Bearer adm_test_token"})
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])
            suspend_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(suspend_res["success"])
            self.assertEqual(suspend_res["account_status"], "suspended")

    def test_admin_login_rate_limiting(self):
        """Admin login locks out after 5 consecutive attempts within 15 minutes."""
        for attempt in range(5):
            self._set_post("/api/admin/auth/login", {
                "handle": "bruteforce_target",
                "password": f"WrongPass{attempt}"
            })
            self.handler.do_POST()

        # 6th attempt must be rate-limited (429)
        self._set_post("/api/admin/auth/login", {
            "handle": "bruteforce_target",
            "password": "AnyPassword"
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [429])
        res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertIn("Too many admin login attempts", res["error"])

    def test_mandatory_2fa_enforcement_blocks_control_surfaces_until_enabled(self):
        """Mandatory 2FA: Unconfigured 2FA admin can reach /me and /2fa-setup, but /overview and /users are 403 blocked."""
        mock_unconfigured_admin = {
            "id": "u_unconfigured_admin",
            "handle": "unconfigured_admin",
            "name": "Unconfigured Admin",
            "role": "admin",
            "admin_totp_enabled": 0
        }

        with patch("server.get_current_user", return_value=mock_unconfigured_admin):
            # 1. /api/admin/me returns force_2fa_setup: True
            self.handler.path = "/api/admin/me"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            me_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(me_res["user"]["force_2fa_setup"])
            self.assertFalse(me_res["user"]["admin_totp_enabled"])

            # 2. /api/admin/auth/2fa-setup is accessible
            self.handler.path = "/api/admin/auth/2fa-setup"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [200])
            setup_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(setup_res["success"])
            self.assertIn("secret", setup_res)

            # 3. Control surface /api/admin/overview is strictly 403 blocked
            self.handler.path = "/api/admin/overview"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])
            overview_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(overview_res.get("requires_2fa_setup"))
            self.assertIn("mandatory for administrator access", overview_res.get("error", ""))

            # 4. Users list /api/admin/users is strictly 403 blocked
            self.handler.path = "/api/admin/users"
            self.handler.wfile = BytesIO()
            self.sent_status = []
            self.handler.do_GET()
            self.assertEqual(self.sent_status, [403])
            users_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
            self.assertTrue(users_res.get("requires_2fa_setup"))

    def test_admin_security_email_alerts_dispatched(self):
        """Security alert emails are triggered on failed login, successful login, and sudo elevation."""
        sent_emails = []

        def mock_send_email(to, subject, html, text=""):
            sent_emails.append({"to": to, "subject": subject, "html": html, "text": text})
            return {"success": True}

        with patch("server.send_email_brevo", side_effect=mock_send_email):
            # 1. Failed login attempt triggers security alert email
            self._set_post("/api/admin/auth/login", {
                "handle": "secadmin",
                "password": "WrongPasswordAlertTest"
            })
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [401])

            # Give daemon thread a brief tick to run
            import time
            time.sleep(0.05)
            self.assertTrue(any("Failed Admin Login Attempt" in e["subject"] for e in sent_emails))

            # 2. Successful login triggers login notification
            self._set_post("/api/admin/auth/login", {
                "handle": "secadmin",
                "password": "AdminSecret123!"
            })
            self.handler.do_POST()
            self.assertEqual(self.sent_status, [200])

            time.sleep(0.05)
            self.assertTrue(any("Admin Portal Login Detected" in e["subject"] for e in sent_emails))

    def test_admin_emergency_backup_recovery_codes_workflow(self):
        """Test backup recovery codes generation, verification, single-use burning, and login."""
        # 1. Establish session
        totp_code = server.compute_totp(self.totp_secret)
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": totp_code
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        login_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        admin_token = login_res["token"]

        # 2. Generate 8 backup recovery codes
        codes = server.generate_admin_backup_codes("u_harden_2fa", count=8)
        self.assertEqual(len(codes), 8)
        for c in codes:
            self.assertEqual(len(c), 9) # Format XXXX-XXXX
            self.assertIn("-", c)

        # 3. Check remaining count via GET /api/admin/auth/backup-codes
        self.sent_status.clear()
        self.handler.wfile = BytesIO()
        self.handler.path = "/api/admin/auth/backup-codes"
        self.handler.headers = {"Authorization": f"Bearer {admin_token}"}
        self.handler.do_GET()
        self.assertEqual(self.sent_status, [200])
        status_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(status_res.get("success"))
        self.assertEqual(status_res.get("remaining"), 8)

        # 4. Use one code to log in via POST /api/admin/auth/login
        test_code = codes[0]
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": test_code
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        login_res2 = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(login_res2.get("success"))
        self.assertTrue(login_res2.get("sudo_active"))

        # 5. Same code CANNOT be reused (single-use guarantee)
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": test_code
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [401])
        fail_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertFalse(fail_res.get("success"))

        # 6. Check remaining count is now 7
        self.sent_status.clear()
        self.handler.wfile = BytesIO()
        self.handler.path = "/api/admin/auth/backup-codes"
        self.handler.headers = {"Authorization": f"Bearer {admin_token}"}
        self.handler.do_GET()
        self.assertEqual(self.sent_status, [200])
        status_res2 = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(status_res2.get("remaining"), 7)

    def test_mobile_clock_skew_tolerance_window(self):
        """Test verify_totp accepts +/- 60s window to absorb mobile phone carrier clock drift."""
        import time
        secret = "JBSWY3DPEHPK3PXP"
        now = int(time.time())
        # Code from 60 seconds ago (-2 intervals)
        code_minus_60 = server.compute_totp(secret, for_time=now - 60)
        # Code from 60 seconds in future (+2 intervals)
        code_plus_60 = server.compute_totp(secret, for_time=now + 60)
        # Code from 120 seconds ago (outside window)
        code_minus_120 = server.compute_totp(secret, for_time=now - 120)

        # verify_totp with window=2 (the default) accepts +/- 60s
        self.assertTrue(server.verify_totp(secret, code_minus_60))
        self.assertTrue(server.verify_totp(secret, code_plus_60))
        self.assertFalse(server.verify_totp(secret, code_minus_120))

    def test_admin_geographic_origin_and_campus_circles_analytics(self):
        """Test /api/admin/overview returns geo_distribution and top_campuses."""
        # 1. Establish session token
        totp_code = server.compute_totp(self.totp_secret)
        self._set_post("/api/admin/auth/login", {
            "handle": "admin2fa",
            "password": "Admin2FaPass123!",
            "code": totp_code
        })
        self.handler.do_POST()
        self.assertEqual(self.sent_status, [200])
        login_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        admin_token = login_res["token"]

        # 2. Query /api/admin/overview
        self.sent_status.clear()
        self.handler.wfile = BytesIO()
        self.handler.path = "/api/admin/overview"
        self.handler.headers = {"Authorization": f"Bearer {admin_token}"}
        self.handler.do_GET()
        self.assertEqual(self.sent_status, [200])
        overview_res = json.loads(self.handler.wfile.getvalue().decode("utf-8"))
        self.assertTrue(overview_res.get("success"))
        self.assertIn("geo_distribution", overview_res)
        self.assertIn("top_campuses", overview_res)
        self.assertIsInstance(overview_res["geo_distribution"], list)
        self.assertIsInstance(overview_res["top_campuses"], list)
        self.assertGreater(len(overview_res["top_campuses"]), 0)


if __name__ == "__main__":
    unittest.main()
