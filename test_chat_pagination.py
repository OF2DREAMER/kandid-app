#!/usr/bin/env python3
"""
Focused tests for CHAT PAGINATION (Bug 2).

Exercises the REAL `GET /api/chat/messages` handler in-process against a
disposable SQLite copy (server.DB_FILE redirected), so the production route,
its auth, conversation scoping, deletion-state filter and tombstone masking
are all under test — not a reimplementation.

Covers:
  A. initial page returns the latest `limit` (50) messages
  B. before_id returns the next older page
  C. ordering across pages: no duplicates, no skips, chronological
  D. has_more true while older remain, false at the end
  E. authorization: a before_id from another conversation is rejected (400)
  F. delete compatibility: deleted-for-me hidden, deleted-for-everyone masked
  I. repeated pagination 50 -> 100 -> ... until has_more is false

Read-only w.r.t. the real database (redirected to a temp file).
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
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402
from server import KandidHandler  # noqa: E402

TOTAL = 120
# Messages hidden from user A (deleted-for-me). The correct column depends on who
# sent them: A-sent -> sender_state, B-sent -> receiver_state.
DELETED_FOR_ME = {5, 8, 12, 33, 40, 74, 111}
DELETED_FOR_EVERYONE = {3, 60, 90}


def _created_at(i):
    # Groups of three consecutive messages share a timestamp, to prove the
    # (created_at DESC, id DESC) tie-break does not skip or duplicate rows.
    return "2026-01-01T00:00:%02d" % (i // 3)


def _msg_id(i):
    return "msg_%03d" % i


class ChatPaginationTest(unittest.TestCase):
    maxDiff = 400

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_chat_pg_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_chat_pg.db")
        server.init_db()

        conn = server.get_db()
        users = [
            ("u_a", "a@example.test", "user_a", "User A"),
            ("u_b", "b@example.test", "user_b", "User B"),
            ("u_c", "c@example.test", "user_c", "User C"),
        ]
        for uid, email, handle, name in users:
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, email, handle, name, "hash", "salt"),
            )
        conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
            ("s_a", "u_a", "token_a", "2999-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
            ("s_c", "u_c", "token_c", "2999-01-01T00:00:00"),
        )

        for i in range(TOTAL):
            sender = "u_a" if i % 2 == 0 else "u_b"
            receiver = "u_b" if sender == "u_a" else "u_a"
            sender_state = "active"
            receiver_state = "active"
            if i in DELETED_FOR_ME:
                if sender == "u_a":
                    sender_state = "in_trash"
                else:
                    receiver_state = "in_trash"
            conn.execute(
                """INSERT INTO messages
                   (id, sender_id, receiver_id, content, created_at, message_type,
                    media_url, sender_state, receiver_state, is_deleted_for_everyone)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_msg_id(i), sender, receiver, "hello %d" % i, _created_at(i),
                 "text", None, sender_state, receiver_state,
                 1 if i in DELETED_FOR_EVERYONE else 0),
            )
        # Message in a DIFFERENT conversation (A<->C) used as a cross-conversation cursor.
        conn.execute(
            """INSERT INTO messages
               (id, sender_id, receiver_id, content, created_at, message_type,
                media_url, sender_state, receiver_state, is_deleted_for_everyone)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("msg_other", "u_a", "u_c", "other convo", "2026-01-01T00:00:00",
             "text", None, "active", "active", 0),
        )
        conn.commit()
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), KandidHandler)
        cls.host, cls.port = "127.0.0.1", cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

        # Expected visible set (chronological) for user A talking to B.
        cls.expected = []
        for i in range(TOTAL):
            if i in DELETED_FOR_ME:
                continue
            cls.expected.append((_created_at(i), _msg_id(i)))
        cls.expected.sort(key=lambda t: (t[0], t[1]))
        cls.expected_ids = [mid for _, mid in cls.expected]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._orig_db
            server.DATABASE_URL = cls._orig_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _get(self, query, token="token_a"):
        req = urllib.request.Request(
            "http://%s:%d/api/chat/messages?%s" % (self.host, self.port, query),
            headers={"Authorization": "Bearer " + token},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    # ---- A. initial latest page ------------------------------------------
    def test_a_initial_page_is_latest_50(self):
        status, body = self._get("chat_id=u_b&limit=50")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        msgs = body["messages"]
        self.assertEqual(len(msgs), 50, "initial page must be 50 messages")
        expected_latest = self.expected_ids[-50:]
        self.assertEqual([m["id"] for m in msgs], expected_latest,
                         "latest page must be the newest 50, in chronological order")
        self.assertIs(body.get("has_more"), True)
        print("  PASS A: initial page = latest 50 in chronological order")

    # ---- B. before_id returns older page ---------------------------------
    def test_b_before_id_returns_older_page(self):
        _, first = self._get("chat_id=u_b&limit=50")
        oldest = first["messages"][0]["id"]
        status, older = self._get("chat_id=u_b&limit=50&before_id=" + oldest)
        self.assertEqual(status, 200)
        got = [m["id"] for m in older["messages"]]
        self.assertEqual(len(got), 50)
        # strictly older than the cursor, immediate predecessors
        self.assertNotIn(oldest, got)
        self.assertEqual(got, self.expected_ids[-100:-50])
        print("  PASS B: before_id returns the immediately older 50")

    # ---- C. ordering across pages: no dups / no skips --------------------
    def test_c_full_pagination_no_dup_no_skip(self):
        seen = []
        cursor = None
        while True:
            q = "chat_id=u_b&limit=50" + (("&before_id=" + cursor) if cursor else "")
            _, body = self._get(q)
            page = [m["id"] for m in body["messages"]]
            seen = page + seen  # pages arrive newest->older; build chronological
            if not body.get("has_more"):
                break
            cursor = page[0]  # oldest of this page (chronological head)
        self.assertEqual(len(seen), len(set(seen)), "no duplicate messages across pages")
        self.assertEqual(seen, self.expected_ids, "every message reached once, chronologically")
        print("  PASS C: pagination yields every message once, in order")

    # ---- D. has_more flips correctly -------------------------------------
    def test_d_has_more_true_then_false(self):
        _, p1 = self._get("chat_id=u_b&limit=50")
        self.assertTrue(p1["has_more"])
        _, p2 = self._get("chat_id=u_b&limit=50&before_id=" + p1["messages"][0]["id"])
        self.assertTrue(p2["has_more"])
        _, p3 = self._get("chat_id=u_b&limit=50&before_id=" + p2["messages"][0]["id"])
        self.assertFalse(p3["has_more"], "final page must report has_more=false")
        print("  PASS D: has_more true while older remain, false at the end")

    # ---- E. authorization: cross-conversation cursor rejected ------------
    def test_e_cross_conversation_cursor_rejected(self):
        # msg_other belongs to A<->C, not A<->B.
        status, body = self._get("chat_id=u_b&limit=50&before_id=msg_other")
        self.assertEqual(status, 400, "cursor from another conversation must be rejected")
        self.assertFalse(body.get("success"))
        print("  PASS E: cross-conversation before_id rejected with 400")

    def test_e2_unauthenticated_rejected(self):
        req = urllib.request.Request(
            "http://%s:%d/api/chat/messages?chat_id=u_b&limit=50" % (self.host, self.port))
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertEqual(status, 401)
        print("  PASS E2: unauthenticated request still 401")

    # ---- F. delete-state compatibility -----------------------------------
    def test_f_deleted_states_respected(self):
        all_msgs = {}
        cursor = None
        while True:
            q = "chat_id=u_b&limit=50" + (("&before_id=" + cursor) if cursor else "")
            _, body = self._get(q)
            for m in body["messages"]:
                all_msgs[m["id"]] = m
            if not body.get("has_more"):
                break
            cursor = body["messages"][0]["id"]

        for i in DELETED_FOR_ME:
            self.assertNotIn(_msg_id(i), all_msgs,
                             "message deleted-for-me must not reappear in older pages")
        for i in DELETED_FOR_EVERYONE:
            m = all_msgs.get(_msg_id(i))
            self.assertIsNotNone(m, "deleted-for-everyone must still appear as tombstone")
            self.assertEqual(m["content"], "Message deleted")
            self.assertEqual(m["message_type"], "deleted")
            self.assertIsNone(m["media_url"])
            self.assertIsNone(m["moment_id"])
            self.assertIsNone(m["reply_to_id"])
        print("  PASS F: deleted-for-me hidden; deleted-for-everyone masked as tombstone")

    # ---- I. repeated pagination to the end -------------------------------
    def test_i_repeated_pagination_50_100_150(self):
        _, p1 = self._get("chat_id=u_b&limit=50")
        _, p2 = self._get("chat_id=u_b&limit=50&before_id=" + p1["messages"][0]["id"])
        _, p3 = self._get("chat_id=u_b&limit=50&before_id=" + p2["messages"][0]["id"])
        self.assertEqual(len(p1["messages"]), 50)
        self.assertEqual(len(p2["messages"]), 50)
        self.assertEqual(len(p3["messages"]), len(self.expected) - 100)
        merged = p3["messages"] + p2["messages"] + p1["messages"]
        self.assertEqual([m["id"] for m in merged], self.expected_ids)
        print("  PASS I: 50 -> 100 -> %d until has_more=false" % len(self.expected))


if __name__ == "__main__":
    print("\n=== CHAT PAGINATION TESTS ===")
    unittest.main(verbosity=0)
