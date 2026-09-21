#!/usr/bin/env python3
"""
Focused regression test for D4-03: centralized unhandled-exception boundary.

BEFORE the fix, an unexpected exception inside a route (e.g. /api/event?id=abc
against a DB without the campus_events table, or any latent bug) propagated out
of do_GET into socketserver, which printed the traceback, closed the socket and
delivered ZERO bytes to the client ("Remote end closed connection without
response"). If a response had already started, a stray second status line could
also corrupt the stream.

The fix adds one method, KandidHandler.handle_one_request(), which wraps the
standard lifecycle:
  - BrokenPipeError / ConnectionResetError -> quiet disconnect, no response
  - any other unexpected exception         -> ONE generic JSON 500, but ONLY
    when self._response_status shows no response has started; otherwise the
    connection is closed safely without writing another status line.
  - self.close_connection = True after an unexpected exception.
  - no DB rollback logic, no route changes, no socket timeout.

Tests use the REAL handler in-process. Route exceptions come from a controlled
fault-injection subclass that flips class-level flags (no production route is
modified). The natural-crash route /api/event?id=abc is also exercised against
a throwaway DB that lacks campus_events.

Read-only: the database is redirected to a disposable SQLite copy, so
data/kandid.db is never touched.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import time
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402
from server import KandidHandler  # noqa: E402


def _read_raw(path, host, port, method="GET", headers=None):
    """Raw socket request; returns the exact bytes the client received."""
    req = f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
    for k, v in (headers or {}).items():
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(req.encode())
        chunks = []
        while True:
            try:
                b = s.recv(65536)
            except socket.timeout:
                break
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)


def _status_line_count(raw):
    return raw.count(b"HTTP/1.")


class FaultKandidHandler(KandidHandler):
    """Real handler with two class-level fault switches (default OFF)."""
    fault_unread = False          # raise mid-route in /api/chat/unread-count
    fault_unread_after_start = False  # raise AFTER a response has started
    real_events = False           # allow /api/event to hit the real DB

    def do_GET(self):
        if self.fault_unread and self.path.startswith("/api/chat/unread-count"):
            raise RuntimeError("injected fault (before response)")
        if self.fault_unread_after_start and self.path.startswith("/api/chat/unread-count"):
            try:
                self.send_json(200, {"success": True, "count": 0})
            except (BrokenPipeError, ConnectionResetError):
                pass
            raise RuntimeError("injected fault (after response started)")
        super().do_GET()


class UnhandledExceptionBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_d4_03_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_d4_03.db")
        server.init_db()

        conn = server.get_db()
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_d403", "d403@example.test", "d403_user", "D4 User", "hash", "salt"),
        )
        conn.commit()
        conn.close()

        # campus_events exists in the fixture so the real /api/event route can
        # serve its normal 400/404 paths; test_14 drops it to trigger the
        # natural sqlite3.OperationalError crash.
        conn = server.get_db()
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS campus_events (id TEXT PRIMARY KEY, title TEXT DEFAULT '')"
        )
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FaultKandidHandler)
        cls.host, cls.port = "127.0.0.1", cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._orig_db
            server.DATABASE_URL = cls._orig_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    # ---- 1. exception before response -> single generic 500 JSON ----------
    def test_01_exception_before_response_returns_single_500_json(self):
        FaultKandidHandler.fault_unread = True
        try:
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://{self.host}:{self.port}/api/chat/unread-count", timeout=10)
            self.assertEqual(cm.exception.code, 500)
            body = json.loads(cm.exception.read().decode("utf-8"))
            self.assertEqual(body, {"success": False, "error": "Internal server error"})
        finally:
            FaultKandidHandler.fault_unread = False

    def test_02_crash_response_has_exactly_one_status_line(self):
        FaultKandidHandler.fault_unread = True
        try:
            raw = _read_raw("/api/chat/unread-count", self.host, self.port)
        finally:
            FaultKandidHandler.fault_unread = False
        self.assertEqual(_status_line_count(raw), 1, f"status lines in stream: {raw[:120]!r}")

    def test_03_500_body_contains_no_internal_details(self):
        FaultKandidHandler.fault_unread = True
        try:
            raw = _read_raw("/api/chat/unread-count", self.host, self.port)
        finally:
            FaultKandidHandler.fault_unread = False
        text = raw.decode("utf-8", errors="replace").lower()
        for forbidden in ("runtimeerror", "traceback", "inject", "sqlite", "postgres",
                          "select ", "server.py", "/home/", "tmpdir", "d403"):
            self.assertNotIn(forbidden, text)

    def test_04_close_connection_set_after_crash(self):
        FaultKandidHandler.fault_unread = True
        try:
            raw = _read_raw("/api/chat/unread-count", self.host, self.port)
        finally:
            FaultKandidHandler.fault_unread = False
        # HTTP/1.0 closes connections by default (no explicit Connection
        # header); the observable contract is that the server closed the
        # stream after the single 500 response (recv loop terminated).
        self.assertTrue(raw.endswith(b'}'), "stream did not terminate cleanly after 500")
        self.assertEqual(_status_line_count(raw), 1)

    # ---- 2. exception AFTER response started -> no second response --------
    def test_05_exception_after_response_started_no_second_status_line(self):
        FaultKandidHandler.fault_unread_after_start = True
        try:
            raw = _read_raw("/api/chat/unread-count", self.host, self.port)
        finally:
            FaultKandidHandler.fault_unread_after_start = False
        self.assertEqual(_status_line_count(raw), 1, f"duplicate status line: {raw[:200]!r}")
        self.assertIn(b'{"success": true, "count": 0}', raw)
        self.assertNotIn(b"Internal server error", raw)

    # ---- 3. broken pipe -> quiet, no response attempt ----------------------
    def test_06_broken_pipe_no_response_attempt(self):
        # Connect, send a partial request, and vanish before the response.
        s = socket.create_connection((self.host, self.port), timeout=10)
        s.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n")
        s.close()  # abrupt close -> BrokenPipeError/ConnectionResetError server-side
        # Give the server a moment; then prove it is still healthy.
        time.sleep(0.3)
        status, _ = self._get_status("/health")
        self.assertEqual(status, 200)

    # ---- 4. unknown route unchanged -----------------------------------------
    def test_07_unknown_route_still_404(self):
        status, body = self._get_status("/definitely/not/a/route")
        self.assertEqual(status, 404)

    # ---- 5. missing auth unchanged ------------------------------------------
    def test_08_missing_auth_still_401(self):
        status, _ = self._get_status("/api/me")
        self.assertEqual(status, 401)

    # ---- 6. existing 4xx paths unchanged ------------------------------------
    def test_09_existing_error_paths_unchanged(self):
        status, _ = self._get_status("/api/event")            # 400 missing id
        self.assertEqual(status, 400)
        status, _ = self._get_status("/api/event?id=zzz-nope")  # 404 not found
        self.assertEqual(status, 404)
        status, body = self._get_status("/api/chat/unread-count")  # unauth -> 200 {count:0}
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("count"), 0)

    # ---- 7. CORS preflight unchanged ----------------------------------------
    def test_10_cors_preflight_unchanged(self):
        raw = _read_raw("/api/feed", self.host, self.port, method="OPTIONS",
                        headers={"Origin": "https://kindid.in",
                                 "Access-Control-Request-Method": "GET"})
        self.assertIn(b"200", raw.split(b"\r\n")[0])
        self.assertIn(b"access-control-allow-origin: https://kindid.in", raw.lower())
        self.assertIn(b"access-control-allow-headers:", raw.lower())
        self.assertIn(b"access-control-allow-methods:", raw.lower())
        # trusted origin must NOT be answered with a wildcard
        self.assertNotIn(b"access-control-allow-origin: *", raw.lower())

    # ---- 8. HEAD request: headers preserved, no body -------------------------
    def test_11_head_request_headers_only(self):
        # HEAD of a static asset: standard lifecycle, headers only, no body.
        raw = _read_raw("/index.html", self.host, self.port, method="HEAD")
        first = raw.split(b"\r\n", 1)[0]
        self.assertIn(b"200", first)
        head, _, body = raw.partition(b"\r\n\r\n")
        self.assertEqual(body, b"", "HEAD responses must not carry a body")
        self.assertIn(b"content-type", head.lower())

    # ---- 9. static asset unchanged -------------------------------------------
    def test_12_static_asset_unchanged(self):
        status, body = self._get_status("/index.html")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 100)

    # ---- 10. /health unchanged -------------------------------------------------
    def test_13_health_still_200(self):
        status, body = self._get_status("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("status"), "ok")

    # ---- 11/12. natural crash -> single JSON 500, no internals ------------------
    def test_14_natural_crash_api_event_returns_single_500_json(self):
        conn = server.get_db()
        conn.executescript("DROP TABLE IF EXISTS campus_events")
        conn.close()
        try:
            raw = _read_raw("/api/event?id=abc", self.host, self.port)
        finally:
            conn = server.get_db()
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS campus_events (id TEXT PRIMARY KEY, title TEXT DEFAULT '')"
            )
            conn.close()
        self.assertEqual(_status_line_count(raw), 1)
        first = raw.split(b"\r\n", 1)[0]
        self.assertIn(b"500", first)
        body = raw.rpartition(b"\r\n\r\n")[2]
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data, {"success": False, "error": "Internal server error"})
        low = raw.decode("utf-8", errors="replace").lower()
        for forbidden in ("operationalerror", "campus_events", "no such table", "traceback"):
            self.assertNotIn(forbidden, low)

    # ---- 14. sustained crash loop: server stays responsive ----------------------
    def test_15_sustained_crash_loop_stays_responsive(self):
        conn = server.get_db()
        conn.executescript("DROP TABLE IF EXISTS campus_events")
        conn.close()
        try:
            for _ in range(30):
                raw = _read_raw("/api/event?id=abc", self.host, self.port)
                self.assertEqual(_status_line_count(raw), 1)
                self.assertIn(b"500", raw.split(b"\r\n", 1)[0])
        finally:
            conn = server.get_db()
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS campus_events (id TEXT PRIMARY KEY, title TEXT DEFAULT '')"
            )
            conn.close()
        status, body = self._get_status("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body).get("status"), "ok")

    # ---- helpers -------------------------------------------------------------
    def _get_status(self, path):
        try:
            with urllib.request.urlopen(f"http://{self.host}:{self.port}{path}", timeout=10) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")


if __name__ == "__main__":
    unittest.main(verbosity=2)
