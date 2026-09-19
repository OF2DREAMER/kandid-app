#!/usr/bin/env python3
"""
Focused regression test for P0-1 chat bandwidth.

Verifies:
  1. GET /api/chat/messages returns at most the newest 50 messages.
  2. The returned window is chronological and only the oldest history drops.
  3. The response keeps the JSON shape app.js expects (message fields plus
     reply_to / moment / reactions).
  4. Blocked conversations still return 403 and never leak messages.
  5. app.js no longer refetches the open conversation from the 3s heartbeat
     poller (the 2.5s chat sync poller owns that job).

Runs against a throwaway SQLite database; data/kandid.db is never touched.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402

APP_JS = os.path.join(PROJECT_DIR, "app.js")

TOTAL_MESSAGES = 120
EXPECTED_CAP = 50

MESSAGE_KEYS = {
    "id", "sender_id", "receiver_id", "content", "created_at", "read_at",
    "message_type", "moment_id", "media_url", "reply_to_id",
    "reply_to", "moment", "reactions",
}


class ChatBandwidthP0Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_p0_1_")
        cls._original_db_file = server.DB_FILE
        cls._original_database_url = server.DATABASE_URL

        # Force a disposable SQLite database for this test run.
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_p0_1.db")
        server.init_db()

        cls.token = "p0_1_test_token"
        cls.user_a = "u_p0_1_a"
        cls.user_b = "u_p0_1_b"
        cls.ids = ["m_p0_1_%03d" % i for i in range(1, TOTAL_MESSAGES + 1)]

        conn = server.get_db()
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.user_a, "p0_1_a@example.test", "p0_1_a", "Alpha", "hash", "salt"),
        )
        conn.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.user_b, "p0_1_b@example.test", "p0_1_b", "Beta", "hash", "salt"),
        )
        conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
            ("s_p0_1_test", cls.user_a, cls.token, (datetime.now() + timedelta(days=1)).isoformat()),
        )
        base = datetime(2026, 1, 1, 12, 0, 0)
        for i, mid in enumerate(cls.ids):
            sender, receiver = (cls.user_a, cls.user_b) if i % 2 == 0 else (cls.user_b, cls.user_a)
            conn.execute(
                "INSERT INTO messages (id, sender_id, receiver_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (mid, sender, receiver, "seeded message %d" % (i + 1), (base + timedelta(seconds=i)).isoformat()),
            )
        conn.commit()
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._original_db_file
            server.DATABASE_URL = cls._original_database_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get_messages(self):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/chat/messages?chat_id=%s" % (self.port, self.user_b),
            headers={"Authorization": "Bearer %s" % self.token},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")), raw

    def test_01_polling_duplication_removed_from_app_js(self):
        with open(APP_JS, encoding="utf-8") as fh:
            src = fh.read()

        self.assertNotIn(
            "state.activeScreen === 'chat'", src,
            "dead 'chat' screen branch must not be reintroduced",
        )

        hb_start = src.find("// 5b. Real-time Heartbeat, Notification, & Presence Poller")
        self.assertNotEqual(hb_start, -1, "heartbeat poller marker missing")
        hb_end = src.find("}, 3000);", hb_start)
        self.assertNotEqual(hb_end, -1, "3s heartbeat interval end missing")
        heartbeat_block = src[hb_start:hb_end]
        self.assertNotIn(
            "loadChatMessages", heartbeat_block,
            "3s heartbeat poller must not refetch the open conversation",
        )

        sync_start = src.find("window.chatSyncGlobalInterval = setInterval(function() {")
        self.assertNotEqual(sync_start, -1, "2.5s chat sync poller missing")
        sync_end = src.find("}, 2500);", sync_start)
        sync_block = src[sync_start:sync_end]
        self.assertIn(
            "loadChatMessages(state.activeChatUser, true)", sync_block,
            "2.5s poller must keep refreshing the open conversation",
        )
        self.assertEqual(src.count("state.activeScreen === 'chat-home'"), 1)

    def test_02_endpoint_caps_history_to_newest_50(self):
        status, payload, raw = self._get_messages()
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_chat_id"], self.user_b)

        msgs = payload["messages"]
        self.assertEqual(len(msgs), EXPECTED_CAP, "must return at most 50 messages")

        # Only the oldest history is dropped.
        self.assertEqual(msgs[0]["id"], self.ids[TOTAL_MESSAGES - EXPECTED_CAP])
        self.assertEqual(msgs[-1]["id"], self.ids[-1])

        # Chronological order must survive the newest-N query + reverse.
        stamps = [m["created_at"] for m in msgs]
        self.assertEqual(stamps, sorted(stamps), "returned messages must be chronological")
        returned = [m["id"] for m in msgs]
        self.assertEqual(returned, sorted(returned))

        # Bounded payload (bounded well below the unbounded conversation size).
        projected_full = int(len(raw) / EXPECTED_CAP * TOTAL_MESSAGES)
        self.assertLess(len(raw), 40 * 1024, "50-message payload must stay small")
        print("  ℹ️  50-message payload = %d bytes (120-message payload would be ~%d bytes)"
              % (len(raw), projected_full))

    def test_03_response_shape_is_unchanged(self):
        _, payload, _ = self._get_messages()
        for m in payload["messages"]:
            missing = MESSAGE_KEYS - set(m.keys())
            self.assertFalse(missing, "message missing keys: %s" % sorted(missing))
            self.assertIsNone(m["reply_to"])
            self.assertIsNone(m["moment"])
            self.assertIsInstance(m["reactions"], list)

    def test_04_blocked_conversation_still_returns_403(self):
        conn = server.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
            ("b_p0_1_test", self.user_a, self.user_b),
        )
        conn.commit()
        conn.close()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get_messages()
            self.assertEqual(ctx.exception.code, 403)
            body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertFalse(body["success"])
            self.assertEqual(body["messages"], [])
        finally:
            conn = server.get_db()
            conn.execute("DELETE FROM blocks WHERE id = ?", ("b_p0_1_test",))
            conn.commit()
            conn.close()

        # Unblocking restores normal access.
        status, payload, _ = self._get_messages()
        self.assertEqual(status, 200)
        self.assertTrue(payload["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
