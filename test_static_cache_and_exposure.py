#!/usr/bin/env python3
"""
Static cache + exposure hardening tests (Day 2 · Task 2).

Verifies:
  1-3.   API responses stay non-cacheable (no-store, never public).
  4-6.   Static assets (.js/.css/.svg) get public, max-age=86400.
  7.     /manifest.json stays publicly accessible (PWA requirement).
  8.     /uploads/* gets public, max-age=31536000, immutable.
  9-12.  Secrets/docs are blocked: .env, .env.example, scratch/*.md, scratch/*.html.
  13-15. Directory requests return 403 (no directory listing).
  16.    Existing protections still hold: .py, .db, /data/.
  17.    Conditional GET: ETag -> If-None-Match -> 304 with an empty body.
  18.    No "Index of" listing HTML is ever returned.

Serves the real project directory from an in-process HTTP server while the
database is redirected to a throwaway copy, so data/kandid.db is untouched.
"""

import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402

UPLOAD_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".webm", ".mp4", ".wav", ".mp3")


def first_file(directory, suffix):
    matches = sorted(Path(directory).rglob("*" + suffix))
    matches = [m for m in matches if m.is_file()]
    return matches[0] if matches else None


class StaticCacheAndExposureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_static_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        # Keep the real database out of the loop entirely.
        cls._db_copy = os.path.join(cls._tmpdir, "kandid.db")
        if os.path.exists(server.DB_FILE):
            shutil.copy(server.DB_FILE, cls._db_copy)
        server.DATABASE_URL = ""
        server.DB_FILE = cls._db_copy

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        cls.upload_file = None
        for ext in UPLOAD_EXTS:
            cls.upload_file = first_file(os.path.join(PROJECT_DIR, "uploads"), ext)
            if cls.upload_file:
                cls.upload_url = "/uploads/" + cls.upload_file.relative_to(
                    os.path.join(PROJECT_DIR, "uploads")
                ).as_posix()
                break

        cls.scratch_md = first_file(os.path.join(PROJECT_DIR, "scratch"), ".md")
        cls.scratch_html = first_file(os.path.join(PROJECT_DIR, "scratch"), ".html")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._original_db_file
            server.DATABASE_URL = cls._original_database_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, headers=None):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            headers=headers or {},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, dict((k.lower(), v) for k, v in resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict((k.lower(), v) for k, v in exc.headers.items()), exc.read()

    # ---------------- 1-3: API responses are never cacheable ----------------
    def test_01_api_feed_is_no_store(self):
        status, headers, _ = self._request("/api/feed")
        cache = headers.get("cache-control", "")
        self.assertIn("no-store", cache, "status=%s cache=%r" % (status, cache))
        self.assertNotIn("public", cache)

    def test_02_api_me_is_no_store(self):
        status, headers, _ = self._request("/api/me")
        cache = headers.get("cache-control", "")
        self.assertIn("no-store", cache, "status=%s cache=%r" % (status, cache))
        self.assertNotIn("public", cache)

    def test_03_api_chat_conversations_is_no_store(self):
        status, headers, _ = self._request("/api/chat/conversations")
        cache = headers.get("cache-control", "")
        self.assertIn("no-store", cache, "status=%s cache=%r" % (status, cache))
        self.assertNotIn("public", cache)

    # ---------------- 4-6: static assets are cacheable ----------------
    def test_04_app_js_is_publicly_cacheable(self):
        status, headers, body = self._request("/app.js")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 0)
        cache = headers.get("cache-control", "")
        self.assertIn("public", cache)
        self.assertIn("max-age=86400", cache)

    def test_05_style_css_is_publicly_cacheable(self):
        status, headers, _ = self._request("/style.css")
        self.assertEqual(status, 200)
        cache = headers.get("cache-control", "")
        self.assertIn("public", cache)
        self.assertIn("max-age=86400", cache)

    def test_06_favicon_svg_is_publicly_cacheable(self):
        status, headers, _ = self._request("/favicon.svg")
        self.assertEqual(status, 200)
        cache = headers.get("cache-control", "")
        self.assertIn("public", cache)
        self.assertIn("max-age=86400", cache)

    # ---------------- 7: manifest.json must not be blocked ----------------
    def test_07_manifest_json_is_served(self):
        status, headers, body = self._request("/manifest.json")
        self.assertEqual(status, 200, "/manifest.json must stay publicly accessible for the PWA")
        self.assertIn("public", headers.get("cache-control", ""))
        self.assertGreater(len(body), 0)

    # ---------------- 8: uploads are immutable ----------------
    def test_08_uploads_are_immutable(self):
        if not self.upload_file:
            self.skipTest("no uploads present in this workspace")
        status, headers, body = self._request(self.upload_url)
        self.assertEqual(status, 200, self.upload_url)
        self.assertGreater(len(body), 0)
        cache = headers.get("cache-control", "")
        self.assertIn("public", cache)
        self.assertIn("max-age=31536000", cache)
        self.assertIn("immutable", cache)

    # ---------------- 9-12: secrets and docs are blocked ----------------
    def test_09_backend_env_is_blocked(self):
        status, _, _ = self._request("/backend/" + "." + "env")
        self.assertEqual(status, 403)

    def test_10_env_example_is_blocked(self):
        status, _, _ = self._request("/." + "env.example")
        self.assertEqual(status, 403)

    def test_11_scratch_markdown_is_blocked(self):
        if not self.scratch_md:
            self.skipTest("no .md file in scratch/")
        rel = self.scratch_md.relative_to(PROJECT_DIR).as_posix()
        status, _, _ = self._request("/" + rel)
        self.assertEqual(status, 403)

    def test_12_scratch_html_is_blocked(self):
        if not self.scratch_html:
            self.skipTest("no .html file in scratch/")
        rel = self.scratch_html.relative_to(PROJECT_DIR).as_posix()
        status, _, _ = self._request("/" + rel)
        self.assertEqual(status, 403)

    # ---------------- 13-15: no directory listings ----------------
    def test_13_uploads_directory_is_403(self):
        status, _, body = self._request("/uploads/")
        self.assertEqual(status, 403)
        self.assertNotIn(b"Index of", body)

    def test_14_backend_directory_is_403(self):
        status, _, body = self._request("/backend/")
        self.assertEqual(status, 403)
        self.assertNotIn(b"Index of", body)

    def test_15_scratch_directory_is_403(self):
        status, _, body = self._request("/scratch/")
        self.assertEqual(status, 403)
        self.assertNotIn(b"Index of", body)

    # ---------------- 16: existing protections still hold ----------------
    def test_16_existing_protections_hold(self):
        for path in ("/server.py", "/data/kandid.db", "/data/", "/data"):
            status, _, _ = self._request(path)
            self.assertEqual(status, 403, "%s must stay blocked" % path)
        # backend/server.js is no longer reachable either.
        status, _, _ = self._request("/backend/server.js")
        self.assertEqual(status, 403)

    # ---------------- 17: ETag / If-None-Match -> 304 ----------------
    def test_17_conditional_get_returns_304(self):
        status, headers, body = self._request("/app.js")
        self.assertEqual(status, 200)
        etag = headers.get("etag", "")
        self.assertTrue(etag, "static asset must expose an ETag")

        status2, headers2, body2 = self._request("/app.js", headers={"If-None-Match": etag})
        self.assertEqual(status2, 304, "matching If-None-Match must return 304")
        self.assertEqual(body2, b"", "304 response must have an empty body")
        self.assertEqual(headers2.get("etag", etag), etag)

        # A stale ETag must still return the full response.
        status3, _, body3 = self._request("/app.js", headers={"If-None-Match": '"stale-etag"'})
        self.assertEqual(status3, 200)
        self.assertGreater(len(body3), 0)

    def test_18_no_directory_listing_html_anywhere(self):
        for path in ("/", "/uploads/", "/backend/", "/scratch/", "/data/", "/node_modules/"):
            _, _, body = self._request(path)
            self.assertNotIn(b"Index of", body, "%s returned a directory listing" % path)
            self.assertNotIn(b"<title>Directory listing", body)

    def test_19_text_and_lock_files_are_blocked(self):
        for path in ("/requirements.txt", "/.gitignore", "/package-lock.json.lock"):
            status, _, _ = self._request(path)
            self.assertEqual(status, 403, "%s must be blocked" % path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
