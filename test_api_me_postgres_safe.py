#!/usr/bin/env python3
"""
Focused regression test for D4-01: /api/me PostgreSQL compatibility.

BEFORE the fix, the "captured today" lookup inside /api/me (server.py ~6266)
was:

    WHERE user_id = ? AND (DATE(created_at) = DATE('now') OR created_at LIKE ?)

Problems:
  * `DATE('now')` is SQLite syntax. The project's SQLite->PostgreSQL shim
    (PostgresCursorWrapper.execute, server.py ~1944) translates
    `datetime('now')` variants only — `DATE(...)` function-call syntax has no
    translation rule and no scalar DATE() equivalent, so on Neon the query
    raised a syntax error and /api/me 500'd for every authenticated user.
  * The second arm `created_at LIKE 'YYYY-MM-DD%'` (built from today_prefix)
    already selects exactly the same rows, making the DATE('now') branch
    redundant.

The fix removes only the redundant, incompatible branch:

    WHERE user_id = ? AND created_at LIKE ?

today_prefix and the query bindings are unchanged.

Three layers of proof (no live DB server required):
  A. STATIC       - the /api/me "captured today" query no longer contains
                    DATE('now'); today_prefix and bindings are unchanged;
                    the rest of server.py is byte-identical to baseline
                    f884968 apart from that one line.
  B. WRAPPER      - the REAL PostgresCursorWrapper translates the fixed SQL
                    cleanly (no translation needed, no leftover DATE tokens,
                    placeholders converted), while the baseline SQL would
                    have shipped an untranslatable DATE('now') to PostgreSQL.
  C. BEHAVIOURAL  - the REAL /api/me handler is exercised over HTTP against
                    an isolated SQLite fixture and returns 200 with the
                    today_moment key, with today's capture selected by the
                    LIKE branch.

Runs read-only: DB_FILE/DATABASE_URL are redirected to a throwaway SQLite
copy, so data/kandid.db is never touched.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

SERVER_PY = os.path.join(PROJECT_DIR, "server.py")
BASELINE_COMMIT = "f8849688fb86f9554d6dc29fd55bf8231883c5ca"

import server  # noqa: E402


def _git_show_baseline(path="server.py"):
    out = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:{path}"],
        cwd=PROJECT_DIR, capture_output=True, check=True
    )
    return out.stdout.decode("utf-8")


def _captured_today_sql(src):
    """Return the SQL block of the /api/me 'captured today' query."""
    m = re.search(r"SELECT \* FROM posts\s*\n\s*WHERE user_id = \? AND[^\"]*ORDER BY created_at DESC LIMIT 1", src)
    return m.group(0) if m else None


def _api_me_region(src, start=6240, end=6350):
    """Extract the /api/me handler region as a localized blast-radius window."""
    lines = src.splitlines(keepends=True)
    a = max(0, start - 1)
    b = min(len(lines), end)
    return "".join(lines[a:b])


class TestApiMeStatic(unittest.TestCase):
    """Layer A: static source assertions."""

    @classmethod
    def setUpClass(cls):
        with open(SERVER_PY, "r", encoding="utf-8") as fh:
            cls.src = fh.read()
        cls.baseline = _git_show_baseline()

    def test_01_no_date_now_in_api_me_query(self):
        sql = _captured_today_sql(self.src)
        self.assertIsNotNone(sql, "could not locate /api/me 'captured today' SQL")
        self.assertNotIn("DATE('now')", sql)
        self.assertNotIn("DATE(created_at)", sql)

    def test_02_no_date_now_anywhere_in_server_py(self):
        self.assertNotIn("DATE('now')", self.src)

    def test_03_today_prefix_unchanged(self):
        m = re.search(r"today_prefix = (.+)", self.src)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), "datetime.utcnow().strftime('%Y-%m-%d')")

    def test_04_fixed_where_clause_is_exact(self):
        sql = _captured_today_sql(self.src)
        self.assertIn("WHERE user_id = ? AND created_at LIKE ?", sql)

    def test_05_bindings_unchanged_two_params(self):
        sql_block = re.search(
            r"SELECT \* FROM posts\s*\n\s*WHERE user_id = \? AND created_at LIKE \?\s*\n\s*ORDER BY created_at DESC LIMIT 1\s*\n\s*\"\"\", \(user\[\"id\"\], f\"\{today_prefix\}%\"\)\)",
            self.src,
        )
        self.assertIsNotNone(sql_block, "bindings tuple changed")

    def test_06_blast_radius_single_line(self):
        """Only that one WHERE line differs from baseline f884968."""
        now_lines = self.src.splitlines()
        base_lines = self.baseline.splitlines()
        self.assertEqual(len(now_lines), len(base_lines))
        diffs = [
            (i, a, b) for i, (a, b) in enumerate(zip(base_lines, now_lines)) if a != b
        ]
        self.assertEqual(len(diffs), 1, f"expected exactly 1 changed line, got {len(diffs)}")
        i, base_line, now_line = diffs[0]
        self.assertIn("DATE(created_at) = DATE('now') OR created_at LIKE ?", base_line)
        self.assertIn("created_at LIKE ?", now_line)


class _StubCursor:
    """Records the last executed SQL and returns a canned today_row."""

    def __init__(self, today_row=None):
        self.last_sql = None
        self.last_params = None
        self.today_row = today_row

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return self

    def fetchone(self):
        if self.today_row is None:
            return None
        if self.today_row.get("__is_today_row__"):
            return dict(self.today_row, **{k: v for k, v in self.today_row.items() if k != "__is_today_row__"})
        return self.today_row

    def fetchall(self):
        return []


class _StubConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class TestApiMeWrapper(unittest.TestCase):
    """Layer B: the real PostgresCursorWrapper must handle the fixed SQL."""

    @classmethod
    def setUpClass(cls):
        cls.wrapper_cls = getattr(server, "PostgresCursorWrapper", None)

    def test_01_wrapper_class_exists(self):
        self.assertIsNotNone(self.wrapper_cls, "PostgresCursorWrapper not found in server.py")

    def test_02_fixed_sql_translates_without_date_tokens(self):
        wrapper = self.wrapper_cls(_StubCursor())
        fixed = (
            "\n                SELECT * FROM posts \n"
            "                WHERE user_id = ? AND created_at LIKE ?\n"
            "                ORDER BY created_at DESC LIMIT 1\n            "
        )
        wrapper.execute(fixed, (42, "2026-09-21%"))
        out = wrapper.raw_cursor.last_sql
        self.assertNotIn("DATE(", out.upper())
        self.assertNotIn("NOW", out.upper())
        self.assertIn("%s", out)
        self.assertNotIn("?", out)
        self.assertIn("LIKE %s", out)

    def test_03_baseline_sql_would_have_shipped_untranslatable_date_now(self):
        """Prove the OLD SQL really was the problem for the shim."""
        wrapper = self.wrapper_cls(_StubCursor())
        baseline_sql = (
            "SELECT * FROM posts WHERE user_id = ? AND "
            "(DATE(created_at) = DATE('now') OR created_at LIKE ?)"
        )
        wrapper.execute(baseline_sql, (42, "2026-09-21%"))
        out = wrapper.raw_cursor.last_sql
        self.assertIn("DATE(", out.upper())  # untranslatable DATE tokens remain
        self.assertIn("NOW", out.upper())    # DATE('now') passed through

    def test_04_datetime_now_translation_still_intact(self):
        """The shim's datetime('now') rules are untouched by this task."""
        wrapper = self.wrapper_cls(_StubCursor())
        wrapper.execute("SELECT * FROM t WHERE created_at >= datetime('now', '-7 days')", ())
        out = wrapper.raw_cursor.last_sql.upper()
        self.assertIn("CURRENT_TIMESTAMP", out)
        self.assertIn("INTERVAL '7 DAYS'", out)


