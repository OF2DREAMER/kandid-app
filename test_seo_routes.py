import os
import unittest
import xml.etree.ElementTree as ET
import urllib.robotparser
from io import BytesIO
from unittest.mock import MagicMock

import server


class TestSEORoutes(unittest.TestCase):
    def setUp(self):
        self.repo_dir = os.path.dirname(os.path.abspath(__file__))
        self.robots_path = os.path.join(self.repo_dir, "robots.txt")
        self.sitemap_path = os.path.join(self.repo_dir, "sitemap.xml")

    def test_robots_file_exists_and_valid(self):
        self.assertTrue(os.path.exists(self.robots_path), "robots.txt must exist on disk")
        with open(self.robots_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(lines)

        # Allowed routes
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/"), "Root should be crawlable")
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/about"), "/about should be crawlable")
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/campuses"), "/campuses should be crawlable")
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/privacy"), "/privacy should be crawlable")
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/terms"), "/terms should be crawlable")

        # Disallowed routes
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/api/feed"), "/api/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/data/db"), "/data/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/scratch/tmp"), "/scratch/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/backend/test"), "/backend/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/uploads/chat_attachments/1.jpg"), "chat attachments must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/kandid_feed.html"), "orphan prototypes must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/admin"), "/admin must be disallowed")

        # Sitemap directive
        sitemaps = parser.site_maps()
        self.assertIsNotNone(sitemaps, "Sitemap directive must be present")
        self.assertIn("https://kindid.in/sitemap.xml", sitemaps)

    def test_sitemap_file_exists_and_valid_xml(self):
        self.assertTrue(os.path.exists(self.sitemap_path), "sitemap.xml must exist on disk")
        tree = ET.parse(self.sitemap_path)
        root = tree.getroot()

        self.assertEqual(root.tag, "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset")

        locs = [elem.text for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        expected_canonical_urls = [
            "https://kindid.in/",
            "https://kindid.in/about",
            "https://kindid.in/campuses",
            "https://kindid.in/privacy",
            "https://kindid.in/terms"
        ]
        self.assertEqual(locs, expected_canonical_urls)

        # Confirm no disallowed or internal patterns in any url
        for loc in locs:
            self.assertTrue(loc.startswith("https://kindid.in/"))
            self.assertNotIn("localhost", loc)
            self.assertNotIn("127.0.0.1", loc)
            self.assertNotIn("/api", loc)
            self.assertNotIn("/data", loc)
            self.assertNotIn("chat", loc)

    def test_is_blocked_static_path_exempts_robots(self):
        # /robots.txt must NOT be blocked
        self.assertFalse(server.is_blocked_static_path("/robots.txt"))
        self.assertFalse(server.is_blocked_static_path("/sitemap.xml"))

        # Other .txt files and sensitive paths must REMAIN blocked
        self.assertTrue(server.is_blocked_static_path("/requirements.txt"))
        self.assertTrue(server.is_blocked_static_path("/notes.txt"))
        self.assertTrue(server.is_blocked_static_path("/data/kandid.db"))
        self.assertTrue(server.is_blocked_static_path("/.env"))
        self.assertTrue(server.is_blocked_static_path("/server.py"))

    def test_handler_serves_robots_and_sitemap(self):
        # Test simulated GET /robots.txt
        handler = server.KandidHandler.__new__(server.KandidHandler)
        handler.headers = {}
        handler.wfile = BytesIO()
        handler._headers_sent = []

        sent_status = []
        sent_headers = {}

        def fake_send_response(code):
            sent_status.append(code)

        def fake_send_header(name, val):
            sent_headers[name.lower()] = val

        def fake_end_headers():
            pass

        handler.send_response = fake_send_response
        handler.send_header = fake_send_header
        handler.end_headers = fake_end_headers

        # 1. GET /robots.txt
        handler.path = "/robots.txt"
        handler.do_GET()
        self.assertEqual(sent_status, [200])
        self.assertIn("text/plain", sent_headers.get("content-type", ""))
        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("Sitemap: https://kindid.in/sitemap.xml", body)

        # 2. GET /sitemap.xml
        sent_status.clear()
        sent_headers.clear()
        handler.wfile = BytesIO()
        handler.path = "/sitemap.xml"
        handler.do_GET()
        self.assertEqual(sent_status, [200])
        self.assertEqual(sent_headers.get("content-type"), "application/xml")
        xml_body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("<loc>https://kindid.in/</loc>", xml_body)

        # 2b. GET /https://kindid.in/sitemap.xml (GSC paste trap fallback)
        sent_status.clear()
        sent_headers.clear()
        handler.wfile = BytesIO()
        handler.path = "/https://kindid.in/sitemap.xml"
        handler.do_GET()
        self.assertEqual(sent_status, [200])
        self.assertEqual(sent_headers.get("content-type"), "application/xml")

        # 3. HEAD /robots.txt
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/robots.txt"
        handler.do_HEAD()
        self.assertEqual(sent_status, [200])
        self.assertIn("text/plain", sent_headers.get("content-type", ""))
        self.assertTrue(int(sent_headers.get("content-length", 0)) > 0)

        # 4. HEAD /sitemap.xml
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/sitemap.xml"
        handler.do_HEAD()
        self.assertEqual(sent_status, [200])
        self.assertEqual(sent_headers.get("content-type"), "application/xml")
        self.assertTrue(int(sent_headers.get("content-length", 0)) > 0)

        # 5. HEAD /about
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/about"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/about.html")
            mock_head.assert_called_once()

        # 5b. GET /about
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/about"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_GET") as mock_get:
            handler.do_GET()
            self.assertEqual(handler.path, "/about.html")
            mock_get.assert_called_once()

        # 5c. GET /about/
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/about/"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_GET") as mock_get:
            handler.do_GET()
            self.assertEqual(handler.path, "/about.html")
            mock_get.assert_called_once()

        # 6. HEAD /campuses
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/campuses"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/campuses.html")
            mock_head.assert_called_once()

        # 6b. GET /campuses
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/campuses"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_GET") as mock_get:
            handler.do_GET()
            self.assertEqual(handler.path, "/campuses.html")
            mock_get.assert_called_once()

        # 7. HEAD /privacy
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/privacy"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/privacy.html")
            mock_head.assert_called_once()

        # 8. HEAD /terms
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/terms"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/terms.html")
            mock_head.assert_called_once()

        # 9. Canonical .html redirects -> 301
        for src, dst in (("/about.html", "/about"), ("/campuses.html", "/campuses"), ("/privacy.html", "/privacy"), ("/terms.html", "/terms"), ("/index.html", "/"), ("/landing", "/")):
            sent_status.clear()
            sent_headers.clear()
            handler.path = src
            handler.do_GET()
            self.assertEqual(sent_status, [301], f"Expected 301 redirect for {src}")
            self.assertEqual(sent_headers.get("location"), dst)

        # 10. Orphan prototype HTMLs & /requirements.txt -> 403 Forbidden
        for blocked in ("/requirements.txt", "/kandid_feed.html", "/kandid_search.html", "/kandid_campus.html"):
            sent_status.clear()
            sent_headers.clear()
            handler.wfile = BytesIO()
            handler.path = blocked
            handler.do_GET()
            self.assertEqual(sent_status, [403], f"Expected 403 for {blocked}")

    def test_kindid_branding_and_public_metadata_consistency(self):
        """All public pages use unified Kindid branding, OG images, canonical URLs, and PNG favicons."""
        public_pages = {
            "index.html": ("https://kindid.in/", "Kindid"),
            "about.html": ("https://kindid.in/about", "About Kindid"),
            "campuses.html": ("https://kindid.in/campuses", "Campus Circles"),
            "privacy.html": ("https://kindid.in/privacy", "Privacy Policy"),
            "terms.html": ("https://kindid.in/terms", "Terms of Service"),
        }
        for fname, (canonical, title_fragment) in public_pages.items():
            fpath = os.path.join(self.repo_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"Missing public page {fname}")
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(title_fragment, content, f"{fname} missing title fragment {title_fragment}")
            self.assertIn(f'<link rel="canonical" href="{canonical}">', content, f"{fname} missing canonical link")
            self.assertIn('property="og:image" content="https://kindid.in/og-image.png"', content, f"{fname} missing og:image")
            self.assertIn('name="twitter:image" content="https://kindid.in/og-image.png"', content, f"{fname} missing twitter:image")
            self.assertIn('/favicon-48.png', content, f"{fname} missing 48px PNG favicon")
            self.assertIn('/apple-touch-icon.png', content, f"{fname} missing apple-touch-icon")
            self.assertNotIn("cdn.tailwindcss.com", content, f"{fname} should use compiled Tailwind CSS")
            self.assertEqual(content.count("<h1"), 1, f"{fname} should have exactly one <h1>")

        # Verify about.html brand unification ("About Kindid", never "About Kandid")
        with open(os.path.join(self.repo_dir, "about.html"), "r", encoding="utf-8") as f:
            about_html = f.read()
        self.assertNotIn("About Kandid", about_html)
        self.assertNotIn("What is Kandid", about_html)

        # Verify homepage contains crawlable <a> links to all public SEO pages
        with open(os.path.join(self.repo_dir, "index.html"), "r", encoding="utf-8") as f:
            index_html = f.read()
        for target in ('href="/about"', 'href="/campuses"', 'href="/privacy"', 'href="/terms"'):
            self.assertIn(target, index_html, f"index.html missing crawlable link {target}")
        self.assertNotIn("user-scalable=no", index_html)

        # Verify raster PNG assets exist on disk
        for asset in ("og-image.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon-48.png"):
            self.assertTrue(os.path.exists(os.path.join(self.repo_dir, asset)), f"Missing SEO image asset {asset}")


class TestSEOLiveHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil, tempfile, threading, sqlite3
        from http.server import ThreadingHTTPServer

        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_seo_live_")
        cls._orig_db = server.DB_FILE
        cls._orig_pg = server.DATABASE_URL
        cls._db_path = os.path.join(cls._tmpdir, "seo_test.db")
        server.DATABASE_URL = ""
        server.DB_FILE = cls._db_path
        server.init_db()

        conn = sqlite3.connect(cls._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, role, is_onboarded, onboarding_status) "
            "VALUES ('u_seo_1', 'seo@kindid.in', 'seotester', 'SEO Tester', 'h', 's', 'student', 1, 'active')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, is_private, moderation_status) "
            "VALUES ('m_pub_1', 'u_seo_1', 'SEO Tester', 'seotester', 'Delhi University', 'https://res.cloudinary.com/demo/image/upload/sample.jpg', '', 'Sunset from North Campus', 0, 'active')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, is_private, moderation_status) "
            "VALUES ('m_priv_1', 'u_seo_1', 'SEO Tester', 'seotester', 'Delhi University', 'https://res.cloudinary.com/demo/image/upload/secret.jpg', '', 'Top secret private caption', 1, 'active')"
        )
        conn.commit()
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        import shutil
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._orig_db
            server.DATABASE_URL = cls._orig_pg
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get_raw(self, path):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        return resp.status, headers, body

    def test_root_cache_and_moment_og_engine(self):
        status, headers, body = self._get_raw("/")
        self.assertEqual(status, 200)
        self.assertNotIn("no-store", headers.get("cache-control", ""))
        self.assertIn("must-revalidate", headers.get("cache-control", ""))
        self.assertTrue(headers.get("etag"))

        # Public moment OG preview: single og:title & cloudinary image
        status_pub, _, body_pub = self._get_raw("/?moment=m_pub_1")
        self.assertEqual(status_pub, 200)
        self.assertEqual(body_pub.count('property="og:title"'), 1)
        self.assertIn("Moment by @seotester on Kindid", body_pub)
        self.assertIn("Sunset from North Campus", body_pub)
        self.assertIn("https://res.cloudinary.com/demo/image/upload/sample.jpg", body_pub)

        # Private moment must NEVER leak caption or image
        status_priv, _, body_priv = self._get_raw("/?moment=m_priv_1")
        self.assertEqual(status_priv, 200)
        self.assertNotIn("Top secret private caption", body_priv)
        self.assertNotIn("secret.jpg", body_priv)

    def test_canonical_redirects_and_noindex_headers(self):
        for src, dst in (("/about.html", "/about"), ("/campuses.html", "/campuses"), ("/index.html", "/"), ("/landing", "/")):
            status, headers, _ = self._get_raw(src)
            self.assertEqual(status, 301)
            self.assertEqual(headers.get("location"), dst)

        status_admin, headers_admin, _ = self._get_raw("/admin")
        self.assertEqual(status_admin, 200)
        self.assertEqual(headers_admin.get("x-robots-tag"), "noindex, nofollow")
        self.assertIn("no-store", headers_admin.get("cache-control", ""))

        status_campuses, _, body_campuses = self._get_raw("/campuses")
        self.assertEqual(status_campuses, 200)
        self.assertIn("Real Places. Real Campus Communities.", body_campuses)

        status_proto, _, _ = self._get_raw("/kandid_search.html")
        self.assertEqual(status_proto, 403)


if __name__ == "__main__":
    unittest.main()
