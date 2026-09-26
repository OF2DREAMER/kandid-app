#!/usr/bin/env python3
"""
Focused tests for KINDID Surgical Implementation Batch 1.

Verifies:
1. community pulse does not query community_drops
2. community manage does not query financial_ledger
3. community manage does not query community_transactions
4. creator dashboard does not query financial_ledger
5. creator dashboard does not query community_transactions
6. creator dashboard response contract matches frontend expectations
7. collective memories existing id -> 200
8. collective memories missing id -> 404
9. collective memories does not fabricate moments
10. event route is removed
11. campus_events reference removed from moderation audit and server.py
12. migration table list does not contain obsolete tables
13. active app.js pre-existing avatar change remains intact
"""

import ast
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler
import migrate_sqlite_to_postgres


class TestBatch1Cleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_batch1_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_batch1.db")
        server.init_db()

        # Insert test users, session, and community in the clean database.
        # Note: We strictly DO NOT create community_drops, financial_ledger,
        # community_transactions, or campus_events tables.
        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, is_creator, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u_creator", "creator@example.test", "creator_handle", "Creator User", "test_hash", "test_salt", 1, "creator"),
        )
        cursor.execute(
            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            ("test_token_creator", "u_creator", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, city, description, creator_id, creator_handle, members_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_test", "Test Campus Club", "Campus", "Campus City", "Desc", "u_creator", "creator_handle", 10),
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test", "u_creator", "owner", "active"),
        )
        # Also ensure collective_memories has an entry mem_1
        cursor.execute(
            "INSERT OR IGNORE INTO collective_memories (id, campus, community_name, title, date_str, moments_count, story, cover_img) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("mem_1", "Test Campus Club", "Test Campus Club", "Spring Fest", "Mar 2026", 0, "Memory story", "cover.jpg"),
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, token=None, method="GET", body=None):
        s1, s2 = socket.socketpair()
        class DummyServer:
            pass

        def run_handler():
            try:
                KandidHandler(s1, ("127.0.0.1", 12345), DummyServer())
            except Exception:
                pass
            finally:
                try:
                    s1.close()
                except Exception:
                    pass

        t = threading.Thread(target=run_handler)
        t.start()

        body_bytes = b""
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body_bytes = body.encode("utf-8")
            elif isinstance(body, bytes):
                body_bytes = body

        req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "\r\n"

        s2.settimeout(5.0)
        s2.sendall(req.encode("utf-8") + body_bytes)
        try:
            s2.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        chunks = []
        while True:
            try:
                chunk = s2.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        s2.close()
        t.join(timeout=5.0)

        raw = b"".join(chunks).decode("utf-8")
        headers_part, _, body_part = raw.partition("\r\n\r\n")
        status_line = headers_part.splitlines()[0]
        status_code = int(status_line.split()[1])
        try:
            body = json.loads(body_part)
        except Exception:
            body = body_part
        return status_code, body

    # 1. community pulse does not query community_drops
    def test_01_community_pulse_does_not_query_community_drops(self):
        status, body = self._request("/api/community/pulse?community_id=comm_test")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertIn("pulse_state", body)
        # Verify static code: no community_drops in pulse handler
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        pulse_start = code.find('if path == "/api/community/pulse":')
        pulse_end = code.find('if path == "/api/community/manage":')
        pulse_handler = code[pulse_start:pulse_end]
        self.assertNotIn("community_drops", pulse_handler)

    # 2. community manage does not query financial_ledger
    def test_02_community_manage_does_not_query_financial_ledger(self):
        status, body = self._request("/api/community/manage", token="test_token_creator")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        # Verify static code
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        manage_start = code.find('if path == "/api/community/manage":')
        manage_end = code.find('if path == "/api/community/memories/detail":')
        manage_handler = code[manage_start:manage_end]
        self.assertNotIn("financial_ledger", manage_handler)

    # 3. community manage does not query community_transactions
    def test_03_community_manage_does_not_query_community_transactions(self):
        status, body = self._request("/api/community/manage", token="test_token_creator")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        manage_start = code.find('if path == "/api/community/manage":')
        manage_end = code.find('if path == "/api/community/memories/detail":')
        manage_handler = code[manage_start:manage_end]
        self.assertNotIn("community_transactions", manage_handler)

    # 4. creator dashboard does not query financial_ledger
    def test_04_creator_dashboard_does_not_query_financial_ledger(self):
        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        dash_start = code.find('if path == "/api/creator/dashboard":')
        dash_end = code.find('if path.startswith("/api/"):', dash_start)
        dash_handler = code[dash_start:dash_end]
        self.assertNotIn("financial_ledger", dash_handler)

    # 5. creator dashboard does not query community_transactions
    def test_05_creator_dashboard_does_not_query_community_transactions(self):
        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        dash_start = code.find('if path == "/api/creator/dashboard":')
        dash_end = code.find('if path.startswith("/api/"):', dash_start)
        dash_handler = code[dash_start:dash_end]
        self.assertNotIn("community_transactions", dash_handler)

    # 6. creator dashboard response contract matches frontend expectations
    def test_06_creator_dashboard_contract_matches_frontend(self):
        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        overview = body.get("overview", {})
        # Frontend in app.js:7488-7491 expects these exact four counters:
        self.assertIn("spaces_managed", overview)
        self.assertIn("total_members", overview)
        self.assertIn("total_moments", overview)
        self.assertIn("live_pulse_count", overview)
        # Spaces list
        self.assertIn("spaces", body)
        self.assertIsInstance(body["spaces"], list)
        # No payment or dead drop entries in overview
        self.assertNotIn("total_drops_hosted", overview)
        self.assertNotIn("earnings", body)

    # 7. collective memories existing id -> 200
    def test_07_collective_memories_existing_id_200(self):
        status, body = self._request("/api/community/memories/detail?id=mem_1")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        memory = body.get("memory", {})
        self.assertEqual(memory.get("id"), "mem_1")
        self.assertIn("title", memory)
        self.assertIn("date_str", memory)
        self.assertIn("story", memory)
        self.assertIn("moments", body)
        self.assertIsInstance(body["moments"], list)

    # 8. collective memories missing id -> 404
    def test_08_collective_memories_missing_id_404(self):
        status, body = self._request("/api/community/memories/detail?id=non_existent_mem")
        self.assertEqual(status, 404)
        self.assertFalse(body.get("success"))
        status2, body2 = self._request("/api/community/memories/detail")
        self.assertEqual(status2, 404)
        self.assertFalse(body2.get("success"))

    # 9. collective memories does not fabricate moments
    def test_09_collective_memories_does_not_fabricate_moments(self):
        status, body = self._request("/api/community/memories/detail?id=mem_1")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("moments"), [])

    # 10. event route is removed
    def test_10_event_route_removed(self):
        status, body = self._request("/api/event?id=any_event")
        self.assertEqual(status, 404)
        self.assertFalse(body.get("success"))
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        self.assertNotIn('if path == "/api/event":', code)

    # 11. campus_events removed from server and shared handler preserves empty events
    def test_11_campus_events_removed_and_shared_handler_preserves_empty_events(self):
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            lines = f.readlines()
        executable_references = []
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if "campus_events" in stripped and not stripped.startswith("#"):
                executable_references.append((idx, stripped))
        self.assertEqual(executable_references, [], f"Executable campus_events found in server.py: {executable_references}")

        # Shared handler (/api/community/detail) preserves events and liveEvents as []
        status, body = self._request("/api/community/detail?community_id=comm_test")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("events"), [])
        self.assertEqual(body.get("liveEvents"), [])

    # 12. migration table list does not contain obsolete tables
    def test_12_migration_table_list_pruned(self):
        obsolete_tables = [
            "otps",
            "community_drops",
            "drop_orders",
            "community_drop_registrations",
            "community_transactions",
            "financial_ledger",
            "campus_events",
        ]
        for tbl in obsolete_tables:
            self.assertNotIn(tbl, migrate_sqlite_to_postgres.KANDID_TABLES)

        # drop_reminders is created by init_db (server.py:2732) and must be preserved
        self.assertIn("drop_reminders", migrate_sqlite_to_postgres.KANDID_TABLES)

    # 13. active app.js pre-existing avatar change remains intact
    def test_13_app_js_avatar_change_intact(self):
        with open(os.path.join(PROJECT_DIR, "app.js")) as f:
            app_js_content = f.read()
        self.assertIn("function triggerDirectAvatarUpload()", app_js_content)
        self.assertIn("function handleDirectAvatarUpload(event)", app_js_content)
        self.assertIn("window.triggerDirectAvatarUpload = triggerDirectAvatarUpload;", app_js_content)
        self.assertIn("youDirectAvatarInput", app_js_content)
        self.assertIn("youProfileAvatar", app_js_content)
        # Also ensure removed event functions are gone from app.js
        self.assertNotIn("function openEventDetail", app_js_content)
        self.assertNotIn("function closeEventDetail", app_js_content)
        self.assertNotIn("function captureEventMoment", app_js_content)


    # 14. creator dashboard total_members has no duplicates and only counts active members
    def test_14_creator_dashboard_total_members_no_duplicates_and_active_only(self):
        """Documented semantics:
        'TOTAL MEMBERS' = unique active members across the creator's managed communities.
        A user belonging to multiple communities managed by the same creator must be counted once.
        Inactive/banned rows must be excluded.
        """
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO communities (id, name, type, city, description, creator_id, creator_handle, members_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_test_2", "Second Managed Community", "Club", "City", "Desc", "u_creator", "creator_handle", 5),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test_2", "u_creator", "owner", "active"),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, is_creator, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u_member_1", "m1@test.com", "m1", "M One", "hash", "salt", 0, "user"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test", "u_member_1", "member", "active"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test_2", "u_member_1", "member", "active"),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, is_creator, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u_member_2", "m2@test.com", "m2", "M Two", "hash", "salt", 0, "user"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test", "u_member_2", "member", "active"),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, is_creator, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("u_member_3", "m3@test.com", "m3", "M Three", "hash", "salt", 0, "user"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO community_members (community_id, user_id, role, status) VALUES (?, ?, ?, ?)",
            ("comm_test", "u_member_3", "member", "inactive"),
        )
        conn.commit()
        conn.close()

        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        overview = body.get("overview", {})
        self.assertEqual(overview.get("total_members"), 3)

    # 15. creator dashboard total_moments scoping, deduplication, and moderation predicate
    def test_15_creator_dashboard_total_moments_scoping_dedup_and_moderation(self):
        """Requirements:
        - COUNT(DISTINCT posts.id)
        - primary_community_id OR context_community_id
        - is_private = 0
        - (moderation_status IS NULL OR moderation_status NOT IN ('hidden', 'removed', 'suspended'))
        - same post counted once even if both primary and context match
        - removed, hidden, and suspended content excluded
        - private content excluded
        """
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_a", "u_creator", "Creator", "creator", "img", "pip", 0, "comm_test", "comm_test_2", "active", "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_b", "u_creator", "Creator", "creator", "img", "pip", 0, "", "comm_test", None, "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_c", "u_creator", "Creator", "creator", "img", "pip", 1, "comm_test", "", "active", "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_d_removed", "u_creator", "Creator", "creator", "img", "pip", 0, "comm_test", "", "removed", "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_d_hidden", "u_creator", "Creator", "creator", "img", "pip", 0, "comm_test", "", "hidden", "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_d_suspended", "u_creator", "Creator", "creator", "img", "pip", 0, "comm_test", "", "suspended", "2026-09-01 10:00:00"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("post_e", "u_creator", "Creator", "creator", "img", "pip", 0, "unmanaged_comm", "", "active", "2026-09-01 10:00:00"),
        )
        conn.commit()
        conn.close()

        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        overview = body.get("overview", {})
        self.assertEqual(overview.get("total_moments"), 2)

    # 16. creator dashboard live pulse date window and scoping
    def test_16_creator_dashboard_live_pulse_time_window(self):
        """Requirements:
        - 2-hour LIVE NOW threshold: age_seconds <= 7200
        - post <= 7200 sec -> counted
        - post > 7200 sec and <= 86400 sec -> NOT counted as live
        - post > 86400 sec -> NOT counted
        - duplicate primary/context match counted once
        - hidden, removed, and suspended content excluded
        """
        now = datetime.now(timezone.utc)
        ts_live = (now - timedelta(seconds=1800)).isoformat()
        ts_live_dup = (now - timedelta(seconds=3600)).isoformat()
        ts_active = (now - timedelta(seconds=10000)).isoformat()
        ts_old = (now - timedelta(seconds=100000)).isoformat()
        ts_removed = (now - timedelta(seconds=1800)).isoformat()
        ts_hidden = (now - timedelta(seconds=1800)).isoformat()
        ts_suspended = (now - timedelta(seconds=1800)).isoformat()
        ts_private = (now - timedelta(seconds=1800)).isoformat()

        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts")
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'active', ?)",
            ("p_live_1", "u_creator", "C", "c", "img", "pip", ts_live)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', 'comm_test_2', 'active', ?)",
            ("p_live_2", "u_creator", "C", "c", "img", "pip", ts_live_dup)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'active', ?)",
            ("p_active_not_live", "u_creator", "C", "c", "img", "pip", ts_active)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'active', ?)",
            ("p_old_not_live", "u_creator", "C", "c", "img", "pip", ts_old)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'removed', ?)",
            ("p_live_removed", "u_creator", "C", "c", "img", "pip", ts_removed)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'hidden', ?)",
            ("p_live_hidden", "u_creator", "C", "c", "img", "pip", ts_hidden)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'suspended', ?)",
            ("p_live_suspended", "u_creator", "C", "c", "img", "pip", ts_suspended)
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 'comm_test', '', 'active', ?)",
            ("p_live_private", "u_creator", "C", "c", "img", "pip", ts_private)
        )
        conn.commit()
        conn.close()

        status, body = self._request("/api/creator/dashboard", token="test_token_creator")
        self.assertEqual(status, 200)
        overview = body.get("overview", {})
        self.assertEqual(overview.get("total_moments"), 4)
        self.assertEqual(overview.get("live_pulse_count"), 2)

    # 17. collective memories honest empty state consistency in API and UI logic
    def test_17_collective_memories_honest_empty_state_consistency(self):
        # Existing memory returns 200 with moments: []
        status, body = self._request("/api/community/memories/detail?id=mem_1")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("moments"), [])

        # Missing memory returns 404
        status_missing, body_missing = self._request("/api/community/memories/detail?id=non_existent_mem")
        self.assertEqual(status_missing, 404)
        self.assertFalse(body_missing.get("success"))

        with open(os.path.join(PROJECT_DIR, "app.js")) as f:
            app_code = f.read()

        self.assertNotIn("moments_count || 14", app_code)
        self.assertIn("(m.moments_count ?? 0)", app_code)
        self.assertIn("capturedByEl.textContent = 'No contributors yet';", app_code)
        self.assertIn("No moments captured yet.", app_code)

        with open(os.path.join(PROJECT_DIR, "index.html")) as f:
            html_code = f.read()
        self.assertNotIn("14 Moments captured together", html_code)
        self.assertIn('id="collectiveMemoryCountBadge" class="font-mono-tag text-[9px] text-zinc-300 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded">0 Moments captured together</span>', html_code)
        self.assertNotIn("Loading contributors", html_code)
        self.assertIn("No contributors yet", html_code)

    # 18. moderation action and report submission do not query community_drops
    def test_18_community_report_and_moderation_action_no_drops(self):
        # 1. Create a fresh, self-contained moment in the test database
        conn = server.get_db()
        cursor = conn.cursor()
        fresh_post_id = "post_fresh_test_18"
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, is_private, primary_community_id, context_community_id, moderation_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, 'comm_test', '', 'active', ?)",
            (fresh_post_id, "u_creator", "Creator", "creator", "img", "pip", datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

        # 2. target_type == 'drop' is rejected by report validation
        status, body = self._request(
            "/api/community/report",
            token="test_token_creator",
            method="POST",
            body={
                "community_id": "comm_test",
                "target_type": "drop",
                "target_id": "drop_123",
                "reason": "Spam"
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        self.assertIn("Must be community, moment, or user", body["error"])

        # 3. Create a report on the fresh moment
        status, body = self._request(
            "/api/community/report",
            token="test_token_creator",
            method="POST",
            body={
                "community_id": "comm_test",
                "target_type": "moment",
                "target_id": fresh_post_id,
                "reason": "Inappropriate Content",
                "details": "Violates community standards"
            }
        )
        self.assertEqual(status, 201)
        report_id = body.get("report_id")
        self.assertTrue(report_id)

        # Verify report was persisted with pending status
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT target_type, target_id, status FROM community_reports WHERE id = ?", (report_id,))
        rep_row = cursor.fetchone()
        self.assertIsNotNone(rep_row)
        self.assertEqual(rep_row[0], "moment")
        self.assertEqual(rep_row[1], fresh_post_id)
        self.assertEqual(rep_row[2], "pending")
        conn.close()

        # 4. Execute moderation action 'hide' on the reported moment
        status, body = self._request(
            "/api/community/moderation/action",
            token="test_token_creator",
            method="POST",
            body={
                "report_id": report_id,
                "action": "hide",
                "reason": "Hiding flagged post"
            }
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

        # Verify side effects: post is hidden, report is actioned, audit logged
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT moderation_status FROM posts WHERE id = ?", (fresh_post_id,))
        post_row = cursor.fetchone()
        self.assertEqual(post_row[0], "hidden")

        cursor.execute("SELECT status, action_taken, reviewed_by FROM community_reports WHERE id = ?", (report_id,))
        rep_after = cursor.fetchone()
        self.assertEqual(rep_after[0], "actioned")
        self.assertEqual(rep_after[1], "hidden")
        self.assertEqual(rep_after[2], "u_creator")

        cursor.execute("SELECT action, target_type, target_id FROM moderation_audit_log WHERE community_id = ? ORDER BY rowid DESC LIMIT 1", ("comm_test",))
        audit_row = cursor.fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row[0], "hide")
        self.assertEqual(audit_row[1], "moment")
        self.assertEqual(audit_row[2], fresh_post_id)
        conn.close()

        # 5. Execute moderation action 'restore' and verify restorative side effect
        status, body = self._request(
            "/api/community/moderation/action",
            token="test_token_creator",
            method="POST",
            body={
                "report_id": report_id,
                "action": "restore",
                "reason": "Reinstating post"
            }
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT moderation_status, is_private FROM posts WHERE id = ?", (fresh_post_id,))
        restored_post = cursor.fetchone()
        self.assertEqual(restored_post[0], "active")
        self.assertEqual(restored_post[1], 0)

        cursor.execute("SELECT action_taken FROM community_reports WHERE id = ?", (report_id,))
        self.assertEqual(cursor.fetchone()[0], "restored")
        conn.close()

        # 6. Verify static code: no community_drops in report and moderation action routes
        with open(os.path.join(PROJECT_DIR, "server.py")) as f:
            code = f.read()
        report_start = code.find('if path == "/api/community/report":')
        mod_end = code.find('if path.startswith("/api/"):', report_start)
        mod_slice = code[report_start:mod_end]
        self.assertNotIn("community_drops", mod_slice)


if __name__ == "__main__":
    unittest.main()
