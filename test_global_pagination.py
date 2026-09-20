#!/usr/bin/env python3
"""
Focused regression test for Day-3 Task 2: /api/global hardening.

Covers:
  1. Bounding: 200+ seeded posts -> default request returns at most 50.
  2. Limit clamping: 1 / 50 / 999 / 0 / negative / non-numeric never exceed 50.
  3. Default envelope: no limit/cursor -> EXACTLY {success, window, region, moments}.
  4. Cursor walk: no duplicates, no gaps, has_more false only on the last page.
  5. Identical timestamps: ORDER BY created_at DESC, id DESC keeps every row.
  6. N+1 regression: constant SQL statement count as page size grows
     (one grouped reaction query, no per-post queries; PRAGMA connection
     setup statements are not counted).
  7. Block filtering both directions (blocked-by-me and blocked-me authors),
     applied INSIDE the SQL so pages stay full (block + pagination).
  8. Anonymous behavior unchanged (no block filtering applied).
  9. Moderation + private regressions (hidden/suspended/removed absent,
     active/NULL present, is_private=1 absent).
 10. Region parity for region-specific and all-region walks.
 11. Cursor safety: a cursor from one region is inert under another region.
 12. Empty page: valid JSON, no `IN ()`, no exception.
 13. Malformed/oversized cursor: first-page behavior, never 500/0-byte.

Runs against a throwaway SQLite database; data/kandid.db is never touched.
An in-test oracle recomputes the expected visible post sets independently.
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

TOKEN = "gp_test_token"
AUTHOR = "u_gp_a"       # plain visible author
BLOCKED = "u_gp_b"      # u_gp_w blocked this author
REVERSE = "u_gp_c"      # this author blocked u_gp_w
VIEWER = "u_gp_w"       # authenticated viewer who blocks BLOCKED, blocked by REVERSE

BASE = datetime(2026, 3, 1, 9, 0, 0)
REGIONS = ["asia", "europe", "americas"]
WALK_COUNT = 200

# Seeded posts: (id, author, region, is_private, moderation_status, created_at, circle)
SEED_POSTS = []


def _t(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def _seed_definitions():
    posts = []
    for i in range(WALK_COUNT):
        posts.append(("p_gp_walk_%03d" % i, AUTHOR, REGIONS[i % 3], 0, "active", _t(i)))
    posts += [
        ("p_gp_hidden", AUTHOR, "europe", 0, "hidden", _t(500)),
        ("p_gp_suspended", AUTHOR, "europe", 0, "suspended", _t(501)),
        ("p_gp_removed", AUTHOR, "asia", 1, "removed", _t(502)),   # mirrors real remove action
        ("p_gp_null", AUTHOR, "americas", 0, None, _t(503)),
        ("p_gp_active", AUTHOR, "europe", 0, "active", _t(504)),
        ("p_gp_private", AUTHOR, "asia", 1, "active", _t(505)),
    ]
    for suffix in "abcde":
        posts.append(("p_gp_tie_" + suffix, AUTHOR, "americas", 0, "active", _t(1000)))
    for n in (1, 2, 3):
        posts.append(("p_gp_blk_%d" % n, BLOCKED, "europe", 0, "active", _t(1000 + n)))
        posts.append(("p_gp_rev_%d" % n, REVERSE, "americas", 0, "active", _t(1003 + n)))
    return posts


SEED_POSTS = _seed_definitions()

BLOCKED_AUTHORS = {BLOCKED, REVERSE}  # invisible to VIEWER, both directions


def _expected_visible(region=None, authed=False):
    """Independent oracle mirroring the endpoint's visibility rules."""
    rows = []
    for pid, author, region_v, is_private, mod, created_at in SEED_POSTS:
        if is_private:
            continue
        if mod not in (None, "active"):
            continue
        if region and region_v != region:
            continue
        if authed and author in BLOCKED_AUTHORS:
            continue
        rows.append((created_at, pid))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [pid for _, pid in rows]


