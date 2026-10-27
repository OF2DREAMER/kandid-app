#!/usr/bin/env python3
"""
Focused regression coverage for /api/feed keyset cursor pagination.

The suite runs a real KandidHandler against a throwaway SQLite database. It
never opens or mutates data/kandid.db.

Covered:
  1. Composite (created_at, id) index exists after init_db().
  2. Cursor helpers round-trip, accept legacy ISO timestamps, and reject junk.
  3. A full cursor walk returns every visible moment exactly once, in order,
     with has_more true only on intermediate pages.
  4. Ties on identical created_at survive a page boundary.
  5. Pages stay full while blocked authors are excluded in SQL.
  6. The grouped reaction query is used (constant statement count).
  7. Cross-circle, malformed, oversized and empty cursors are safe.
  8. Existing feed isolation rules still exclude community, drop, perspective,
     private, hidden, removed and suspended content.
"""

import base64
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

TOKEN = "feed_cursor_test_token"
VIEWER = "u_feed_cursor_viewer"
BLOCKED = "u_feed_cursor_blocked"
REVERSE = "u_feed_cursor_reverse"
AUTHOR = "u_feed_cursor_author"

BASE = datetime(2026, 1, 1, 12, 0, 0)

VISIBLE_ALL = []
VISIBLE_CAMPUS = []
VISIBLE_GLOBAL = []
ISOLATED_IDS = []


