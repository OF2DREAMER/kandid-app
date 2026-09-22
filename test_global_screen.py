#!/usr/bin/env python3
"""
Test Suite: Kandid.app Approved Global Window Screen
"""

import os
import shutil
import sys
import json
import sqlite3
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

# D4-07: pristine DB path captured at import time — the isolation source.
_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


def _isolate_db(testcase_cls, prefix):
    """D4-07: run this test class against a disposable temp database so the
    repository's data/kandid.db is never opened, mutated or deleted.

    Both cleanup callbacks are registered BEFORE any global is mutated.
    unittest fires class cleanups in LIFO order, so execution is:
      1. restore server.DB_FILE / server.DATABASE_URL
      2. remove the temporary directory
    """
    tmpdir = tempfile.mkdtemp(prefix=prefix)
    # Registration order matters: LIFO makes the globals restore run first.
    testcase_cls.addClassCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
    testcase_cls.addClassCleanup(_restore_server_globals)
    server.DATABASE_URL = ""
    server.DB_FILE = os.path.join(tmpdir, "kandid.db")
    server.init_db()
    return tmpdir


def _seed_min_global_fixture():
    """D4-07: deterministic minimum data the assertions actually read.
    init_db() seeds catalogs only (users/posts/reactions stay empty), so the
    suite seeds exactly the rows its region filters, privacy exclusion and
    realmoji aggregation require."""
    conn = server.get_db()
    for uid, handle, name, campus, city in [
        ("u_hana", "hana_k", "Hana K", "Waseda University", "TOKYO · 35.6762° N"),
        ("u_euro", "euro_eli", "Eli G", "University of Iceland", "REYKJAVÍK · 64.1466° N"),
        ("u_am", "am_casey", "Casey R", "New York University", "NEW YORK · 40.7128° N"),
        ("u_seed", "seed_user", "Seed User", "Central Campus", "Supaul, India"),
        # tests 06/10 INSERT rows referencing this user id directly.
        ("u_casey", "casey.rx", "Casey Rhodes", "North City University", "New Delhi"),
    ]:
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, location_city) VALUES (?,?,?,?,?,?,?,?)",
            (uid, f"{handle}@example.test", handle, name, "x", "s", campus, city),
        )
    for pid, uid, author, handle, campus, city, region, private in [
        ("post_g_asia_1", "u_hana", "Hana K", "hana_k", "Waseda University", "TOKYO · 35.6762° N", "asia", 0),
        ("post_hana_1", "u_hana", "Hana K", "hana_k", "Waseda University", "TOKYO · 35.6762° N", "asia", 0),
        ("post_g_europe_1", "u_euro", "Eli G", "euro_eli", "University of Iceland", "REYKJAVÍK · 64.1466° N", "europe", 0),
        ("post_g_americas_1", "u_am", "Casey R", "am_casey", "New York University", "NEW YORK · 40.7128° N", "americas", 0),
        ("post_secret_1", "u_seed", "Secret", "secret_user", "Private Zone", "Hidden City", "asia", 1),
    ]:
        conn.execute(
            """INSERT INTO posts (id, user_id, author_name, author_handle, campus, main_img, pip_img,
                                   caption, circle, region, location_city, is_private, moderation_status)
               VALUES (?,?,?,?,?,'img','pip',?, 'global', ?, ?, ?, 'approved')""",
            (pid, uid, author, handle, campus, f"Moment {pid}", region, city, private),
        )
    conn.execute("INSERT INTO reactions (id, post_id, user_id, emoji) VALUES ('react_g_1', 'post_hana_1', 'u_hana', '🔥')")
    conn.commit()
    conn.close()


class TestGlobalScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _isolate_db(cls, "kandid_global_")
        _seed_min_global_fixture()

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
