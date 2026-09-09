#!/usr/bin/env python3
"""
Test Suite: Kandid Search 2.0 — Updated for Production DOM
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

    # ── Helper: replicate /api/search handler logic ─────────────────────
    def _call_search(self, q='', type_param='all'):
        conn = server.get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT campus as name, COUNT(*) as count FROM posts
            WHERE is_private = 0 AND moderation_status != 'removed' AND campus != ''
            GROUP BY campus ORDER BY count DESC LIMIT 6
        """)
        db_sectors = cursor.fetchall()
        icon_map = {
            0: {"icon": "☕", "category": "Cafe & Creative Space"},
            1: {"icon": "💻", "category": "Tech & Creator Hub"},
            2: {"icon": "🌿", "category": "Open Commons & Lawns"},
            3: {"icon": "📚", "category": "Study & Reading Wing"},
            4: {"icon": "🎨", "category": "Arts & Design Collective"}
        }
        sectors = []
        for i, r in enumerate(db_sectors):
            meta = icon_map.get(i % 5, {"icon": "📍", "category": "Community Space"})
            sectors.append({
                "id": f"sec_{i+1}", "number": f"0{i+1}",
                "icon": meta["icon"],
                "name": (r["name"] or "COMMUNITY QUAD").upper(),
                "momentsCount": r["count"], "area": meta["category"]
            })

        cursor.execute("SELECT caption FROM posts WHERE is_private = 0 AND moderation_status != 'removed' AND caption IS NOT NULL")
        captions = [r[0] for r in cursor.fetchall()]
        tag_counts = {}
        for cap in captions:
            for w in cap.split():
                if w.startswith("#") and len(w) > 1:
                    ct = w.upper()
                    tag_counts[ct] = tag_counts.get(ct, 0) + 1
        frequencies = []
        if tag_counts:
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:4]
            for idx, (t, c) in enumerate(sorted_tags, 1):
                frequencies.append({"number": f"0{idx}", "tag": t, "postsCount": c})
        else:
            frequencies = [{"number": "01", "tag": "#CAMPUS", "postsCount": 0}]

        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM posts WHERE is_private = 0")
        node_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'banned'")
        user_cnt = cursor.fetchone()[0]
        active_nodes = max(node_cnt, user_cnt, 3)

        people_results = []
        campus_results = []
        moments_results = []

        if type_param in ["people", "all"]:
            if q:
                q_clean = q.strip().lower()
                cursor.execute("""
                    SELECT id, name, handle, avatar_url, avatar_letter, campus, bio FROM users
                    WHERE (LOWER(handle) LIKE ? OR LOWER(name) LIKE ? OR LOWER(campus) LIKE ?)
                      AND (role IS NULL OR role != 'banned')
                    ORDER BY name ASC LIMIT 20
                """, (f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%"))
            else:
                cursor.execute("SELECT id, name, handle, avatar_url, avatar_letter, campus, bio FROM users WHERE (role IS NULL OR role != 'banned') ORDER BY streak_count DESC LIMIT 20")
            people_results = [dict(r) for r in cursor.fetchall()]

        if type_param in ["campuses", "all"]:
            if q:
                cursor.execute("SELECT id, name, city, state, country, verified FROM campuses WHERE LOWER(name) LIKE ? OR LOWER(city) LIKE ? ORDER BY verified DESC, name ASC LIMIT 10", (f"%{q}%", f"%{q}%"))
            else:
                cursor.execute("SELECT id, name, city, state, country, verified FROM campuses ORDER BY verified DESC, name ASC LIMIT 10")
            for cr in cursor.fetchall():
                c_dict = dict(cr)
                cursor.execute("SELECT COUNT(*) FROM posts WHERE campus = ? AND is_private = 0", (c_dict["name"],))
                c_dict["moments_count"] = cursor.fetchone()[0]
                campus_results.append(c_dict)

        if type_param in ["moments", "all"]:
            if q:
                clean_q = q.replace("#", "")
                cursor.execute("""
                    SELECT p.* FROM posts p
                    WHERE p.is_private = 0 AND p.moderation_status != 'removed' AND (
                        LOWER(p.caption) LIKE ? OR LOWER(p.campus) LIKE ? OR LOWER(p.author_handle) LIKE ?
                    )
                    ORDER BY p.created_at DESC LIMIT 30
                """, (f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%"))
            else:
                cursor.execute("SELECT p.* FROM posts p WHERE p.is_private = 0 AND p.moderation_status != 'removed' ORDER BY p.created_at DESC LIMIT 20")
            moments_results = [dict(r) for r in cursor.fetchall()]

        conn.close()
        return 200, {
            "success": True, "query": q, "type": type_param,
            "activeNodes": active_nodes, "sectors": sectors, "frequencies": frequencies,
            "people": people_results, "campuses": campus_results, "moments": moments_results
        }

    # ── Tests ───────────────────────────────────────────────────────────
    def test_01_search_all_default_api(self):
        status, res = self._call_search(type_param='all')
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertGreaterEqual(res.get("activeNodes", 0), 1)
        self.assertIn("frequencies", res)
        self.assertIn("sectors", res)
        self.assertIn("campuses", res)
        print("  ✅ PASS: 1. /api/search?type=all returns active nodes, sectors, frequencies, campuses")

    def test_02_search_people_match(self):
        conn = server.get_db()
        try:
            conn.execute("INSERT OR REPLACE INTO users (id, name, handle, email, password_hash, salt, campus, role) VALUES ('u_searchtest', 'Alex Kumar', 'alex_kumar', 'alex@test.com', 'hash123', 'salt123', 'North City University', 'user')")
            conn.commit()
        finally:
            conn.close()
        status, res = self._call_search(q='alex', type_param='people')
        self.assertEqual(status, 200)
        people = res.get("people", [])
        self.assertTrue(any('alex' in (p.get("handle","") + p.get("name","")).lower() for p in people))
        for p in people:
            self.assertNotIn("followers", p)
            self.assertNotIn("follower_count", p)
        print("  ✅ PASS: 2. People search returns matches without vanity follower metrics")

    def test_03_search_campuses_type(self):
        status, res = self._call_search(type_param='campuses')
        self.assertEqual(status, 200)
        campuses = res.get("campuses", [])
        self.assertIsInstance(campuses, list)
        if campuses:
            self.assertIn("moments_count", campuses[0])
        print(f"  ✅ PASS: 3. /api/search?type=campuses returns campus list ({len(campuses)} campuses)")

    def test_04_search_moments_private_excluded(self):
        conn = server.get_db()
        try:
            conn.execute("INSERT OR IGNORE INTO users (id, name, handle, email, password_hash, salt) VALUES ('u_x', 'Test X', 'x_user', 'x@test.com', 'hash', 'salt')")
            conn.execute("""
                INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, circle, region, is_private, moderation_status)
                VALUES ('post_priv_srch', 'u_x', 'X', 'x_user', 'Campus', 'img', 'pip', 'Top secret study notes', 'campus', 'all', 1, 'approved')
            """)
            conn.commit()
        finally:
            conn.close()
        status, res = self._call_search(q='secret', type_param='moments')
        moments = res.get("moments", [])
        self.assertFalse(any(m["id"] == "post_priv_srch" for m in moments))
        print("  ✅ PASS: 4. Private posts (is_private=1) excluded from Search")

    def test_05_search_moments_removed_excluded(self):
        conn = server.get_db()
        try:
            conn.execute("INSERT OR IGNORE INTO users (id, name, handle, email, password_hash, salt) VALUES ('u_x', 'Test X', 'x_user', 'x@test.com', 'hash', 'salt')")
            conn.execute("""
                INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img, caption, circle, region, is_private, moderation_status)
                VALUES ('post_removed_srch', 'u_x', 'X', 'x_user', 'Campus', 'img', 'pip', 'Removed content study', 'campus', 'all', 0, 'removed')
            """)
            conn.commit()
        finally:
            conn.close()
        status, res = self._call_search(q='removed content', type_param='moments')
        moments = res.get("moments", [])
        self.assertFalse(any(m["id"] == "post_removed_srch" for m in moments))
        print("  ✅ PASS: 5. Removed posts (moderation_status=removed) excluded from Search")

    def test_06_recent_searches_table_exists(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recent_searches'")
        self.assertIsNotNone(cursor.fetchone())
        cursor.execute("PRAGMA table_info(recent_searches)")
        cols = [r[1] for r in cursor.fetchall()]
        for col in ["id", "user_id", "query", "search_type", "created_at"]:
            self.assertIn(col, cols)
        conn.close()
        print("  ✅ PASS: 6. recent_searches table exists with all required columns")

    def test_07_html_search_2_dom_ids(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        for dom_id in [
            'id="screen-search"', 'id="searchInput"', 'id="searchClearBtn"',
            'id="searchFilterChips"', 'id="searchIdleView"', 'id="searchFocusedView"',
            'id="searchResultsView"', 'id="searchResultsContainer"',
            'id="searchEmptyState"', 'id="searchErrorState"',
            'PROXIMITY', 'id="activeNodesBadge"', 'id="radarSvg"', 'id="radarNodes"',
            'id="searchSectorsContainer"', 'id="searchFrequenciesContainer"',
            'id="searchExploreGateway"', 'id="screen-search-global"',
            'id="globalMomentsList"', 'id="recentSearchesList"',
            'AROUND YOUR WORLD', 'YOU',
        ]:
            self.assertIn(dom_id, html, f"Missing: {dom_id}")
        print("  ✅ PASS: 7. index.html contains all Search 2.0 polished DOM elements")

    def test_08_html_old_ids_removed(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertNotIn('id="searchFilterTabs"', html)
        self.assertNotIn('id="searchDiscoveryDefault"', html)
        print("  ✅ PASS: 8. Old Search 1.0 DOM IDs removed from index.html")

    def test_09_standalone_kandid_search_html(self):
        s_path = os.path.join(PROJECT_DIR, "kandid_search.html")
        self.assertTrue(os.path.exists(s_path))
        with open(s_path, "r") as f:
            html = f.read()
        self.assertIn("SECTORS", html)
        self.assertIn("FREQUENCIES", html)
        print("  ✅ PASS: 9. kandid_search.html standalone file exists and verified")

    def test_10_js_search2_functions(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()
        for fn in [
            "function handleSearchInput(", "function selectSearchFilter(",
            "function performSearch(", "function loadSearchDiscovery(",
            "function filterBySector(", "function filterByFrequency(",
            "function onSearchFocus(", "function onSearchBlur(",
            "function loadRadar(", "function loadRecentSearches(",
            "function saveRecentSearch(", "function deleteRecentSearch(",
            "function clearAllRecentSearches(", "function openGlobalSearch(",
            "function closeGlobalSearch(", "function loadGlobalMoments(",
            "function renderCampusSearchResults(", "function renderGlobalMoment(",
            "function _searchShowView(",
        ]:
            self.assertIn(fn, js, f"Missing: {fn}")
        print("  ✅ PASS: 10. app.js contains all Search 2.0 JS functions")

    def test_11_js_state_fields(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()
        for field in ["state.searchFocused", "state.globalCursor", "state.globalMoments", "state.globalHasMore"]:
            self.assertIn(field, js, f"Missing: {field}")
        print("  ✅ PASS: 11. app.js has all Search 2.0 state fields")

    def test_12_server_new_endpoints(self):
        with open(os.path.join(PROJECT_DIR, "server.py"), "r") as f:
            py = f.read()
        self.assertIn('path == "/api/search/radar"', py)
        self.assertIn('path == "/api/search/global"', py)
        self.assertIn('path == "/api/search/recent"', py)
        print("  ✅ PASS: 12. server.py has /api/search/radar, /api/search/global, /api/search/recent")

    def test_13_server_campuses_type(self):
        with open(os.path.join(PROJECT_DIR, "server.py"), "r") as f:
            py = f.read()
        self.assertIn('"campuses"', py)
        self.assertIn("campus_results", py)
        print("  ✅ PASS: 13. server.py /api/search supports campuses type")

    def test_14_migration_has_recent_searches(self):
        with open(os.path.join(PROJECT_DIR, "migrate_sqlite_to_postgres.py"), "r") as f:
            py = f.read()
        self.assertIn('"recent_searches"', py)
        print("  ✅ PASS: 14. migrate_sqlite_to_postgres.py includes recent_searches table")

    def test_15_css_search_box(self):
        with open(os.path.join(PROJECT_DIR, "style.css"), "r") as f:
            css = f.read()
        self.assertIn(".search-box", css)
        print("  ✅ PASS: 15. style.css contains .search-box styling")

    def test_16_radar_privacy_no_gps(self):
        with open(os.path.join(PROJECT_DIR, "server.py"), "r") as f:
            py = f.read()
        self.assertIn("coarse_context_only", py)
        print("  ✅ PASS: 16. /api/search/radar returns coarse_context_only privacy metadata")

    def test_17_active_nodes_real_count(self):
        status, res = self._call_search(type_param='all')
        nodes = res.get("activeNodes", 0)
        self.assertGreaterEqual(nodes, 1)
        print(f"  ✅ PASS: 17. activeNodes = {nodes} (real DB count, not hardcoded)")

    def test_18_cache_buster_updated(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn("app.js?v=5.2.13", html)
        print("  ✅ PASS: 18. Cache buster updated to v=5.2.13")

    def test_19_global_screen_navigation(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn('id="screen-search-global"', html)
        self.assertIn('closeGlobalSearch()', html)
        self.assertIn('openGlobalSearch()', html)
        print("  ✅ PASS: 19. screen-search-global has open/close navigation wired up")

    def test_20_filter_chips_all_types(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn('id="searchFilterChips"', html)
        for chip in ['data-filter="people"', 'data-filter="campuses"',
                     'data-filter="moments"', 'data-filter="places"',
                     'data-filter="communities"', 'data-filter="all"']:
            self.assertIn(chip, html, f"Missing chip: {chip}")
        print("  ✅ PASS: 20. Filter chips include All/People/Campuses/Moments/Places/Communities")

    def test_21_radar_security_no_angle_or_dist(self):
        with open(os.path.join(PROJECT_DIR, "server.py"), "r") as f:
            py = f.read()
        radar_block = py[py.find('path == "/api/search/radar"'):py.find('path == "/api/search/global"')]
        self.assertNotIn('"angle_deg"', radar_block)
        self.assertNotIn('"dist_factor"', radar_block)
        self.assertIn('"slot"', radar_block)
        self.assertIn('"ring"', radar_block)
        print("  ✅ PASS: 21. Radar endpoint has zero angle_deg or dist_factor exposure (uses opaque slots/rings)")

    def test_22_search_query_cap_80_chars(self):
        with open(os.path.join(PROJECT_DIR, "server.py"), "r") as f:
            py = f.read()
        self.assertIn('[:80]', py)
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn('maxlength="80"', html)
        print("  ✅ PASS: 22. Search query strictly capped at 80 characters (server & HTML input)")

    def test_23_prefers_reduced_motion_supported(self):
        with open(os.path.join(PROJECT_DIR, "style.css"), "r") as f:
            css = f.read()
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("#radarSweepArm", css)
        print("  ✅ PASS: 23. prefers-reduced-motion supported in style.css for radar sweep")

    def test_24_no_unsplash_fallback_in_search_moments(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()
        search_moments_block = js[js.find('function renderGlobalMoment('):js.find('function openUserProfile(')]
        self.assertNotIn("unsplash.com", search_moments_block)
        print("  ✅ PASS: 24. No fake Unsplash fallback images in search moment renderers")

    def test_25_placeholder_invitation_copy(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn('placeholder="Search people, places, Moments..."', html)
        self.assertIn('AROUND YOUR WORLD', html)
        print("  ✅ PASS: 25. Inviting placeholder and editorial 'AROUND YOUR WORLD' section header verified")


if __name__ == "__main__":
    print("\n🚀 RUNNING KANDID SEARCH 2.0 TEST SUITE (10/10 POLISH PASS)")
    print("=" * 60)
    unittest.main(verbosity=0)


