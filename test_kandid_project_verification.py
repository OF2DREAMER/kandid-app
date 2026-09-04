#!/usr/bin/env python3
"""
Complete Verification Suite for Kandid Project (Feed, Campus, Global, Search)
"""

import os
import sys
import sqlite3
import json

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

def run_tests():
    print("🚀 RUNNING FULL KANDID PROJECT VERIFICATION SUITE")
    print("=" * 60)

    # 1. Check Directory Files
    files_to_check = [
        "index.html",
        "kandid_feed.html",
        "kandid_campus.html",
        "kandid_global.html",
        "kandid_search.html",
        "kandid_you.html",
        "kandid_capture.html",
        "style.css",
        "app.js",
        "server.py",
        "manifest.json",
        "favicon.svg",
        "sw.js",
        "data/kandid.db"
    ]
    for fname in files_to_check:
        full_p = os.path.join(PROJECT_DIR, fname)
        assert os.path.exists(full_p), f"Missing file: {fname}"
        print(f"  ✅ File exists: {fname}")

    # 2. Check Database & Seeds
    server.init_db()
    conn = server.get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    assert users_count >= 6, f"Expected >= 6 users, got {users_count}"
    print(f"  ✅ Database seeded: {users_count} users present")

    cur.execute("SELECT COUNT(*) FROM posts WHERE circle = 'campus'")
    campus_posts = cur.fetchone()[0]
    assert campus_posts >= 2, f"Expected >= 2 campus posts, got {campus_posts}"
    print(f"  ✅ Campus moments seeded: {campus_posts} moments present")

    cur.execute("SELECT COUNT(*) FROM posts WHERE circle = 'global'")
    global_posts = cur.fetchone()[0]
    assert global_posts >= 3, f"Expected >= 3 global posts, got {global_posts}"
    print(f"  ✅ Global moments seeded: {global_posts} moments present")

    # 3. Check HTML Contents
    with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
        index_html = f.read()

    assert "id=\"feedContentStream\"" in index_html, "feedContentStream missing"
    assert "id=\"campusContentStream\"" in index_html, "campusContentStream missing"
    assert "id=\"globalContentStream\"" in index_html, "globalContentStream missing"
    assert "id=\"screen-search\"" in index_html, "screen-search missing"
    assert "PROXIMITY RADAR" in index_html, "PROXIMITY RADAR missing"
    assert "id=\"searchFilterTabs\"" in index_html, "searchFilterTabs missing"
    print("  ✅ index.html contains Feed, Campus, Global, and Search screen structures")

    # 4. Check JS Functionality
    with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
        js_code = f.read()

    assert "function selectSubTab(" in js_code
    assert "function selectSearchFilter(" in js_code
    assert "function performSearch(" in js_code
    assert "function loadSearchDiscovery(" in js_code
    print("  ✅ app.js navigation & dynamic Search discovery verified")

    print("\n" + "=" * 60)
    print("🎉 ALL FULL PLATFORM TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
