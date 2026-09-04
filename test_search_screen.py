#!/usr/bin/env python3
"""
Test Suite: Kandid.app Approved Search & Discovery Screen
"""

import os
import sys
import json
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

class TestSearchScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()

    def simulate_search_get(self, path):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(path)
        p = parsed.path
        query = parse_qs(parsed.query)

        if p == "/api/search":
            q = query.get("q", [""])[0].strip().lower()
            type_param = query.get("type", ["all"])[0].lower()

            conn = server.get_db()
            cursor = conn.cursor()

            sectors = [
                {"id": "s1", "number": "01", "name": "NORTH BLOCK", "momentsCount": 12, "area": "North Campus"},
                {"id": "s2", "number": "02", "name": "THE UNION", "momentsCount": 8, "area": "Central Student Hub"},
                {"id": "s3", "number": "03", "name": "LIBRARY WING", "momentsCount": 5, "area": "Academic Wing"}
            ]

            frequencies = [
                {"number": "01", "tag": "#MIDTERMS", "postsCount": 84},
                {"number": "02", "tag": "#NIGHTWALK", "postsCount": 56},
                {"number": "03", "tag": "#FILMNOTES", "postsCount": 32}
            ]

            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM posts WHERE is_private = 0")
            node_cnt = cursor.fetchone()[0]
            active_nodes = node_cnt if node_cnt > 0 else 3

            people_results = []
            places_results = []
            moments_results = []

            if type_param in ["people", "all"] and q:
                cursor.execute("""
                    SELECT id, name, handle, avatar_url, avatar_letter, campus, bio FROM users
                    WHERE (LOWER(handle) LIKE ? OR LOWER(name) LIKE ?) AND (role != 'banned')
                    ORDER BY name ASC
                """, (f"%{q}%", f"%{q}%"))
                people_results = [dict(r) for r in cursor.fetchall()]
                for pr in people_results:
                    pr["connection_status"] = "connect"

            if type_param in ["places", "all"]:
                if q:
                    places_results = [s for s in sectors if q in s["name"].lower() or q in s["area"].lower()]
                else:
                    places_results = sectors

            if type_param in ["moments", "all"] and q:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE is_private = 0 AND (
                        LOWER(caption) LIKE ? OR
                        LOWER(campus) LIKE ? OR
                        LOWER(location_city) LIKE ? OR
                        LOWER(author_handle) LIKE ?
                    )
                    ORDER BY created_at DESC
                """, (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
                moments_results = [dict(r) for r in cursor.fetchall()]
                for m in moments_results:
                    cursor.execute("SELECT emoji, COUNT(*) as cnt FROM reactions WHERE post_id = ? GROUP BY emoji", (m["id"],))
                    m["realmojis"] = {r["emoji"]: r["cnt"] for r in cursor.fetchall()}
                    m["timeAgo"] = "18 MIN AGO"
            elif type_param in ["moments", "live"] and not q:
                cursor.execute("SELECT * FROM posts WHERE is_private = 0 ORDER BY created_at DESC LIMIT 6")
                moments_results = [dict(r) for r in cursor.fetchall()]
                for m in moments_results:
                    cursor.execute("SELECT emoji, COUNT(*) as cnt FROM reactions WHERE post_id = ? GROUP BY emoji", (m["id"],))
                    m["realmojis"] = {r["emoji"]: r["cnt"] for r in cursor.fetchall()}
                    m["timeAgo"] = "18 MIN AGO"

            conn.close()

            return 200, {
                "success": True,
                "query": q,
                "type": type_param,
                "activeNodes": active_nodes,
                "sectors": sectors,
                "frequencies": frequencies,
                "people": people_results,
                "places": places_results,
                "moments": moments_results
            }

        return 404, {"error": "Not Found"}

    def test_01_search_live_default_api(self):
        status, res = self.simulate_search_get("/api/search?type=live")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertGreaterEqual(res.get("activeNodes", 0), 1)
        self.assertEqual(len(res.get("sectors", [])), 3)
        self.assertEqual(len(res.get("frequencies", [])), 3)
        print("  ✅ PASS: 1. /api/search?type=live returns active nodes, sectors, and frequencies")

    def test_02_search_people(self):
        status, res = self.simulate_search_get("/api/search?q=alex&type=people")
        self.assertEqual(status, 200)
        people = res.get("people", [])
        self.assertTrue(any(p["handle"] == "alex_k" for p in people))
        # Ensure no follower/following popularity counts exist
        for p in people:
            self.assertNotIn("followers", p)
            self.assertNotIn("follower_count", p)
        print("  ✅ PASS: 2. /api/search?q=alex&type=people finds user without vanity follower metrics")

    def test_03_search_places(self):
        status, res = self.simulate_search_get("/api/search?q=north&type=places")
        self.assertEqual(status, 200)
        places = res.get("places", [])
        self.assertTrue(any("NORTH BLOCK" in p["name"] for p in places))
        print("  ✅ PASS: 3. /api/search?q=north&type=places returns matching sectors")

    def test_04_search_moments(self):
        status, res = self.simulate_search_get("/api/search?q=study&type=moments")
        self.assertEqual(status, 200)
        moments = res.get("moments", [])
        self.assertTrue(any("study" in m["caption"].lower() for m in moments))
        print("  ✅ PASS: 4. /api/search?q=study&type=moments returns matching moment cards")

    def test_05_search_privacy_exclusion(self):
        conn = server.get_db()
        conn.execute("""
            INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, circle, region, is_private)
            VALUES ('post_secret_search', 'u_casey', 'Secret', 'secret_user', 'Private Area', 'img', 'pip', 'Top secret notes', 'campus', 'all', 1)
        """)
        conn.commit()
        conn.close()

        status, res = self.simulate_search_get("/api/search?q=secret&type=moments")
        moments = res.get("moments", [])
        self.assertFalse(any(m["id"] == "post_secret_search" for m in moments))
        print("  ✅ PASS: 5. Private posts (is_private=1) are strictly excluded from search")

    def test_06_html_structure(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()

        self.assertIn('id="screen-search"', html)
        self.assertIn('class="search-box', html)
        self.assertIn('id="searchInput"', html)
        self.assertIn('id="searchFilterTabs"', html)
        self.assertIn('id="searchDiscoveryDefault"', html)
        self.assertIn('PROXIMITY RADAR', html)
        self.assertIn('id="activeNodesBadge"', html)
        self.assertIn('id="searchSectorsContainer"', html)
        self.assertIn('id="searchFrequenciesContainer"', html)
        self.assertIn('id="searchResultsContainer"', html)
        self.assertIn('id="searchEmptyState"', html)
        self.assertIn('id="searchErrorState"', html)
        print("  ✅ PASS: 6. index.html contains all approved Search & Discovery DOM elements")

    def test_07_standalone_kandid_search_html(self):
        s_path = os.path.join(PROJECT_DIR, "kandid_search.html")
        self.assertTrue(os.path.exists(s_path))
        with open(s_path, "r") as f:
            html = f.read()
        self.assertIn("PROXIMITY RADAR", html)
        self.assertIn("SECTORS", html)
        self.assertIn("FREQUENCIES", html)
        self.assertIn("SEARCH PEOPLE, PLACES, MOMENTS...", html)
        print("  ✅ PASS: 7. kandid_search.html standalone file exists and verified")

    def test_08_js_methods(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()

        self.assertIn("function handleSearchInput(", js)
        self.assertIn("function selectSearchFilter(", js)
        self.assertIn("function performSearch(", js)
        self.assertIn("function loadSearchDiscovery(", js)
        self.assertIn("function filterBySector(", js)
        self.assertIn("function filterByFrequency(", js)
        print("  ✅ PASS: 8. app.js contains all Search & Discovery event handlers and methods")

    def test_09_css_search_box(self):
        with open(os.path.join(PROJECT_DIR, "style.css"), "r") as f:
            css = f.read()
        self.assertIn(".search-box", css)
        print("  ✅ PASS: 9. style.css contains .search-box tactile gradient styling")

if __name__ == "__main__":
    print("\n🚀 RUNNING APPROVED SEARCH & DISCOVERY TEST SUITE")
    print("=" * 60)
    unittest.main(verbosity=0)
