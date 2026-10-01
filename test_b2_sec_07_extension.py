#!/usr/bin/env python3
"""
Regression test suite for B2-SEC-07 Extension:
Visibility & Moderation enforcement across:
  1. GET /api/cluster/<id>
  2. GET /api/user/profile
  3. GET /api/invite/preview

Verifies that private, hidden, suspended, and removed posts are never leaked,
and that blocked-user boundaries are strictly respected.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


class TestB2Sec07Extension(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec07_")
        cls.addClassCleanup(shutil.rmtree, cls._tmpdir, ignore_errors=True)
        cls.addClassCleanup(_restore_server_globals)

        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()

        # Seed Users
        # u_author: creates originator moments & profile
        # u_viewer: queries endpoints
        # u_blocker: has block relation with u_author
        for uid, handle, name in [
            ("u_author", "author_user", "Author User"),
            ("u_viewer", "viewer_user", "Viewer User"),
            ("u_blocker", "blocker_user", "Blocker User"),
        ]:
            cursor.execute("""
                INSERT INTO users (id, email, handle, name, password_hash, salt, campus, location_city, bio, profile_visibility, role)
                VALUES (?, ?, ?, ?, 'secret_hash', 'secret_salt', 'Delhi University', 'New Delhi', 'Test Bio', 'public', 'student')
            """, (uid, f"{handle}@example.test", handle, name))

        # Seed session for u_viewer and u_blocker
        cls.viewer_token = "sess_viewer_token_123"
        cls.blocker_token = "sess_blocker_token_123"
        now_dt = datetime.now()
        exp_dt = (now_dt + timedelta(days=7)).isoformat()
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                       ("sess_viewer", "u_viewer", cls.viewer_token, exp_dt))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                       ("sess_blocker", "u_blocker", cls.blocker_token, exp_dt))

        # Bidirectional block between u_author and u_blocker
        cursor.execute("INSERT INTO blocks (user_id, blocked_user_id) VALUES (?, ?)", ("u_author", "u_blocker"))

        # Seed Community
        cursor.execute("""
            INSERT INTO communities (id, name, type, description, icon, city, visibility, members_count, creator_id)
            VALUES ('comm_main', 'Tech Club', 'Interest', 'A tech community', '💻', 'New Delhi', 'public', 10, 'u_author')
        """)

        # Seed Moments with various privacy and moderation states
        # (id, user_id, is_private, mod_status, caption, main_img)
        moments_to_seed = [
            ("m_pub_active", "u_author", 0, "active", "Sensitive Caption: Public Active", "https://img.test/active.jpg"),
            ("m_pub_null", "u_author", 0, None, "Sensitive Caption: Public Null", "https://img.test/null.jpg"),
            ("m_private", "u_author", 1, "active", "Sensitive Caption: Private Post", "https://img.test/private.jpg"),
            ("m_hidden", "u_author", 0, "hidden", "Sensitive Caption: Hidden Post", "https://img.test/hidden.jpg"),
            ("m_suspended", "u_author", 0, "suspended", "Sensitive Caption: Suspended Post", "https://img.test/suspended.jpg"),
            ("m_removed", "u_author", 1, "removed", "Sensitive Caption: Removed Post", "https://img.test/removed.jpg"),
            ("m_perspective_active", "u_viewer", 0, "active", "Viewer Perspective Active", "https://img.test/persp_active.jpg"),
            ("m_perspective_hidden", "u_author", 0, "hidden", "Author Perspective Hidden", "https://img.test/persp_hidden.jpg"),
        ]
        base_time = datetime(2026, 4, 1, 10, 0, 0)
        for i, (mid, uid, is_priv, mod, cap, img) in enumerate(moments_to_seed):
            cursor.execute("""
                INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, caption,
                                   circle, region, campus, location_city, is_private, moderation_status,
                                   exif_iso, exif_aperture, exif_shutter, created_at)
                VALUES (?, ?, 'Author', '@author', ?, '', ?,
                        'global', 'asia', 'Delhi University', 'New Delhi', ?, ?,
                        '100', 'f/1.8', '1/250s', ?)
            """, (mid, uid, img, cap, is_priv, mod, (base_time + timedelta(minutes=i)).isoformat()))

        # Seed Clusters
        # 1. cls_active: originator = m_pub_active
        # 2. cls_private: originator = m_private
        # 3. cls_hidden: originator = m_hidden
        # 4. cls_suspended: originator = m_suspended
        # 5. cls_removed: originator = m_removed
        clusters = [
            ("cls_active", "m_pub_active"),
            ("cls_private", "m_private"),
            ("cls_hidden", "m_hidden"),
            ("cls_suspended", "m_suspended"),
            ("cls_removed", "m_removed"),
        ]
        for cid, orig_m in clusters:
            cursor.execute("""
                INSERT INTO moment_clusters (id, cluster_type, originating_context, originator_moment_id,
                                            originator_user_id, community_id, visibility, status, created_at)
                VALUES (?, 'context', 'Test Context', ?, 'u_author', 'comm_main', 'public', 'active', ?)
            """, (cid, orig_m, base_time.isoformat()))

        # Perspective members for cls_active:
        # m_perspective_active (visible) and m_perspective_hidden (moderated)
        cursor.execute("""
            INSERT INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
            VALUES ('clsm_1', 'cls_active', 'u_viewer', 'm_perspective_active', 'perspective', ?)
        """, (base_time.isoformat(),))
        cursor.execute("""
            INSERT INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
            VALUES ('clsm_2', 'cls_active', 'u_author', 'm_perspective_hidden', 'perspective', ?)
        """, (base_time.isoformat(),))

        # Seed Invites
        invites = [
            ("inv_active", "CODE_ACTIVE", "comm_main", "m_pub_active"),
            ("inv_private", "CODE_PRIVATE", "comm_main", "m_private"),
            ("inv_hidden", "CODE_HIDDEN", "comm_main", "m_hidden"),
            ("inv_suspended", "CODE_SUSPENDED", "comm_main", "m_suspended"),
            ("inv_removed", "CODE_REMOVED", "comm_main", "m_removed"),
        ]
        for inv_id, code, comm_id, mom_id in invites:
            cursor.execute("""
                INSERT INTO community_invites (id, invite_code, community_id, inviter_user_id, moment_id, status, created_at)
                VALUES (?, ?, ?, 'u_author', ?, 'active', ?)
            """, (inv_id, code, comm_id, mom_id, base_time.isoformat()))

        conn.commit()
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = _ORIGINAL_DB_FILE
            server.DATABASE_URL = _ORIGINAL_DATABASE_URL
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get_json(self, path, token=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    # =========================================================================
    # 1. GET /api/cluster/<id>
    # =========================================================================

    def test_01_cluster_active_public_primary_visible(self):
        status, body = self._get_json("/api/cluster/cls_active")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        primary = cluster.get("primary_moment")
        self.assertIsNotNone(primary)
        self.assertEqual(primary["id"], "m_pub_active")
        self.assertIn("Sensitive Caption: Public Active", primary["caption"])
        self.assertEqual(primary["main_img"], "https://img.test/active.jpg")

    def test_02_cluster_private_primary_excluded(self):
        # Unauthenticated request
        status, body = self._get_json("/api/cluster/cls_private")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        self.assertIsNone(cluster.get("primary_moment"))
        # Ensure sensitive data from m_private is nowhere in the JSON payload
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Private Post", raw_text)
        self.assertNotIn("https://img.test/private.jpg", raw_text)

    def test_03_cluster_hidden_primary_excluded(self):
        status, body = self._get_json("/api/cluster/cls_hidden")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        self.assertIsNone(cluster.get("primary_moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Hidden Post", raw_text)
        self.assertNotIn("https://img.test/hidden.jpg", raw_text)

    def test_04_cluster_suspended_primary_excluded(self):
        status, body = self._get_json("/api/cluster/cls_suspended")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        self.assertIsNone(cluster.get("primary_moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Suspended Post", raw_text)
        self.assertNotIn("https://img.test/suspended.jpg", raw_text)

    def test_05_cluster_removed_primary_excluded(self):
        status, body = self._get_json("/api/cluster/cls_removed")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        self.assertIsNone(cluster.get("primary_moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Removed Post", raw_text)
        self.assertNotIn("https://img.test/removed.jpg", raw_text)

    def test_06_cluster_blocked_primary_excluded(self):
        # u_blocker has bidirectional block with u_author
        status, body = self._get_json("/api/cluster/cls_active", token=self.blocker_token)
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        cluster = body["cluster"]
        self.assertIsNone(cluster.get("primary_moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Public Active", raw_text)

    def test_07_cluster_perspectives_filter_moderation(self):
        status, body = self._get_json("/api/cluster/cls_active")
        self.assertEqual(status, 200)
        cluster = body["cluster"]
        persp_ids = [p["id"] for p in cluster.get("perspectives", [])]
        # Active perspective is visible
        self.assertIn("m_perspective_active", persp_ids)
        # Hidden perspective is filtered out
        self.assertNotIn("m_perspective_hidden", persp_ids)
        raw_text = json.dumps(body)
        self.assertNotIn("Author Perspective Hidden", raw_text)

    def test_08_cluster_unauthenticated_cannot_pivot_to_private(self):
        status, body = self._get_json("/api/cluster/cls_private")
        self.assertEqual(status, 200)
        self.assertIsNone(body["cluster"].get("primary_moment"))

    # =========================================================================
    # 2. GET /api/user/profile
    # =========================================================================

    def test_09_profile_active_public_moments_visible(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        moment_ids = [m["id"] for m in body.get("moments", [])]
        self.assertIn("m_pub_active", moment_ids)
        self.assertIn("m_pub_null", moment_ids)

    def test_10_profile_private_moments_excluded(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        moment_ids = [m["id"] for m in body.get("moments", [])]
        self.assertNotIn("m_private", moment_ids)
        raw_text = json.dumps(body.get("moments", []))
        self.assertNotIn("Sensitive Caption: Private Post", raw_text)

    def test_11_profile_hidden_moments_excluded(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        moment_ids = [m["id"] for m in body.get("moments", [])]
        self.assertNotIn("m_hidden", moment_ids)
        raw_text = json.dumps(body.get("moments", []))
        self.assertNotIn("Sensitive Caption: Hidden Post", raw_text)

    def test_12_profile_suspended_moments_excluded(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        moment_ids = [m["id"] for m in body.get("moments", [])]
        self.assertNotIn("m_suspended", moment_ids)
        raw_text = json.dumps(body.get("moments", []))
        self.assertNotIn("Sensitive Caption: Suspended Post", raw_text)

    def test_13_profile_removed_moments_excluded(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        moment_ids = [m["id"] for m in body.get("moments", [])]
        self.assertNotIn("m_removed", moment_ids)
        raw_text = json.dumps(body.get("moments", []))
        self.assertNotIn("Sensitive Caption: Removed Post", raw_text)

    def test_14_profile_user_field_allowlist_preserved(self):
        status, body = self._get_json("/api/user/profile?user_id=u_author")
        self.assertEqual(status, 200)
        user_obj = body.get("user", {})
        # Sensitive credentials must NEVER be leaked
        self.assertNotIn("password_hash", user_obj)
        self.assertNotIn("salt", user_obj)
        self.assertNotIn("email", user_obj)
        # Expected safe fields must be present
        self.assertEqual(user_obj.get("id"), "u_author")
        self.assertEqual(user_obj.get("handle"), "author_user")
        self.assertEqual(user_obj.get("name"), "Author User")
        self.assertEqual(user_obj.get("profile_visibility"), "public")
        # Moment count matches only visible moments (m_pub_active, m_pub_null)
        self.assertEqual(user_obj.get("momentCount"), 2)

    # =========================================================================
    # 3. GET /api/invite/preview
    # =========================================================================

    def test_15_invite_preview_active_public_moment_visible(self):
        status, body = self._get_json("/api/invite/preview?code=CODE_ACTIVE")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        invite = body.get("invite", {})
        moment = invite.get("moment")
        self.assertIsNotNone(moment)
        self.assertEqual(moment["id"], "m_pub_active")
        self.assertIn("Sensitive Caption: Public Active", moment["caption"])
        self.assertEqual(moment["main_img"], "https://img.test/active.jpg")
        self.assertFalse(moment.get("is_private"))

    def test_16_invite_preview_private_moment_no_sensitive_data(self):
        status, body = self._get_json("/api/invite/preview?code=CODE_PRIVATE")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        invite = body.get("invite", {})
        moment = invite.get("moment", {}) or {}
        # Sensitive caption and image must NEVER be leaked
        self.assertNotIn("caption", moment)
        self.assertNotIn("main_img", moment)
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Private Post", raw_text)
        self.assertNotIn("https://img.test/private.jpg", raw_text)

    def test_17_invite_preview_hidden_moment_excluded(self):
        status, body = self._get_json("/api/invite/preview?code=CODE_HIDDEN")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        invite = body.get("invite", {})
        self.assertIsNone(invite.get("moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Hidden Post", raw_text)
        self.assertNotIn("https://img.test/hidden.jpg", raw_text)

    def test_18_invite_preview_suspended_moment_excluded(self):
        status, body = self._get_json("/api/invite/preview?code=CODE_SUSPENDED")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        invite = body.get("invite", {})
        self.assertIsNone(invite.get("moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Suspended Post", raw_text)
        self.assertNotIn("https://img.test/suspended.jpg", raw_text)

    def test_19_invite_preview_removed_moment_excluded(self):
        status, body = self._get_json("/api/invite/preview?code=CODE_REMOVED")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        invite = body.get("invite", {})
        self.assertIsNone(invite.get("moment"))
        raw_text = json.dumps(body)
        self.assertNotIn("Sensitive Caption: Removed Post", raw_text)
        self.assertNotIn("https://img.test/removed.jpg", raw_text)

    def test_20_invite_preview_metadata_intact(self):
        for code in ["CODE_ACTIVE", "CODE_PRIVATE", "CODE_HIDDEN", "CODE_SUSPENDED", "CODE_REMOVED"]:
            status, body = self._get_json(f"/api/invite/preview?code={code}")
            self.assertEqual(status, 200)
            self.assertTrue(body["success"])
            invite = body.get("invite", {})
            self.assertTrue(invite.get("is_valid"))
            self.assertEqual(invite.get("community", {}).get("id"), "comm_main")
            self.assertEqual(invite.get("community", {}).get("name"), "Tech Club")
            self.assertEqual(invite.get("inviter", {}).get("id"), "u_author")


if __name__ == "__main__":
    unittest.main(verbosity=2)