class TestApiMeBehavioural(unittest.TestCase):
    """Layer C: real /api/me handler over HTTP against an isolated SQLite fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="kandid_d4_01_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        # Redirect ALL DB access (including in-request get_db()) to a
        # disposable SQLite database for the whole test class.
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls.tmpdir, "test.db")
        server.init_db()
        db_file = server.DB_FILE

        cls._conn = server.sqlite3.connect(db_file)
        cls._conn.row_factory = server.sqlite3.Row
        cls.now = datetime.utcnow()

        # user (me) + today capture
        cls._conn.execute(
            "INSERT INTO users (id, handle, email, password_hash, salt, name, campus, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("u_me", "me_user", "me@example.com", "x", "s", "Me User", "campus-a",
             (cls.now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")),
        )
        cls._conn.execute(
            """INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img,
                                   caption, circle, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("p_today", "u_me", "Me User", "me_user", "img_today.jpg", "pip_today.jpg",
             "today capture", "global", cls.now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        cls._conn.execute(
            """INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img,
                                   caption, circle, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("p_old", "u_me", "Me User", "me_user", "img_old.jpg", "pip_old.jpg",
             "old capture", "global",
             (cls.now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")),
        )
        # session for auth
        cls._conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?,?,?,?)",
            ("s_me", "u_me", "tok_me",
             (cls.now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
        )
        cls._conn.commit()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._conn.close()
        except Exception:
            pass
        server.DB_FILE = cls._original_db_file
        server.DATABASE_URL = cls._original_database_url
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _start(self):
        class Handler(server.KandidHandler):
            def log_message(self, *a, **k):
                pass

        # server.DB_FILE/DATABASE_URL already point at the fixture for the
        # whole class; just boot the real handler in-process.
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv

    def _get(self, path, token=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self._srv.server_address[1]}{path}")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_10_api_me_200_with_today_moment(self):
        self._srv = self._start()
        status, body = self._get("/api/me", token="tok_me")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertTrue(body["user"].get("has_captured_today"))
        self.assertIn("today_moment", body["user"])
        self.assertEqual(body["user"]["today_moment"]["id"], "p_today")

    def test_11_api_me_today_moment_is_todays_not_yesterdays(self):
        self._srv = self._start()
        status, body = self._get("/api/me", token="tok_me")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["today_moment"]["id"], "p_today")
        self.assertNotEqual(body["user"]["today_moment"]["id"], "p_old")

    def test_12_api_me_counts_and_envelope_keys(self):
        self._srv = self._start()
        status, body = self._get("/api/me", token="tok_me")
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["momentCount"], 2)
        self.assertEqual(body["user"]["memoryCount"], 2)
        for key in ("success", "user"):
            self.assertIn(key, body, f"missing top-level key {key}")
        for key in ("id", "handle", "momentCount", "memoryCount", "today_moment", "has_captured_today", "pending_requests_count"):
            self.assertIn(key, body["user"], f"missing user key {key}")

    def test_13_unauthenticated_401(self):
        self._srv = self._start()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self._srv.server_address[1]}/api/me", timeout=10)
            self.fail("expected HTTP 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
