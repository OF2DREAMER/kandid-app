#!/usr/bin/env python3
"""
Focused regression test for Day-3 Task 1: moderation visibility leak.

Verifies that posts whose moderation_status is 'hidden', 'removed' or
'suspended' are excluded from both public endpoints:

  - GET /api/global (region + all-regions branches)
  - GET /api/feed

while 'active' and NULL moderation_status posts remain publicly visible,
is_private=1 posts stay excluded, and the existing response envelopes plus
feed pagination behavior are unchanged.

Fixture is production-accurate:
  - 'hidden'   mirrors the moderation "hide" action: moderation_status='hidden'
               with is_private left untouched (this is the leak being fixed).
  - 'removed'  mirrors the moderation "remove" action: it sets both
               moderation_status='removed' AND is_private=1.
  - 'suspended' posts are seeded directly to exercise the SQL predicate.

Runs against a throwaway SQLite database; data/kandid.db is never touched.
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

import server  # noqa: E402

REGION_POST = "p_mod_region_active"
HIDDEN_POST = "p_mod_hidden"
REMOVED_POST = "p_mod_removed"
SUSPENDED_POST = "p_mod_suspended"
ACTIVE_POST = "p_mod_active"
NULL_POST = "p_mod_null"
PRIVATE_POST = "p_mod_private"

# All public posts live in the global circle so /api/global sees them too.
PUBLIC_POSTS = [REGION_POST, HIDDEN_POST, REMOVED_POST, SUSPENDED_POST, ACTIVE_POST, NULL_POST]
GLOBAL_POSTS = [REGION_POST, ACTIVE_POST, NULL_POST, HIDDEN_POST, SUSPENDED_POST]


class ModerationVisibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_d3_1_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        # Force a disposable SQLite database for this test run.
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_d3_1.db")
        server.init_db()

        cls.user = "u_mod_author"
        conn = server.get_db()
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.user, "mod_author@example.test", "mod_author", "Author", "hash", "salt"),
        )

        # 'removed' mirrors the real moderation remove action: it also sets
        # is_private=1 (see server.py moderation handler), so it is seeded
        # with is_private=1 on top of moderation_status='removed'.
        rows = [
            # (id, circle, region, is_private, moderation_status, caption)
            (REGION_POST, "global", "asia", 0, "active", "region visible"),
            (ACTIVE_POST, "global", "europe", 0, "active", "active visible"),
            (NULL_POST, "global", "americas", 0, None, "legacy null visible"),
            (HIDDEN_POST, "global", "europe", 0, "hidden", "hidden must not leak"),
            (SUSPENDED_POST, "global", "europe", 0, "suspended", "suspended must not leak"),
            (REMOVED_POST, "campus", "asia", 1, "removed", "removed must not leak"),
            (PRIVATE_POST, "campus", "asia", 1, "active", "private stays private"),
        ]
        base = datetime(2026, 3, 1, 9, 0, 0)
        for i, (pid, circle, region, is_private, mod, caption) in enumerate(rows):
            conn.execute(
                """INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img,
                                       caption, circle, region, is_private, moderation_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, cls.user, "Author", "@mod_author", "img_%s.jpg" % pid, "pip_%s.jpg" % pid,
                    caption, circle, region, is_private, mod,
                    (base + timedelta(seconds=i)).isoformat(),
                ),
            )
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
            server.DB_FILE = cls._original_db_file
            server.DATABASE_URL = cls._original_database_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get_json(self, path):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path))
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _ids(self, payload, key):
        return {m["id"] for m in payload[key]}

    # ---- hidden must not leak anywhere -----------------------------------

    def test_01_hidden_absent_from_global(self):
        _, body = self._get_json("/api/global")
        ids = self._ids(body, "moments")
        self.assertNotIn(HIDDEN_POST, ids)

    def test_02_hidden_absent_from_feed(self):
        _, body = self._get_json("/api/feed")
        ids = self._ids(body, "feed")
        self.assertNotIn(HIDDEN_POST, ids)

    def test_03_removed_absent_from_global(self):
        _, body = self._get_json("/api/global")
        ids = self._ids(body, "moments")
        self.assertNotIn(REMOVED_POST, ids)

    def test_04_removed_absent_from_feed(self):
        _, body = self._get_json("/api/feed")
        ids = self._ids(body, "feed")
        self.assertNotIn(REMOVED_POST, ids)

    def test_05_suspended_absent_from_global(self):
        _, body = self._get_json("/api/global")
        ids = self._ids(body, "moments")
        self.assertNotIn(SUSPENDED_POST, ids)

    def test_06_suspended_absent_from_feed(self):
        _, body = self._get_json("/api/feed")
        ids = self._ids(body, "feed")
        self.assertNotIn(SUSPENDED_POST, ids)

    # ---- visible states remain visible ------------------------------------

    def test_07_active_post_remains_visible(self):
        _, g = self._get_json("/api/global")
        _, f = self._get_json("/api/feed")
        self.assertIn(ACTIVE_POST, self._ids(g, "moments"))
        self.assertIn(ACTIVE_POST, self._ids(f, "feed"))

    def test_08_null_moderation_status_remains_visible(self):
        _, g = self._get_json("/api/global")
        _, f = self._get_json("/api/feed")
        self.assertIn(NULL_POST, self._ids(g, "moments"))
        self.assertIn(NULL_POST, self._ids(f, "feed"))

    # ---- privacy behavior unchanged ----------------------------------------

    def test_09_private_post_still_excluded(self):
        _, g = self._get_json("/api/global")
        _, f = self._get_json("/api/feed")
        self.assertNotIn(PRIVATE_POST, self._ids(g, "moments"))
        self.assertNotIn(PRIVATE_POST, self._ids(f, "feed"))

    # ---- response envelopes unchanged ---------------------------------------

    def test_10_global_envelope_unchanged(self):
        _, g = self._get_json("/api/global")
        self.assertEqual(
            set(g.keys()), {"success", "window", "region", "moments"},
            "/api/global envelope changed",
        )
        self.assertEqual(g["region"], "all")
        self.assertIn("moments", g)

    def test_11_feed_envelope_unchanged(self):
        _, f = self._get_json("/api/feed")
        self.assertEqual(
            set(f.keys()), {"success", "feed", "next_cursor", "has_more"},
            "/api/feed envelope changed",
        )

    def test_12_feed_pagination_unchanged(self):
        # limit=1 -> has_more True, next_cursor == newest returned post's
        # created_at; the follow-up page returns strictly older posts only.
        _, p1 = self._get_json("/api/feed?limit=1")
        self.assertTrue(p1["has_more"])
        self.assertEqual(len(p1["feed"]), 1)
        cursor = p1["next_cursor"]
        self.assertTrue(cursor)
        _, p2 = self._get_json("/api/feed?limit=1&cursor=%s" % urllib.parse.quote(cursor))
        self.assertEqual(len(p2["feed"]), 1)
        self.assertLess(p2["feed"][0]["created_at"], cursor)
        # no duplicate posts across pages
        self.assertNotEqual(p1["feed"][0]["id"], p2["feed"][0]["id"])

    # ---- region branch of /api/global still honors the filter ---------------

    def test_13_region_branch_excludes_hidden(self):
        _, g = self._get_json("/api/global?region=asia")
        self.assertEqual(g["region"], "asia")
        ids = self._ids(g, "moments")
        self.assertIn(REGION_POST, ids)          # active region post visible
        self.assertNotIn(HIDDEN_POST, ids)       # hidden never leaks
        self.assertNotIn(REMOVED_POST, ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
