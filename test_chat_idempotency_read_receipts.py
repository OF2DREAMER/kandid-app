#!/usr/bin/env python3
"""
Focused tests for the chat reliability upgrade.

Covers the real HTTP handlers against a disposable SQLite database:
  - messages.random_id migration and indexes
  - client-assigned idempotency (sequential retry, concurrent retry)
  - deduplication before the non-connected 3-message allowance
  - random_id conflicts across conversations
  - existing block and 3-message protections
  - GET /api/chat/messages no longer marks messages read
  - POST /api/chat/read scoping and cursor validation

The real data/kandid.db is never opened by this test.
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
from server import KandidHandler  # noqa: E402


def _iso(seconds):
    return (datetime(2026, 2, 1, 10, 0, 0) + timedelta(seconds=seconds)).isoformat()


class ChatIdempotencyReadReceiptTest(unittest.TestCase):
    maxDiff = 500

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_chat_idem_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_chat_idem.db")
        server.init_db()

        cls.users = {
            "u_idem_a": "token_idem_a",
            "u_idem_b": "token_idem_b",
            "u_idem_c": "token_idem_c",
            "u_lim_a": "token_lim_a",
            "u_lim_b": "token_lim_b",
            "u_con_a": "token_con_a",
            "u_con_b": "token_con_b",
            "u_read_a": "token_read_a",
            "u_read_b": "token_read_b",
            "u_read_c": "token_read_c",
            "u_legacy_a": "token_legacy_a",
            "u_legacy_b": "token_legacy_b",
        }
        conn = server.get_db()
        for uid, token in cls.users.items():
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, uid + "@example.test", uid, uid, "hash", "salt"),
            )
            conn.execute(
                "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                ("s_" + uid, uid, token, "2999-01-01T00:00:00"),
            )

        # Read-receipt fixture: five inbound, one outbound.
        for i in range(1, 6):
            sender = "u_read_b"
            receiver = "u_read_a"
            conn.execute(
                """INSERT INTO messages
                   (id, sender_id, receiver_id, content, created_at, message_type,
                    sender_state, receiver_state, is_deleted_for_everyone)
                   VALUES (?, ?, ?, ?, ?, 'text', 'active', 'active', 0)""",
                ("m_read_%d" % i, sender, receiver, "inbound %d" % i, _iso(i)),
            )
        conn.execute(
            """INSERT INTO messages
               (id, sender_id, receiver_id, content, created_at, message_type,
                sender_state, receiver_state, is_deleted_for_everyone)
               VALUES (?, ?, ?, ?, ?, 'text', 'active', 'active', 0)""",
            ("m_read_out", "u_read_a", "u_read_b", "outbound", _iso(6)),
        )
        # Cross-conversation cursor source.
        conn.execute(
            """INSERT INTO messages
               (id, sender_id, receiver_id, content, created_at, message_type,
                sender_state, receiver_state, is_deleted_for_everyone)
               VALUES (?, ?, ?, ?, ?, 'text', 'active', 'active', 0)""",
            ("m_read_other", "u_read_c", "u_read_a", "other", _iso(7)),
        )
        conn.commit()
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), KandidHandler)
        cls.host, cls.port = "127.0.0.1", cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._orig_db
            server.DATABASE_URL = cls._orig_url
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, method, path, payload=None, token=None):
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(
            "http://%s:%d%s" % (self.host, self.port, path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _send(self, sender, receiver, random_id, content="hello"):
        return self._request(
            "POST",
            "/api/chat/send",
            {
                "receiver_id": receiver,
                "content": content,
                "message_type": "text",
                "random_id": random_id,
            },
            self.users[sender],
        )

    def _count(self, where, params):
        conn = server.get_db()
        try:
            row = conn.execute("SELECT COUNT(*) FROM messages WHERE " + where, params).fetchone()
            return row[0]
        finally:
            conn.close()

    # ---- schema ---------------------------------------------------------
    def test_01_random_id_column_and_indexes_exist(self):
        conn = server.get_db()
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
            indexes = {r[1] for r in conn.execute("PRAGMA index_list(messages)").fetchall()}
        finally:
            conn.close()
        self.assertIn("random_id", cols)
        self.assertIn("idx_messages_random_id", indexes)
        self.assertIn("idx_messages_sender_random_id", indexes)
        print("  PASS 1: random_id column and both indexes exist")

    # ---- sequential idempotency ----------------------------------------
    def test_02_retry_returns_original_without_duplicate(self):
        status, first = self._send("u_idem_a", "u_idem_b", "msg_rand_seq_001", "one")
        self.assertEqual(status, 201, first)
        self.assertTrue(first["success"])
        first_id = first["message"]["id"]

        status, second = self._send("u_idem_a", "u_idem_b", "msg_rand_seq_001", "one")
        self.assertEqual(status, 200, second)
        self.assertTrue(second["success"])
        self.assertTrue(second.get("deduplicated"))
        self.assertEqual(second["message"]["id"], first_id)
        self.assertEqual(
            self._count("sender_id = ? AND receiver_id = ? AND random_id = ?",
                        ("u_idem_a", "u_idem_b", "msg_rand_seq_001")),
            1,
        )
        print("  PASS 2: sequential retry returns the original row and writes once")

    # ---- legacy clients -------------------------------------------------
    def test_02b_legacy_send_without_random_id_is_not_deduplicated(self):
        first = self._request(
            "POST", "/api/chat/send",
            {"receiver_id": "u_legacy_b", "content": "one", "message_type": "text"},
            self.users["u_legacy_a"],
        )
        self.assertEqual(first[0], 201, first)
        second = self._request(
            "POST", "/api/chat/send",
            {"receiver_id": "u_legacy_b", "content": "two", "message_type": "text"},
            self.users["u_legacy_a"],
        )
        self.assertEqual(second[0], 201, second)
        self.assertEqual(
            self._count("sender_id = ? AND receiver_id = ? AND random_id IS NULL",
                        ("u_legacy_a", "u_legacy_b")),
            2,
        )
        print("  PASS 2b: legacy sends without random_id remain distinct (NULL key)")

    # ---- cross-conversation conflict -----------------------------------
    def test_03_same_random_id_cannot_target_another_receiver(self):
        status, first = self._send("u_idem_a", "u_idem_b", "msg_rand_conflict_1", "one")
        self.assertEqual(status, 201, first)
        status, second = self._send("u_idem_a", "u_idem_c", "msg_rand_conflict_1", "one")
        self.assertEqual(status, 409, second)
        self.assertEqual(second.get("code"), "RANDOM_ID_CONFLICT")
        self.assertEqual(
            self._count("sender_id = ? AND random_id = ?", ("u_idem_a", "msg_rand_conflict_1")),
            1,
        )
        print("  PASS 3: random_id reuse across a different conversation is rejected")

    # ---- 3-message limit + retry ordering -------------------------------
    def test_04_dedup_runs_before_non_connected_limit(self):
        for i in range(3):
            status, body = self._send("u_lim_a", "u_lim_b", "msg_rand_lim_%03d" % i, "limit %d" % i)
            self.assertEqual(status, 201, body)

        status, body = self._send("u_lim_a", "u_lim_b", "msg_rand_lim_999", "fourth")
        self.assertEqual(status, 403, body)
        self.assertEqual(body.get("code"), "NON_CONNECTION_MESSAGE_LIMIT")

        # Retrying an already-persisted message must succeed despite the limit.
        status, body = self._send("u_lim_a", "u_lim_b", "msg_rand_lim_002", "limit 2")
        self.assertEqual(status, 200, body)
        self.assertTrue(body.get("deduplicated"))
        self.assertEqual(
            self._count("sender_id = ? AND receiver_id = ?", ("u_lim_a", "u_lim_b")),
            3,
        )
        print("  PASS 4: 3-message limit still blocks new sends; retry of sent #3 succeeds")

    # ---- concurrent idempotency ----------------------------------------
    def test_05_concurrent_duplicate_requests_create_one_row(self):
        barrier = threading.Barrier(2)
        results = []

        def worker():
            barrier.wait()
            results.append(self._send("u_con_a", "u_con_b", "msg_rand_concurrent_1", "race"))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=25)
        self.assertEqual(len(results), 2, results)
        self.assertTrue(all(r[0] in (200, 201) for r in results), results)
        self.assertTrue(any(r[1].get("deduplicated") for r in results), results)
        self.assertEqual(
            self._count("sender_id = ? AND receiver_id = ? AND random_id = ?",
                        ("u_con_a", "u_con_b", "msg_rand_concurrent_1")),
            1,
        )
        print("  PASS 5: two concurrent retries produce exactly one message row")

    # ---- invalid key ----------------------------------------------------
    def test_06_invalid_random_id_rejected(self):
        status, body = self._send("u_idem_a", "u_idem_b", "bad id with spaces", "x")
        self.assertEqual(status, 400, body)
        self.assertFalse(body.get("success"))
        print("  PASS 6: malformed random_id is rejected")

    # ---- block protection ----------------------------------------------
    def test_07_block_still_prevents_send(self):
        conn = server.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
            ("b_idem_test", "u_idem_b", "u_idem_a"),
        )
        conn.commit()
        conn.close()
        try:
            status, body = self._send("u_idem_a", "u_idem_b", "msg_rand_block_1", "blocked")
            self.assertEqual(status, 403, body)
        finally:
            conn = server.get_db()
            conn.execute("DELETE FROM blocks WHERE id = ?", ("b_idem_test",))
            conn.commit()
            conn.close()
        print("  PASS 7: block relationship still rejects the send")

    # ---- read receipts: GET is read-only --------------------------------
    def test_08_get_messages_does_not_mark_read(self):
        status, body = self._request(
            "GET", "/api/chat/messages?chat_id=u_read_b&limit=50", token="token_read_a"
        )
        self.assertEqual(status, 200, body)
        inbound = [m for m in body["messages"] if m["sender_id"] == "u_read_b"]
        self.assertEqual(len(inbound), 5)
        self.assertTrue(all(m["read_at"] is None for m in inbound))

        conn = server.get_db()
        try:
            unread = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE sender_id = ? AND receiver_id = ? AND read_at IS NULL",
                ("u_read_b", "u_read_a"),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(unread, 5)
        print("  PASS 8: GET history leaves all inbound messages unread")

    def test_09_read_endpoint_marks_only_up_to_cursor(self):
        status, body = self._request(
            "POST",
            "/api/chat/read",
            {"partner_id": "u_read_b", "max_message_id": "m_read_3"},
            "token_read_a",
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["success"])
        self.assertEqual(body["updated"], 3)

        conn = server.get_db()
        try:
            rows = conn.execute(
                "SELECT id, read_at FROM messages WHERE sender_id = ? AND receiver_id = ? ORDER BY id",
                ("u_read_b", "u_read_a"),
            ).fetchall()
        finally:
            conn.close()
        flags = {r["id"]: bool(r["read_at"]) for r in rows}
        self.assertTrue(flags["m_read_1"] and flags["m_read_2"] and flags["m_read_3"])
        self.assertFalse(flags["m_read_4"] or flags["m_read_5"])

        # A later GET must not advance the cursor.
        status, body = self._request(
            "GET", "/api/chat/messages?chat_id=u_read_b&limit=50", token="token_read_a"
        )
        self.assertEqual(status, 200, body)
        by_id = {m["id"]: m for m in body["messages"]}
        self.assertFalse(by_id["m_read_4"]["read_at"])
        self.assertFalse(by_id["m_read_5"]["read_at"])
        print("  PASS 9: read cursor marks only messages up to max_message_id")

    def test_10_read_endpoint_rejects_foreign_cursor(self):
        status, body = self._request(
            "POST",
            "/api/chat/read",
            {"partner_id": "u_read_b", "max_message_id": "m_read_other"},
            "token_read_a",
        )
        self.assertEqual(status, 400, body)
        self.assertFalse(body.get("success"))
        print("  PASS 10: read cursor from another conversation is rejected")

    def test_11_read_endpoint_requires_auth_and_blocks(self):
        status, body = self._request(
            "POST", "/api/chat/read", {"partner_id": "u_read_b", "max_message_id": "m_read_4"}
        )
        self.assertEqual(status, 401, body)

        conn = server.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO blocks (id, user_id, blocked_user_id) VALUES (?, ?, ?)",
            ("b_read_test", "u_read_a", "u_read_b"),
        )
        conn.commit()
        conn.close()
        try:
            status, body = self._request(
                "POST",
                "/api/chat/read",
                {"partner_id": "u_read_b", "max_message_id": "m_read_4"},
                "token_read_a",
            )
            self.assertEqual(status, 403, body)
        finally:
            conn = server.get_db()
            conn.execute("DELETE FROM blocks WHERE id = ?", ("b_read_test",))
            conn.commit()
            conn.close()
        print("  PASS 11: read endpoint requires auth and respects blocks")


if __name__ == "__main__":
    unittest.main(verbosity=2)