def _t(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def _add_post(conn, pid, author, circle, created_at, primary_community_id="",
              context_community_id="", drop_id="", moderation_status="active",
              is_private=0):
    conn.execute(
        """INSERT OR REPLACE INTO posts
           (id, user_id, author_name, author_handle, main_img, pip_img, caption,
            circle, created_at, moderation_status, is_private,
            primary_community_id, context_community_id, drop_id, cluster_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')""",
        (
            pid, author, author.upper(), "@" + author,
            "main_%s.jpg" % pid, "pip_%s.jpg" % pid, "caption %s" % pid,
            circle, created_at, moderation_status, is_private,
            primary_community_id, context_community_id, drop_id,
        ),
    )


class FeedCursorPaginationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_feed_cursor_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_feed_cursor.db")
        server.init_db()

        conn = server.get_db()
        for uid, handle in (
            (AUTHOR, "feed_author"),
            (BLOCKED, "feed_blocked"),
            (REVERSE, "feed_reverse"),
            (VIEWER, "feed_viewer"),
        ):
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) "
                "VALUES (?, ?, ?, ?, 'hash', 'salt')",
                (uid, "%s@example.test" % handle, handle, handle.upper()),
            )
        conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
            ("s_feed_cursor", VIEWER, TOKEN, (datetime.now() + timedelta(days=1)).isoformat()),
        )
        conn.execute(
            "INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
            ("b_feed_cursor_1", VIEWER, BLOCKED),
        )
        conn.execute(
            "INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
            ("b_feed_cursor_2", REVERSE, VIEWER),
        )

        # 100 ordinary campus moments, oldest first.
        for i in range(100):
            pid = "p_feed_n%03d" % i
            _add_post(conn, pid, AUTHOR, "campus", _t(i))
            VISIBLE_ALL.append((_t(i), pid))
            VISIBLE_CAMPUS.append((_t(i), pid))

        # Five moments share one timestamp, split naturally by id ordering.
        for suffix in "abcde":
            pid = "p_feed_tie_" + suffix
            _add_post(conn, pid, AUTHOR, "campus", _t(200))
            VISIBLE_ALL.append((_t(200), pid))
            VISIBLE_CAMPUS.append((_t(200), pid))

        # Global-circle moments remain part of the all/circle walk.
        for i in range(5):
            pid = "p_feed_g%02d" % i
            _add_post(conn, pid, AUTHOR, "global", _t(300 + i))
            VISIBLE_ALL.append((_t(300 + i), pid))
            VISIBLE_GLOBAL.append((_t(300 + i), pid))

        # Newer blocked/reverse-blocked authors sit above every visible row.
        # They must be filtered in SQL, before LIMIT+1, or pages become short.
        for i in range(5):
            _add_post(conn, "p_feed_blocked_%02d" % i, BLOCKED, "campus", _t(400 + i))
            _add_post(conn, "p_feed_reverse_%02d" % i, REVERSE, "campus", _t(500 + i))

        # Newer content that the existing isolation rules must exclude.
        isolated = [
            ("p_feed_comm", dict(primary_community_id="c_feed_isolation")),
            ("p_feed_context", dict(context_community_id="c_feed_isolation")),
            ("p_feed_drop", dict(drop_id="drop_feed_isolation")),
            ("p_feed_circle_community", dict(circle="community")),
            ("p_feed_hidden", dict(moderation_status="hidden")),
            ("p_feed_removed", dict(moderation_status="removed")),
            ("p_feed_suspended", dict(moderation_status="suspended")),
            ("p_feed_private", dict(is_private=1)),
        ]
        for i, (pid, kwargs) in enumerate(isolated):
            circle = kwargs.pop("circle", "campus")
            _add_post(conn, pid, AUTHOR, circle, _t(600 + i), **kwargs)
            ISOLATED_IDS.append(pid)

        # Batched reaction data for the newest visible post.
        for j, emoji in enumerate(("🔥", "🔥")):
            conn.execute(
                "INSERT INTO reactions (id, post_id, user_id, emoji) VALUES (?, ?, ?, ?)",
                ("r_feed_g04_%d" % j, "p_feed_g04", VIEWER if j == 0 else AUTHOR, emoji),
            )

        conn.commit()
        conn.close()

        VISIBLE_ALL.sort(key=lambda row: (row[0], row[1]), reverse=True)
        VISIBLE_CAMPUS.sort(key=lambda row: (row[0], row[1]), reverse=True)
        VISIBLE_GLOBAL.sort(key=lambda row: (row[0], row[1]), reverse=True)

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

    # ---- helpers -----------------------------------------------------------

    def _get(self, path, auth=False):
        headers = {"Authorization": "Bearer %s" % TOKEN} if auth else {}
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path), headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            self.assertTrue(raw, "0-byte response for %s" % path)
            return resp.status, json.loads(raw.decode("utf-8"))

    def _walk(self, path, auth=False, max_pages=100):
        seen, pages, cursor = [], [], ""
        while True:
            url = path
            if cursor:
                separator = "&" if "?" in path else "?"
                url = path + separator + "cursor=" + urllib.parse.quote(cursor)
            _, body = self._get(url, auth=auth)
            pages.append(body)
            seen.extend(m["id"] for m in body["feed"])
            has_more = bool(body.get("has_more"))
            cursor = body.get("next_cursor") or ""
            self.assertLess(len(pages), max_pages, "pagination did not terminate")
            if not has_more:
                self.assertEqual(cursor, "", "has_more false but next_cursor non-empty")
                break
            self.assertTrue(cursor, "has_more true but next_cursor empty")
        return seen, pages

    # ---- tests -------------------------------------------------------------

    def test_01_composite_index_exists(self):
        conn = server.get_db()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_posts_feed_cursor'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

    def test_02_cursor_roundtrip_and_legacy(self):
        cursor = server.encode_feed_cursor("2026-01-01T12:00:00", "p_1", "all")
        decoded = server.decode_feed_cursor(cursor)
        self.assertEqual(decoded, {
            "created_at": "2026-01-01T12:00:00", "id": "p_1", "circle": "all"
        })
        self.assertEqual(
            server.decode_feed_cursor("2026-01-01T12:00:00"),
            {"created_at": "2026-01-01T12:00:00", "id": "", "circle": ""},
        )
        self.assertIsNone(server.decode_feed_cursor("not-a-cursor"))
        self.assertIsNone(server.decode_feed_cursor("a" * 600))
        bad_json = base64.urlsafe_b64encode(b'{"other":1}').decode("ascii").rstrip("=")
        self.assertIsNone(server.decode_feed_cursor(bad_json))

    def test_03_full_walk_no_dupes_or_gaps(self):
        expected = [pid for _, pid in VISIBLE_ALL]
        seen, pages = self._walk("/api/feed?circle=all&limit=20", auth=True)
        self.assertEqual(seen, expected)
        self.assertEqual(len(seen), len(set(seen)), "duplicate post id in walk")
        for page in pages[:-1]:
            self.assertTrue(page["has_more"])
            self.assertEqual(len(page["feed"]), 20, "intermediate page was shortened")
        self.assertFalse(pages[-1]["has_more"])
        self.assertEqual(pages[-1]["next_cursor"], "")

    def test_04_ties_survive_a_page_boundary(self):
        seen, _ = self._walk("/api/feed?circle=campus&limit=4", auth=True)
        ties = [pid for _, pid in VISIBLE_CAMPUS if pid.startswith("p_feed_tie_")]
        self.assertEqual(ties, ["p_feed_tie_e", "p_feed_tie_d", "p_feed_tie_c",
                                "p_feed_tie_b", "p_feed_tie_a"])
        self.assertEqual([pid for pid in seen if pid.startswith("p_feed_tie_")], ties)
        self.assertEqual(len(seen), len(set(seen)))

    def test_05_blocked_authors_filtered_without_short_pages(self):
        expected = [pid for _, pid in VISIBLE_ALL]
        seen, pages = self._walk("/api/feed?circle=all&limit=20", auth=True)
        self.assertEqual(seen, expected)
        for pid in seen:
            self.assertFalse(pid.startswith("p_feed_blocked_"))
            self.assertFalse(pid.startswith("p_feed_reverse_"))
        for page in pages[:-1]:
            self.assertEqual(len(page["feed"]), 20)

    def test_06_grouped_reactions_and_statement_count(self):
        _, first = self._get("/api/feed?circle=all&limit=20", auth=True)
        newest = first["feed"][0]
        self.assertEqual(newest["id"], "p_feed_g04")
        self.assertEqual(newest["realmojis"], {"🔥": 2})

        original = server.get_db
        counter = [0]

        class CountingCursor:
            def __init__(self, cur):
                self._cur = cur

            def execute(self, sql, params=None):
                if sql and not sql.strip().upper().startswith("PRAGMA"):
                    counter[0] += 1
                if params is None:
                    return self._cur.execute(sql)
                return self._cur.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._cur, name)

        class CountingConn:
            def __init__(self, conn):
                self._conn = conn

            def cursor(self):
                return CountingCursor(self._conn.cursor())

            def __getattr__(self, name):
                return getattr(self._conn, name)

        def counting_get_db():
            return CountingConn(original())

        server.get_db = counting_get_db
        try:
            self._get("/api/feed?circle=all&limit=5")
            small = counter[0]
            counter[0] = 0
            self._get("/api/feed?circle=all&limit=30")
            large = counter[0]
            counter[0] = 0
            self._get("/api/feed?circle=all&limit=5", auth=True)
            small_auth = counter[0]
            counter[0] = 0
            self._get("/api/feed?circle=all&limit=30", auth=True)
            large_auth = counter[0]
            counter[0] = 0
            self._get("/api/feed?circle=all&limit=30&cursor=" +
                      urllib.parse.quote("2000-01-01T00:00:00"), auth=True)
            empty = counter[0]
        finally:
            server.get_db = original

        self.assertEqual(small, large, "anonymous statement count grows with page size (N+1)")
        self.assertEqual(small_auth, large_auth, "authenticated statement count grows with page size (N+1)")
        self.assertLessEqual(large, 4, "anonymous feed request issued more than 4 SQL statements")
        self.assertLess(empty, large_auth, "empty page should skip the reaction query")

    def test_07_cursor_context_and_invalid_cursors_are_safe(self):
        _, first = self._get("/api/feed?circle=all&limit=2", auth=True)
        all_cursor = first["next_cursor"]
        self.assertTrue(all_cursor)
        decoded = server.decode_feed_cursor(all_cursor)
        self.assertEqual(decoded["circle"], "all")

        # A cursor from /api/feed?circle=all is inert for circle=global.
        _, global_first = self._get(
            "/api/feed?circle=global&limit=20&cursor=" + urllib.parse.quote(all_cursor)
        )
        self.assertEqual(
            [m["id"] for m in global_first["feed"]],
            [pid for _, pid in VISIBLE_GLOBAL],
        )

        bad_cursors = [
            "not-a-cursor",
            "a" * 600,
            base64.urlsafe_b64encode(b'{"other":1}').decode("ascii").rstrip("="),
            "2026-13-99T99:99:99",
        ]
        for bad in bad_cursors:
            status, body = self._get("/api/feed?circle=all&limit=20&cursor=" +
                                     urllib.parse.quote(bad), auth=True)
            self.assertEqual(status, 200)
            self.assertEqual(body["feed"][0]["id"], "p_feed_g04")

    def test_08_legacy_timestamp_cursor_is_accepted(self):
        legacy = _t(50)
        _, body = self._get(
            "/api/feed?circle=campus&limit=20&cursor=" + urllib.parse.quote(legacy),
            auth=True,
        )
        self.assertEqual(
            [m["id"] for m in body["feed"]],
            ["p_feed_n%03d" % i for i in range(49, 29, -1)],
        )
        self.assertTrue(body["has_more"])

    def test_09_empty_page_is_valid_and_skips_reaction_query(self):
        status, body = self._get(
            "/api/feed?circle=all&limit=20&cursor=" +
            urllib.parse.quote("2000-01-01T00:00:00")
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["feed"], [])
        self.assertFalse(body["has_more"])
        self.assertEqual(body["next_cursor"], "")

    def test_10_existing_feed_isolation_is_preserved(self):
        _, body = self._get("/api/feed?circle=all&limit=50", auth=True)
        ids = {m["id"] for m in body["feed"]}
        for pid in ISOLATED_IDS:
            self.assertNotIn(pid, ids, "isolation regression: %s leaked" % pid)
        self.assertNotIn("p_feed_private", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