class _CountingCursor:
    def __init__(self, cur, counter):
        self._cur = cur
        self._counter = counter

    def execute(self, sql, params=None):
        if sql and not sql.strip().upper().startswith("PRAGMA"):
            self._counter[0] += 1
        return self._cur.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _CountingConn:
    def __init__(self, conn, counter):
        self._conn = conn
        self._counter = counter

    def cursor(self):
        return _CountingCursor(self._conn.cursor(), self._counter)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class GlobalPaginationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_d3_2_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_d3_2.db")
        server.init_db()

        conn = server.get_db()
        for uid, handle in ((AUTHOR, "gp_a"), (BLOCKED, "gp_b"), (REVERSE, "gp_c"), (VIEWER, "gp_w")):
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, "%s@example.test" % handle, handle, handle.upper(), "hash", "salt"),
            )
        conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
            ("s_gp_test", VIEWER, TOKEN, (datetime.now() + timedelta(days=1)).isoformat()),
        )
        conn.execute("INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
                     ("b_gp_1", VIEWER, BLOCKED))
        conn.execute("INSERT INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
                     ("b_gp_2", REVERSE, VIEWER))
        for pid, author, region, is_private, mod, created_at in SEED_POSTS:
            conn.execute(
                """INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img,
                                       caption, circle, region, is_private, moderation_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, author, author.upper(), "@" + handle_of(author),
                    "img_%s.jpg" % pid, "pip_%s.jpg" % pid,
                    "caption %s" % pid, "global", region, is_private, mod, created_at,
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
        """Follow next_cursor until has_more is false; return all moment ids."""
        seen, pages, has_more = [], [], True
        url = path
        while has_more:
            _, body = self._get(url, auth=auth)
            pages.append(body)
            seen.extend(m["id"] for m in body["moments"])
            has_more = bool(body.get("has_more"))
            cursor = body.get("next_cursor") or ""
            self.assertLess(len(pages), max_pages, "pagination did not terminate")
            if has_more:
                self.assertTrue(cursor, "has_more true but next_cursor empty")
                sep = "&" if "?" in path else "?"
                url = "%s%scursor=%s" % (path, sep, urllib.parse.quote(cursor))
            else:
                self.assertEqual(cursor, "", "has_more false but next_cursor non-empty")
        return seen, pages

    # 1. BOUNDING ------------------------------------------------------------

    def test_01_default_bounded_to_50(self):
        _, body = self._get("/api/global")
        self.assertLessEqual(len(body["moments"]), 50)

    # 2. LIMIT CLAMPING --------------------------------------------------------

    def test_02_limit_clamping_never_exceeds_50(self):
        for raw in ("1", "50", "999", "0", "-5", "abc"):
            _, body = self._get("/api/global?limit=" + urllib.parse.quote(raw))
            self.assertGreaterEqual(len(body["moments"]), 1, "limit=%r returned empty page" % raw)
            self.assertLessEqual(len(body["moments"]), 50, "limit=%r bypassed the cap" % raw)
            self.assertIn("has_more", body)  # explicit limit -> paginated envelope
        self.assertEqual(len(self._get("/api/global?limit=1")[1]["moments"]), 1)
        self.assertEqual(len(self._get("/api/global?limit=50")[1]["moments"]), 50)
        self.assertEqual(len(self._get("/api/global?limit=999")[1]["moments"]), 50)

    # 3. DEFAULT ENVELOPE -------------------------------------------------------

    def test_03_default_envelope_exact_keys(self):
        _, body = self._get("/api/global")
        self.assertEqual(set(body.keys()), {"success", "window", "region", "moments"})
        self.assertEqual(body["region"], "all")
        self.assertEqual(body["window"]["title"], "WORLD WINDOW")
        _, body = self._get("/api/global?region=asia")
        self.assertEqual(set(body.keys()), {"success", "window", "region", "moments"})
        self.assertEqual(body["region"], "asia")

    # 4. CURSOR WALK -------------------------------------------------------------

    def test_04_anonymous_cursor_walk_no_dupes_or_gaps(self):
        expected = _expected_visible()
        self.assertGreater(len(expected), 200)
        seen, pages = self._walk("/api/global?limit=50")
        self.assertEqual(seen, expected)
        for page in pages[:-1]:
            self.assertTrue(page["has_more"])
        self.assertFalse(pages[-1]["has_more"])

    def test_04b_authenticated_cursor_walk_filters_blocks(self):
        expected = _expected_visible(authed=True)
        self.assertNotIn("p_gp_blk_1", expected)
        self.assertNotIn("p_gp_rev_1", expected)
        seen, pages = self._walk("/api/global?limit=50", auth=True)
        self.assertEqual(seen, expected)
        self.assertFalse(pages[-1]["has_more"])

    # 5. IDENTICAL TIMESTAMPS ------------------------------------------------------

    def test_05_identical_timestamps_not_lost(self):
        ties = ["p_gp_tie_%s" % s for s in "edcba"]  # id DESC within same timestamp
        _, page1 = self._get("/api/global?limit=7")
        ids1 = [m["id"] for m in page1["moments"]]
        # 3 rev + 3 blk posts are newer; the 7th item is the first tie.
        self.assertEqual(ids1[-1], ties[0])
        seen, _ = self._walk("/api/global?limit=7")
        self.assertIn(ties[0], seen)
        self.assertEqual(seen.count(ties[0]), 1)
        idx = [seen.index(t) for t in ties]
        self.assertEqual(idx, sorted(idx), "tie ordering violated")
        # tie group split across pages must not lose rows: full walk covers it,
        # assert all five ties present exactly once in strict id-DESC order.
        self.assertEqual([t for t in seen if t.startswith("p_gp_tie_")], ties)

    # 6. N+1 REGRESSION --------------------------------------------------------------

    def test_06_statement_count_constant_across_page_sizes(self):
        counter = [0]
        original = server.get_db

        def counting_get_db():
            return _CountingConn(original(), counter)

        server.get_db = counting_get_db
        try:
            self._get("/api/global?limit=10")
            small = counter[0]
            counter[0] = 0
            self._get("/api/global?limit=50")
            large = counter[0]
            counter[0] = 0
            self._get("/api/global")
            default_anon = counter[0]
            counter[0] = 0
            self._get("/api/global?limit=10", auth=True)
            small_auth = counter[0]
            counter[0] = 0
            self._get("/api/global?limit=50", auth=True)
            large_auth = counter[0]
        finally:
            server.get_db = original

        self.assertEqual(small, large, "statement count grew with page size (N+1)")
        self.assertEqual(small_auth, large_auth, "authenticated statement count grew (N+1)")
        self.assertLessEqual(default_anon, 4, "anonymous request exceeded 4 SQL statements")
        self.assertLess(large, 10, "per-post reaction queries appear to remain (N+1)")

    # 7/8. BLOCK FILTERING ------------------------------------------------------------

    def test_07_blocked_authors_excluded_both_directions(self):
        _, body = self._get("/api/global?limit=50", auth=True)
        ids = {m["id"] for m in body["moments"]}
        for n in (1, 2, 3):
            self.assertNotIn("p_gp_blk_%d" % n, ids, "blocked author leaked")
            self.assertNotIn("p_gp_rev_%d" % n, ids, "reverse-blocked author leaked")
        self.assertIn("p_gp_walk_199", ids)

    def test_08_block_filtering_keeps_pages_full(self):
        # 6 blocked posts sit inside the newest window; the page must still
        # fill to the requested limit from visible posts, and has_more must
        # stay correct (207 visible > 50).
        _, body = self._get("/api/global?limit=50", auth=True)
        self.assertEqual(len(body["moments"]), 50)
        self.assertTrue(body["has_more"])
        expected_first = _expected_visible(authed=True)[:50]
        self.assertEqual([m["id"] for m in body["moments"]], expected_first)

    def test_09_anonymous_behavior_unchanged(self):
        _, body = self._get("/api/global?limit=50")
        ids = {m["id"] for m in body["moments"]}
        # Anonymous sees BLOCKED and REVERSE posts (no block filtering).
        for n in (1, 2, 3):
            self.assertIn("p_gp_blk_%d" % n, ids)
            self.assertIn("p_gp_rev_%d" % n, ids)
        self.assertEqual(len(body["moments"]), 50)

    # 10/11. MODERATION + PRIVATE REGRESSIONS --------------------------------------------

    def test_10_moderation_states_regression(self):
        seen, _ = self._walk("/api/global?limit=50")
        self.assertNotIn("p_gp_hidden", seen)
        self.assertNotIn("p_gp_suspended", seen)
        self.assertNotIn("p_gp_removed", seen)
        self.assertIn("p_gp_active", seen)
        self.assertIn("p_gp_null", seen)

    def test_11_private_posts_excluded(self):
        seen, _ = self._walk("/api/global?limit=50")
        self.assertNotIn("p_gp_private", seen)

    # 12. REGION PARITY -------------------------------------------------------------------

    def test_12_region_walks_match_oracle(self):
        for region in ("asia", "europe", "americas"):
            seen, pages = self._walk("/api/global?region=%s&limit=50" % region)
            self.assertEqual(seen, _expected_visible(region=region), "region=%s walk mismatch" % region)
            self.assertFalse(pages[-1]["has_more"])
            for page in pages:
                self.assertLessEqual(len(page["moments"]), 50)
        seen, pages = self._walk("/api/global?limit=50", auth=True)
        self.assertEqual(seen, _expected_visible(authed=True))
        self.assertFalse(pages[-1]["has_more"])

    # 13. CURSOR SAFETY ---------------------------------------------------------------------

    def test_13_cursor_scoped_to_region(self):
        _, asia = self._get("/api/global?region=asia&limit=10")
        self.assertTrue(asia["next_cursor"])
        _, europe_base = self._get("/api/global?region=europe&limit=10")
        _, europe_crossed = self._get(
            "/api/global?region=europe&limit=10&cursor=" + urllib.parse.quote(asia["next_cursor"])
        )
        # Cross-region cursor must be inert: identical to europe's first page.
        self.assertEqual(
            [m["id"] for m in europe_crossed["moments"]],
            [m["id"] for m in europe_base["moments"]],
        )
        self.assertTrue(europe_crossed["has_more"])

    # 14. EMPTY PAGE — handled by EmptyDBTest below (needs a post-free DB).

    # 15. MALFORMED CURSOR -----------------------------------------------------------------

    def test_15_malformed_and_oversized_cursor_safe(self):
        _, base = self._get("/api/global?limit=10")
        base_ids = [m["id"] for m in base["moments"]]
        for garbage in ("@@@@garbage!!", "not-a-cursor", "A" * 5000, "%00", ".."):
            status, body = self._get("/api/global?limit=10&cursor=" + urllib.parse.quote(garbage))
            self.assertEqual(status, 200)
            self.assertEqual([m["id"] for m in body["moments"]], base_ids,
                             "malformed cursor %r did not behave as first page" % garbage)
            self.assertTrue(body["has_more"])


class EmptyDBTest(unittest.TestCase):
    """Empty database: /api/global must return valid JSON with an empty page,
    never raise, never emit an invalid `IN ()` query or a 0-byte response."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_d3_2_empty_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "empty.db")
        server.init_db()  # fresh DB: no posts seeded
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

    def _get(self, path):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path))
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            self.assertTrue(raw, "0-byte response for %s" % path)
            return resp.status, json.loads(raw.decode("utf-8"))

    def test_14_empty_page_safe(self):
        status, body = self._get("/api/global?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(body["moments"], [])
        self.assertFalse(body["has_more"])
        self.assertEqual(body["next_cursor"], "")
        self.assertEqual(
            set(body.keys()),
            {"success", "window", "region", "moments", "next_cursor", "has_more"},
        )

    def test_14b_empty_db_default_envelope(self):
        status, body = self._get("/api/global")
        self.assertEqual(status, 200)
        self.assertEqual(body["moments"], [])
        self.assertEqual(set(body.keys()), {"success", "window", "region", "moments"})


def handle_of(uid):
    return {"u_gp_a": "gp_a", "u_gp_b": "gp_b", "u_gp_c": "gp_c", "u_gp_w": "gp_w"}[uid]


if __name__ == "__main__":
    unittest.main(verbosity=2)
