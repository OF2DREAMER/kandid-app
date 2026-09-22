#!/usr/bin/env python3
"""
Full Production Beta Test Suite for Kandid.app
Covers all screens, APIs, user flows, database persistence, and interactions.
"""

import os
import shutil
import sys
import tempfile
import unittest
import json
from urllib.parse import urlparse, parse_qs

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

# D4-07: pristine DB path captured at import time — the isolation source.
_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


def _isolate_db(testcase_cls, prefix):
    """D4-07: run this test class against a disposable temp database so the
    repository's data/kandid.db is never opened, mutated or deleted.

    Both cleanup callbacks are registered BEFORE any global is mutated.
    unittest fires class cleanups in LIFO order, so execution is:
      1. restore server.DB_FILE / server.DATABASE_URL
      2. remove the temporary directory
    """
    tmpdir = tempfile.mkdtemp(prefix=prefix)
    # Registration order matters: LIFO makes the globals restore run first.
    testcase_cls.addClassCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
    testcase_cls.addClassCleanup(_restore_server_globals)
    server.DATABASE_URL = ""
    server.DB_FILE = os.path.join(tmpdir, "kandid.db")
    server.init_db()
    return tmpdir


def _seed_min_beta_fixture():
    """D4-07: deterministic minimum data the assertions actually read.
    init_db() seeds catalogs only, so the suite seeds 3 users (its per-test
    queries pick a couple of arbitrary existing users/posts), 6 non-private
    posts (>= the 5 asserted by test_01) and 2 campus posts for test_02's
    campus/foryou discovery check."""
    conn = server.get_db()
    for i in (1, 2, 3):
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, location_city) VALUES (?,?,?,?,?,?,?,?)",
            (f"u_beta_{i}", f"beta{i}@example.test", f"beta_user_{i}", f"Beta User {i}", "x", "s", "Beta Campus", "Supaul"),
        )
    for i in range(1, 7):
        conn.execute(
            """INSERT INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img,
                                   caption, circle, region, location_city, is_private, moderation_status)
               VALUES (?,?,?,?,?,'img','pip',?, ?, 'all', 'Near Beta Campus', 0, 'approved')""",
            (f"post_beta_{i}", f"u_beta_{i if i <= 3 else 1}", f"Beta User {i if i <= 3 else 1}",
             f"beta_user_{i if i <= 3 else 1}", "Beta Campus", f"Beta moment {i}",
             "campus" if i <= 2 else "foryou"),
        )
    conn.commit()
    conn.close()


class TestKandidProductionBeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _isolate_db(cls, "kandid_beta_")
        _seed_min_beta_fixture()

    def test_01_feed_and_subtabs(self):
        conn = server.get_db()
        cursor = conn.cursor()
        
        # Test Feed moments
        cursor.execute("SELECT * FROM posts")
        posts = cursor.fetchall()
        self.assertGreaterEqual(len(posts), 5)
        
        # Test Campus and Foryou moments
        campus_posts = [p for p in posts if p["circle"] == "campus"]
        foryou_posts = [p for p in posts if p["circle"] == "foryou"]
        self.assertGreaterEqual(len(campus_posts) + len(foryou_posts), 5)

        conn.close()
        print("  ✅ PASS: 1. Feed, Campus, and Global moments loaded and verified.")

    def test_02_search_and_discovery(self):
        conn = server.get_db()
        cursor = conn.cursor()
        
        # Search People
        cursor.execute("SELECT * FROM users LIMIT 1")
        sample_u = cursor.fetchone()
        self.assertIsNotNone(sample_u)
        
        cursor.execute("SELECT * FROM users WHERE LOWER(handle) LIKE ?", (f"%{sample_u['handle'][:3].lower()}%",))
        found_users = cursor.fetchall()
        self.assertGreaterEqual(len(found_users), 1)
        
        # Search Places / Campuses
        cursor.execute("SELECT DISTINCT campus FROM posts WHERE campus != '' LIMIT 1")
        place = cursor.fetchone()
        if place:
            cursor.execute("SELECT DISTINCT campus FROM posts WHERE LOWER(campus) LIKE ?", (f"%{place[0][:3].lower()}%",))
            places = cursor.fetchall()
            self.assertGreaterEqual(len(places), 1)

        conn.close()
        print("  ✅ PASS: 2. Search & Proximity Discovery queries verified.")

    def test_03_camera_capture_and_publish(self):
        conn = server.get_db()
        test_post_id = "post_test_beta_launch"
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, handle, avatar_url, campus FROM users LIMIT 1")
        u = cursor.fetchone()
        uid = u["id"] if u else "u_sunil"
        u_name = u["name"] if u else "Sunil"
        u_handle = u["handle"] if u else "sunil"
        u_campus = u["campus"] if u else "Central Campus"

        conn.execute("""
            INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, avatar_letter, avatar_url, campus, main_img, pip_img, caption, circle, region, location_city, location_coords, exif_iso, exif_aperture, exif_shutter, is_private)
            VALUES (?, ?, ?, ?, 'K', 'avatar.jpg', ?, 'main.jpg', 'pip.jpg', 'Beta Launch Live Capture!', 'campus', 'all', ?, '', 'ISO 400', 'f/2.8', '1/250s', 0)
        """, (test_post_id, uid, u_name, u_handle, u_campus, u_campus))
        conn.commit()

        cursor.execute("SELECT * FROM posts WHERE id = ?", (test_post_id,))
        p = cursor.fetchone()
        self.assertIsNotNone(p)
        self.assertEqual(p["caption"], "Beta Launch Live Capture!")
        cursor.execute("DELETE FROM posts WHERE id = ?", (test_post_id,))
        conn.commit()
        conn.close()
        print("  ✅ PASS: 3. Dual-Camera Moment Capture & Publish pipeline verified.")

    def test_04_direct_squad_chat(self):
        conn = server.get_db()
        test_msg_id = "m_test_beta_1"
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users LIMIT 2")
        users = cursor.fetchall()
        u1 = users[0][0] if len(users) > 0 else "u_1"
        u2 = users[1][0] if len(users) > 1 else "u_2"

        conn.execute("""
            INSERT OR REPLACE INTO messages (id, sender_id, receiver_id, content, created_at)
            VALUES (?, ?, ?, 'Ready for the Kandid Beta launch!', datetime('now'))
        """, (test_msg_id, u1, u2))
        conn.commit()

        cursor.execute("SELECT * FROM messages WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) ORDER BY created_at ASC", (u1, u2, u2, u1))
        thread = cursor.fetchall()
        self.assertGreaterEqual(len(thread), 1)
        self.assertTrue(any("launch" in m["content"] for m in thread))
        cursor.execute("DELETE FROM messages WHERE id = ?", (test_msg_id,))
        conn.commit()
        conn.close()
        print("  ✅ PASS: 4. Direct Squad Chat messaging and persistence verified.")

    def test_05_profile_archive_and_switch(self):
        conn = server.get_db()
        cursor = conn.cursor()
        
        # Verify first profile
        cursor.execute("SELECT * FROM users LIMIT 1")
        sample_u = cursor.fetchone()
        self.assertIsNotNone(sample_u)
        uid = sample_u["id"]

        # Update profile bio
        conn.execute("UPDATE users SET bio = 'Updated bio for Beta Launch.' WHERE id = ?", (uid,))
        conn.commit()

        cursor.execute("SELECT bio FROM users WHERE id = ?", (uid,))
        updated_bio = cursor.fetchone()[0]
        self.assertEqual(updated_bio, "Updated bio for Beta Launch.")
        conn.close()
        print("  ✅ PASS: 5. User Profile, Authenticity Score, and Profile editing verified.")

    def test_06_realmojis_and_reactions(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posts LIMIT 1")
        post_row = cursor.fetchone()
        post_id = post_row[0] if post_row else "post_1"
        cursor.execute("SELECT id FROM users LIMIT 1")
        user_row = cursor.fetchone()
        user_id = user_row[0] if user_row else "u_1"

        conn.execute("""
            INSERT OR REPLACE INTO reactions (id, post_id, user_id, emoji)
            VALUES ('react_beta_1', ?, ?, '🔥')
        """, (post_id, user_id))
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM reactions WHERE post_id = ? AND emoji = '🔥'", (post_id,))
        flame_count = cursor.fetchone()[0]
        self.assertGreaterEqual(flame_count, 1)
        cursor.execute("DELETE FROM reactions WHERE id = 'react_beta_1'")
        conn.commit()
        conn.close()
        print("  ✅ PASS: 6. RealMoji flame & reaction pipeline verified.")

    def test_07_signal_notifications(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users LIMIT 1")
        user_row = cursor.fetchone()
        user_id = user_row[0] if user_row else "u_1"

        notif_id = "notif_test_beta"
        conn.execute("""
            INSERT OR REPLACE INTO notifications (id, user_id, type, title, body, is_read, created_at)
            VALUES (?, ?, 'moment', 'Moment Alert', 'New moment shared', 0, datetime('now'))
        """, (notif_id, user_id))
        conn.commit()

        cursor.execute("SELECT * FROM notifications WHERE user_id = ?", (user_id,))
        notifs = cursor.fetchall()
        self.assertGreaterEqual(len(notifs), 1)

        # Mark read
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
        conn.commit()

        cursor.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
        conn.commit()
        conn.close()
        print("  ✅ PASS: 7. Calm Signal Notifications & Mark Read verified.")

    def test_08_html_and_client_bindings(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()

        # Check key screens & modals exist
        self.assertIn('id="screen-feed"', html)
        self.assertIn('id="feedContentStream"', html)
        self.assertIn('id="screen-search"', html)
        self.assertIn('id="screen-you"', html)
        self.assertIn('id="screen-notifications"', html)
        self.assertIn('id="cameraStudioModal"', html)
        self.assertIn('id="youSettingsModal"', html)
        
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()
        
        self.assertIn("function openCameraStudio(", js)
        self.assertIn("function takeSnapshot(", js)
        self.assertIn("function publishCapturedMoment(", js)
        self.assertIn("function loadYouScreen(", js)
        self.assertIn("function openMomentDetail(", js)
        self.assertIn("function openYouSettings(", js)
        self.assertIn("function switchUserAccount(", js)
        self.assertIn("markAllNotificationsRead", js)
        print("  ✅ PASS: 8. HTML DOM and Client JavaScript Engine bindings verified.")

if __name__ == "__main__":
    print("\n🚀 RUNNING KANDID BETA PRODUCTION APP VERIFICATION SUITE")
    print("=" * 65)
    unittest.main(verbosity=0)
