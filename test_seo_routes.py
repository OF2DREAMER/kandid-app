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
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/privacy"), "/privacy should be crawlable")
        self.assertTrue(parser.can_fetch("*", "https://kindid.in/terms"), "/terms should be crawlable")

        # Disallowed routes
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/api/feed"), "/api/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/data/db"), "/data/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/scratch/tmp"), "/scratch/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/backend/test"), "/backend/ must be disallowed")
        self.assertFalse(parser.can_fetch("*", "https://kindid.in/uploads/chat_attachments/1.jpg"), "chat attachments must be disallowed")

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
        self.assertIn("application/xml", sent_headers.get("content-type", ""))
        xml_body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("<loc>https://kindid.in/</loc>", xml_body)

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
        self.assertIn("application/xml", sent_headers.get("content-type", ""))
        self.assertTrue(int(sent_headers.get("content-length", 0)) > 0)

        # 5. HEAD /privacy
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/privacy"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/privacy.html")
            mock_head.assert_called_once()

        # 6. HEAD /terms
        sent_status.clear()
        sent_headers.clear()
        handler.path = "/terms"
        with unittest.mock.patch.object(server.SimpleHTTPRequestHandler, "do_HEAD") as mock_head:
            handler.do_HEAD()
            self.assertEqual(handler.path, "/terms.html")
            mock_head.assert_called_once()

        # 7. GET /requirements.txt -> 403 Forbidden
        sent_status.clear()
        sent_headers.clear()
        handler.wfile = BytesIO()
        handler.path = "/requirements.txt"
        handler.do_GET()
        self.assertEqual(sent_status, [403])


if __name__ == "__main__":
    unittest.main()
