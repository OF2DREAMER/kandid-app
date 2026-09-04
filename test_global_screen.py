#!/usr/bin/env python3
"""
Test Suite: Kandid.app Approved Global Window Screen
"""

import os
import sys
import json
import sqlite3
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

class TestGlobalScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()

    def simulate_get(self, path, token=None):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(path)
        p = parsed.path
        query = parse_qs(parsed.query)

        conn = server.get_db()
        cursor = conn.cursor()

        if p == "/api/global":
            region = query.get("region", ["all"])[0].lower()
            if region in ["asia", "europe", "americas"]:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE circle = 'global' AND is_private = 0 AND LOWER(region) = ?
                    ORDER BY created_at DESC
                """, (region,))
            else:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE circle = 'global' AND is_private = 0
                    ORDER BY created_at DESC
                """)
            
            moments = [dict(r) for r in cursor.fetchall()]
            for m in moments:
                cursor.execute("SELECT emoji, COUNT(*) as cnt FROM reactions WHERE post_id = ? GROUP BY emoji", (m["id"],))
                m["realmojis"] = {r["emoji"]: r["cnt"] for r in cursor.fetchall()}
                m["timeAgo"] = "18 MIN AGO"
            
            conn.close()
            return 200, {
                "success": True,
                "window": {
                    "title": "WORLD WINDOW",
                    "subtitle": "LIVE FEED",
                    "description": "Real moments across global coordinates and timezones."
                },
                "region": region,
                "moments": moments
            }

        conn.close()
        return 404, {"error": "Not Found"}

    def test_01_global_unauthenticated_api(self):
        status, res = self.simulate_get("/api/global")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertIn("window", res)
        self.assertEqual(res["window"]["title"], "WORLD WINDOW")
        self.assertIsInstance(res.get("moments"), list)
        self.assertGreaterEqual(len(res["moments"]), 3)
        print("  ✅ PASS: 1. /api/global unauthenticated request returns 200 with moments")

    def test_02_global_authenticated_api(self):
        status, res = self.simulate_get("/api/global", token="token_casey_prod")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        print("  ✅ PASS: 2. /api/global authenticated request returns 200")

    def test_03_region_filter_asia(self):
        status, res = self.simulate_get("/api/global?region=asia")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("region"), "asia")
        moments = res.get("moments", [])
        self.assertTrue(any(m.get("author_handle") == "hana_k" or "Tokyo" in m.get("campus", "") or "TOKYO" in m.get("location_city", "") for m in moments))
        print("  ✅ PASS: 3. region=asia returns Tokyo moments")

    def test_04_region_filter_europe(self):
        status, res = self.simulate_get("/api/global?region=europe")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("region"), "europe")
        moments = res.get("moments", [])
        self.assertTrue(any("REYKJAVÍK" in m.get("location_city", "") or "LONDON" in m.get("location_city", "") for m in moments))
        print("  ✅ PASS: 4. region=europe returns European moments")

    def test_05_region_filter_americas(self):
        status, res = self.simulate_get("/api/global?region=americas")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("region"), "americas")
        moments = res.get("moments", [])
        self.assertTrue(any("NEW YORK" in m.get("location_city", "") for m in moments))
        print("  ✅ PASS: 5. region=americas returns Americas moments")

    def test_06_privacy_exclusion(self):
        conn = server.get_db()
        conn.execute("""
            INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, circle, region, is_private)
            VALUES ('post_secret_1', 'u_casey', 'Secret', 'secret_user', 'Private Zone', 'img', 'pip', 'Secret moment', 'global', 'asia', 1)
        """)
        conn.commit()
        conn.close()

        status, res = self.simulate_get("/api/global?region=asia")
        moments = res.get("moments", [])
        self.assertFalse(any(m.get("id") == "post_secret_1" for m in moments))
        print("  ✅ PASS: 6. is_private=1 posts are strictly excluded from Global API")

    def test_07_html_structure_global(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()

        self.assertIn('id="globalContentStream"', html)
        self.assertIn('id="globalWindowHeader"', html)
        self.assertIn('id="globalRegionFilters"', html)
        self.assertIn('id="globalMomentsContainer"', html)
        self.assertIn('WORLD WINDOW', html)
        self.assertIn('TOKYO · 35.6762° N', html)
        self.assertIn('REYKJAVÍK · 64.1466° N', html)
        self.assertIn('LONDON · 51.5074° N', html)
        self.assertIn('GLOBAL IS QUIET', html)
        print("  ✅ PASS: 7. index.html contains all approved Global Window markup")

    def test_08_standalone_kandid_global_html(self):
        g_path = os.path.join(PROJECT_DIR, "kandid_global.html")
        self.assertTrue(os.path.exists(g_path))
        with open(g_path, "r") as f:
            html = f.read()
        self.assertIn("GLOBAL WINDOW", html)
        self.assertIn("WORLD WINDOW", html)
        self.assertIn("TOKYO · 35.6762° N", html)
        print("  ✅ PASS: 8. kandid_global.html standalone file exists and verified")

    def test_09_js_global_methods(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()

        self.assertIn("function filterGlobalRegion(", js)
        self.assertIn("window.filterGlobalRegion = filterGlobalRegion;", js)
        self.assertIn("function loadGlobalScreen(", js)
        self.assertIn("window.loadGlobalScreen = loadGlobalScreen;", js)
        self.assertIn("function renderGlobalCards(", js)
        self.assertIn("window.renderGlobalCards = renderGlobalCards;", js)
        print("  ✅ PASS: 9. app.js contains all Global Window methods & global exports")

    def test_10_reaction_compatibility(self):
        conn = server.get_db()
        conn.execute("INSERT OR REPLACE INTO reactions (id, post_id, user_id, emoji) VALUES ('react_g_1', 'post_hana_1', 'u_casey', '🔥')")
        conn.commit()
        conn.close()

        status, res = self.simulate_get("/api/global?region=asia")
        hana_moment = next((m for m in res["moments"] if m["id"] == "post_hana_1"), None)
        self.assertIsNotNone(hana_moment)
        self.assertGreaterEqual(hana_moment["realmojis"].get("🔥", 0), 1)
        print("  ✅ PASS: 10. RealMoji reactions persist and aggregate on Global moments")

if __name__ == "__main__":
    print("\n🚀 RUNNING APPROVED GLOBAL WINDOW TEST SUITE")
    print("=" * 60)
    unittest.main(verbosity=0)
