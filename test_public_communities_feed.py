"""
Automated Test Suite for Kindid Public Communities Cross-Community Feed
Verifies:
1. Public Community moments appear in the aggregate view (/api/community/public-feed).
2. Recent Moments are sorted newest-first and pagination cursor works without duplicates.
3. Live Pulse only returns records meeting verified 2-hour live window (-60 <= age <= 7200s).
4. Honest empty state when no verified live activity exists (active_count = 0, QUIET RIGHT NOW).
5. Private Community moments are strictly excluded server-side.
6. Private moments (is_private = 1) are strictly excluded server-side.
7. Blocked users' moments are excluded.
8. Global feed isolation is preserved (no community bleeding into global feed).
"""

import json
import os
import shutil
import socket
import tempfile
import unittest
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta

import server
from server import KandidHandler

TOKEN_TEST_USER = "tok_test_feed_user"
TOKEN_BLOCKED_USER = "tok_test_blocked_user"


def _insert_post(cursor, pid, uid, handle, name, caption, comm_id, is_private, created_at):
    cursor.execute("""
        INSERT OR REPLACE INTO posts (
            id, user_id, author_handle, author_name, main_img, pip_img,
            caption, primary_community_id, is_private, created_at, moderation_status
        ) VALUES (?, ?, ?, ?, 'https://example.com/main.jpg', 'https://example.com/pip.jpg', ?, ?, ?, ?, 'active')
    """, (pid, uid, handle, name, caption, comm_id, is_private, created_at))


class TestPublicCommunitiesFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_public_feed_test_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()

        # Seed test users
        users = [
            ("u_feed_1", "user1@test.com", "user1", "User One", "student"),
            ("u_feed_2", "user2@test.com", "user2", "User Two", "student"),
            ("u_feed_blocked", "blocked@test.com", "blocked_u", "Blocked User", "student"),
        ]
        for uid, email, handle, name, role in users:
            cursor.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) "
                "VALUES (?, ?, ?, ?, 'h', 's', 'North City University', ?, 1, 1, 'active')",
                (uid, email, handle, name, role)
            )

        # Seed sessions
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES ('s_1', 'u_feed_1', ?, '2099-01-01T00:00:00Z')", (TOKEN_TEST_USER,))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES ('s_2', 'u_feed_blocked', ?, '2099-01-01T00:00:00Z')", (TOKEN_BLOCKED_USER,))

        # Block relationship: u_feed_1 blocked u_feed_blocked
        cursor.execute("INSERT INTO blocks (user_id, blocked_user_id) VALUES ('u_feed_1', 'u_feed_blocked')")

        # Seed Communities: Public Community A, Public Community B, Private Community C
        cls.comm_pub_a = f"comm_pub_a_{uuid.uuid4().hex[:6]}"
        cls.comm_pub_b = f"comm_pub_b_{uuid.uuid4().hex[:6]}"
        cls.comm_priv = f"comm_priv_{uuid.uuid4().hex[:6]}"

        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Public Arts Collective', 'Interest', 'Delhi', 'Public Arts Space', 'public', 10),
                   (?, 'Public Tech Commons', 'Campus', 'Delhi', 'Public Tech Space', 'public', 15),
                   (?, 'Secret Vault Club', 'Interest', 'Delhi', 'Private Vault Space', 'private', 5)
        """, (cls.comm_pub_a, cls.comm_pub_b, cls.comm_priv))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        if os.path.exists(cls._tmpdir):
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _req(self, path, method="GET", token=None, body=None):
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

        t = server.threading.Thread(target=run_handler)
        t.daemon = True
        t.start()

        body_bytes = b""
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")

        req = f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\nCookie: session_token={token}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "Connection: close\r\n\r\n"

        s2.sendall(req.encode("utf-8") + body_bytes)

        resp = b""
        while True:
            chunk = s2.recv(4096)
            if not chunk:
                break
            resp += chunk
        s2.close()
        t.join(timeout=2.0)

        header_part, _, body_part = resp.partition(b"\r\n\r\n")
        lines = header_part.decode("latin1", errors="replace").split("\r\n")
        status_code = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 500

        data = {}
        if body_part:
            try:
                data = json.loads(body_part.decode("utf-8", errors="replace"))
            except Exception:
                data = {"raw": body_part.decode("utf-8", errors="replace")}
        return status_code, data

    def test_01_public_communities_feed_aggregates_moments(self):
        """Moments published to public communities appear in aggregate public feed"""
        now = datetime.now(timezone.utc)
        m1_time = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        m2_time = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_pub_1', 'u_feed_2', 'user2', 'User Two', 'Art Moment', self.comm_pub_a, 0, m1_time)
        _insert_post(cursor, 'post_pub_2', 'u_feed_2', 'user2', 'User Two', 'Tech Moment', self.comm_pub_b, 0, m2_time)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=moments", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        moments = res.get("moments", [])
        post_ids = [m["id"] for m in moments]
        self.assertIn("post_pub_1", post_ids)
        self.assertIn("post_pub_2", post_ids)

        # Check community attribution is present
        for m in moments:
            if m["id"] == "post_pub_1":
                self.assertEqual(m.get("community_name"), "Public Arts Collective")
                self.assertEqual(m.get("community_visibility"), "public")
            elif m["id"] == "post_pub_2":
                self.assertEqual(m.get("community_name"), "Public Tech Commons")
                self.assertEqual(m.get("community_visibility"), "public")

    def test_02_recent_moments_newest_first_and_pagination(self):
        """Recent moments are sorted newest-first and pagination cursor works stably"""
        now = datetime.now(timezone.utc)
        p_old_time = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        p_new_time = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")

        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_pagi_1', 'u_feed_2', 'user2', 'User Two', 'Newest Moment', self.comm_pub_a, 0, p_new_time)
        _insert_post(cursor, 'post_pagi_2', 'u_feed_2', 'user2', 'User Two', 'Older Moment', self.comm_pub_b, 0, p_old_time)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=moments&limit=1", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        moments = res.get("moments", [])
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0]["id"], "post_pagi_1")
        self.assertTrue(res.get("has_more"))
        cursor_val = res.get("next_cursor")
        self.assertTrue(bool(cursor_val))

        # Fetch page 2 using cursor
        status2, res2 = self._req(f"/api/community/public-feed?view=moments&limit=1&cursor={urllib.parse.quote(cursor_val)}", token=TOKEN_TEST_USER)
        self.assertEqual(status2, 200)
        moments2 = res2.get("moments", [])
        self.assertEqual(len(moments2), 1)
        self.assertNotEqual(moments2[0]["id"], "post_pagi_1")

    def test_03_private_community_content_strictly_excluded(self):
        """Private Community moments and metadata are NEVER returned in public feed"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_priv_leak_test', 'u_feed_2', 'user2', 'User Two', 'Secret Vault Moment', self.comm_priv, 0, now)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=moments", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        post_ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("post_priv_leak_test", post_ids)

        # Also verify in Live Pulse view
        status_p, res_p = self._req("/api/community/public-feed?view=pulse", token=TOKEN_TEST_USER)
        self.assertEqual(status_p, 200)
        pulse_post_ids = [m["id"] for m in res_p.get("moments", [])]
        self.assertNotIn("post_priv_leak_test", pulse_post_ids)

    def test_04_private_moments_excluded(self):
        """Moments marked is_private = 1 are strictly excluded even in public community"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_personal_priv_test', 'u_feed_2', 'user2', 'User Two', 'Personal Journal', self.comm_pub_a, 1, now)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=moments", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        post_ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("post_personal_priv_test", post_ids)

    def test_05_live_pulse_verified_activity_window(self):
        """Live Pulse only includes moments within the 2-hour window (<= 7200s)"""
        now = datetime.now(timezone.utc)
        live_time = (now - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        stale_time = (now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_pulse_live', 'u_feed_2', 'user2', 'User Two', 'Live Moment', self.comm_pub_a, 0, live_time)
        _insert_post(cursor, 'post_pulse_stale', 'u_feed_2', 'user2', 'User Two', 'Old Stale Moment', self.comm_pub_b, 0, stale_time)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=pulse", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        pulse = res.get("pulse", {})
        self.assertTrue(pulse.get("has_live_activity"))
        self.assertEqual(pulse.get("pulse_state"), "LIVE NOW")
        pulse_post_ids = [m["id"] for m in res.get("moments", [])]
        self.assertIn("post_pulse_live", pulse_post_ids)
        self.assertNotIn("post_pulse_stale", pulse_post_ids)

    def test_06_live_pulse_honest_empty_state_when_all_stale(self):
        """When all moments are older than 2 hours, Live Pulse returns honest empty state"""
        old_time = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET created_at = ?", (old_time,))
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=pulse", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        pulse = res.get("pulse", {})
        self.assertFalse(pulse.get("has_live_activity"))
        self.assertEqual(pulse.get("active_count"), 0)
        self.assertEqual(pulse.get("pulse_state"), "QUIET RIGHT NOW")
        self.assertEqual(res.get("moments", []), [])

    def test_07_blocked_users_excluded(self):
        """Moments from blocked users are excluded for the viewer"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, 'post_blocked_user', 'u_feed_blocked', 'blocked_u', 'Blocked User', 'Blocked Moment', self.comm_pub_a, 0, now)
        conn.commit()
        conn.close()

        status, res = self._req("/api/community/public-feed?view=moments", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        post_ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("post_blocked_user", post_ids)

    def test_08_global_feed_isolation_preserved(self):
        """Community moments do not bleed into the global feed / FOR YOU"""
        status, res = self._req("/api/feed?circle=all", token=TOKEN_TEST_USER)
        self.assertEqual(status, 200)
        feed_posts = res.get("feed", [])
        for p in feed_posts:
            self.assertNotEqual(p.get("id"), "post_pub_1")
            self.assertNotEqual(p.get("id"), "post_pub_2")

    def test_09_personal_feed_moments_strictly_excluded(self):
        """Personal feed / Open Journal moments (no community) are NEVER in public community feed or live pulse"""
        now = datetime.now(timezone.utc)
        fresh_time = (now - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")

        conn = server.get_db()
        cursor = conn.cursor()
        # Personal Open Journal moment: primary_community_id = '', circle = 'foryou'
        cursor.execute("""
            INSERT OR REPLACE INTO posts (
                id, user_id, author_handle, author_name, main_img, pip_img,
                caption, primary_community_id, context_community_id, circle, is_private, created_at, moderation_status
            ) VALUES (
                'post_personal_feed_1', 'u_feed_2', 'user2', 'User Two', 'https://example.com/main.jpg', 'https://example.com/pip.jpg',
                'My Personal Diary Feed Post', '', '', 'foryou', 0, ?, 'active'
            )
        """, (fresh_time,))
        # Another personal feed moment without circle: primary_community_id = ''
        cursor.execute("""
            INSERT OR REPLACE INTO posts (
                id, user_id, author_handle, author_name, main_img, pip_img,
                caption, primary_community_id, context_community_id, circle, is_private, created_at, moderation_status
            ) VALUES (
                'post_personal_feed_2', 'u_feed_2', 'user2', 'User Two', 'https://example.com/main.jpg', 'https://example.com/pip.jpg',
                'General Open Journal Moment', '', '', NULL, 0, ?, 'active'
            )
        """, (fresh_time,))
        conn.commit()
        conn.close()

        # Check Recent Moments in public community feed
        status_m, res_m = self._req("/api/community/public-feed?view=moments", token=TOKEN_TEST_USER)
        self.assertEqual(status_m, 200)
        recent_ids = [m["id"] for m in res_m.get("moments", [])]
        self.assertNotIn("post_personal_feed_1", recent_ids)
        self.assertNotIn("post_personal_feed_2", recent_ids)

        # Check Live Pulse in public community feed
        status_p, res_p = self._req("/api/community/public-feed?view=pulse", token=TOKEN_TEST_USER)
        self.assertEqual(status_p, 200)
        pulse_ids = [m["id"] for m in res_p.get("moments", [])]
        self.assertNotIn("post_personal_feed_1", pulse_ids)
        self.assertNotIn("post_personal_feed_2", pulse_ids)


if __name__ == "__main__":
    unittest.main()
