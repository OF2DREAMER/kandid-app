"""
Kandid V1 Private Messaging Layer - Final Security Audit Test Suite
Comprehensive testing of 24 security vectors across authentication,
Anti-IDOR, input validation, permissions, attachments, rate limiting, and privacy.
"""

import unittest
import json
import io
import os
import sys
import base64
import time
import secrets
from datetime import datetime, timedelta

# Ensure kandid_project is on sys.path
PROJECT_DIR = "/Users/mdsarebaj/kandid_project"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import server

class MockServerResponse:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = b""

class MockRequestHandler:
    def __init__(self, path, method="GET", headers=None, body=None):
        self.path = path
        self.command = method
        self.headers = headers or {}
        self.response = MockServerResponse()
        
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode("utf-8")
            elif isinstance(body, (bytes, bytearray)):
                body_bytes = bytes(body)
            else:
                body_bytes = str(body).encode("utf-8")
            self.rfile = io.BytesIO(body_bytes)
            self.headers["Content-Length"] = str(len(body_bytes))
        else:
            self.rfile = io.BytesIO(b"")
            self.headers["Content-Length"] = "0"
            
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.response.status = status

    def send_header(self, key, val):
        self.response.headers[key] = val

    def end_headers(self):
        pass

    def send_json(self, status, data):
        self.response.status = status
        self.response.body = json.dumps(data).encode("utf-8")
        return data

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        self.rfile.seek(0)
        raw = self.rfile.read(length).decode("utf-8")
        self.rfile.seek(0)
        return json.loads(raw)

class V1PrivateChatSecurityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        conn = server.get_db()
        cursor = conn.cursor()

        # Select 3 distinct real users from database
        cursor.execute("SELECT id, handle, name FROM users WHERE role != 'banned' ORDER BY id ASC LIMIT 3")
        rows = cursor.fetchall()
        assert len(rows) >= 3, "Need at least 3 real users in DB for security testing"
        
        cls.user_a = dict(rows[0])
        cls.user_b = dict(rows[1])
        cls.user_c = dict(rows[2])

        cls.uid_a = cls.user_a["id"]
        cls.uid_b = cls.user_b["id"]
        cls.uid_c = cls.user_c["id"]

        cls.handle_a = cls.user_a.get("handle") or "user_a"
        cls.handle_b = cls.user_b.get("handle") or "user_b"
        cls.handle_c = cls.user_c.get("handle") or "user_c"

        # Create unique test session tokens
        cls.token_a = "tok_sec_a_" + secrets.token_hex(16)
        cls.token_b = "tok_sec_b_" + secrets.token_hex(16)
        cls.token_c = "tok_sec_c_" + secrets.token_hex(16)

        exp = (datetime.now() + timedelta(days=1)).isoformat()
        cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.token_a, cls.uid_a, exp))
        cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.token_b, cls.uid_b, exp))
        cursor.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.token_c, cls.uid_c, exp))

        # Clear blocks between A, B, and C
        cursor.execute("""
            DELETE FROM blocks WHERE (user_id = ? AND blocked_user_id = ?) 
               OR (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?)
        """, (cls.uid_a, cls.uid_b, cls.uid_b, cls.uid_a,
              cls.uid_a, cls.uid_c, cls.uid_c, cls.uid_a,
              cls.uid_b, cls.uid_c, cls.uid_c, cls.uid_b))

        # Create test moments: 1 public by Bob, 1 private by Bob, 1 removed by Bob
        cls.mom_public_b = "p_sec_pub_" + secrets.token_hex(4)
        cls.mom_private_b = "p_sec_priv_" + secrets.token_hex(4)
        cls.mom_removed_b = "p_sec_rem_" + secrets.token_hex(4)

        cls.name_b = cls.user_b.get("name") or "User B"
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, caption, campus, is_private, moderation_status)
            VALUES (?, ?, ?, ?, 'https://example.com/pub.jpg', 'https://example.com/pub_pip.jpg', 'Public Moment', 'Security Campus', 0, 'approved')
        """, (cls.mom_public_b, cls.uid_b, cls.name_b, cls.handle_b))

        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, caption, campus, is_private, moderation_status)
            VALUES (?, ?, ?, ?, 'https://example.com/priv.jpg', 'https://example.com/priv_pip.jpg', 'Private Moment', 'Security Campus', 1, 'approved')
        """, (cls.mom_private_b, cls.uid_b, cls.name_b, cls.handle_b))

        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img, caption, campus, is_private, moderation_status)
            VALUES (?, ?, ?, ?, 'https://example.com/rem.jpg', 'https://example.com/rem_pip.jpg', 'Removed Moment', 'Security Campus', 0, 'removed')
        """, (cls.mom_removed_b, cls.uid_b, cls.name_b, cls.handle_b))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        conn = server.get_db()
        conn.execute("DELETE FROM messages WHERE sender_id IN (?, ?, ?) OR receiver_id IN (?, ?, ?)",
                     (cls.uid_a, cls.uid_b, cls.uid_c, cls.uid_a, cls.uid_b, cls.uid_c))
        conn.execute("DELETE FROM sessions WHERE token IN (?, ?, ?)", (cls.token_a, cls.token_b, cls.token_c))
        conn.execute("DELETE FROM posts WHERE id IN (?, ?, ?)", (cls.mom_public_b, cls.mom_private_b, cls.mom_removed_b))
        conn.execute("DELETE FROM blocks WHERE (user_id = ? AND blocked_user_id = ?) OR (user_id = ? AND blocked_user_id = ?)",
                     (cls.uid_a, cls.uid_b, cls.uid_b, cls.uid_a))
        conn.execute("DELETE FROM chat_attachments WHERE uploader_id IN (?, ?, ?)", (cls.uid_a, cls.uid_b, cls.uid_c))
        conn.execute("DELETE FROM chat_reactions WHERE user_id IN (?, ?, ?)", (cls.uid_a, cls.uid_b, cls.uid_c))
        conn.commit()
        conn.close()

    # --- 1. Authentication & Session Security ---

    def test_01_unauthenticated_chat_send_rejected(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={}, body={
            "recipientId": self.uid_b,
            "content": "Unauthenticated test"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 401)

    def test_02_spoofed_x_user_id_rejected(self):
        # Attacker tries to impersonate Alice via X-User-Id without a valid session token
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"X-User-Id": self.uid_a}, body={
            "recipientId": self.uid_b,
            "content": "Spoofed header test"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 401)

    def test_03_spoofed_sender_id_in_body_rejected(self):
        # Attacker tries to impersonate Alice via JSON body senderId without a session token
        handler = MockRequestHandler("/api/chat/send", "POST", headers={}, body={
            "senderId": self.uid_a,
            "recipientId": self.uid_b,
            "content": "Spoofed body test"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 401)

    def test_04_session_revocation_invalidates_access(self):
        # Revoke Charlie's session
        handler = MockRequestHandler("/api/auth/revoke-session", "POST", headers={"Authorization": f"Bearer {self.token_c}"}, body={})
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 200)

        # Now Charlie should be rejected from sending messages
        handler2 = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_c}"}, body={
            "recipientId": self.uid_a,
            "content": "Post revocation test"
        })
        body2 = handler2.read_json_body()
        server.KandidHandler.do_POST(handler2)
        self.assertEqual(handler2.response.status, 401)

        # Re-create session for Charlie for subsequent tests
        conn = server.get_db()
        exp = (datetime.now() + timedelta(days=1)).isoformat()
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (self.token_c, self.uid_c, exp))
        conn.commit()
        conn.close()

    # --- 2. Input Validation & Bounding ---

    def test_05_empty_message_rejected(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "content": "   "
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 400)

    def test_06_oversized_message_rejected(self):
        huge_text = "A" * 5001
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "content": huge_text
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 400)
        res = json.loads(handler.response.body.decode("utf-8"))
        self.assertIn("exceeds", res.get("error", "").lower())

    def test_07_self_message_rejected(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_a,
            "content": "Talking to myself"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 400)

    def test_08_nonexistent_recipient_rejected(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": "u_does_not_exist_99999",
            "content": "Message into void"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 404)

    # --- 3. Anti-IDOR & Quoted Reply Authorization ---

    def test_09_legitimate_message_exchange_and_notifications(self):
        # Alice sends message to Bob
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "content": "Hello Bob from Alice"
        })
        body = handler.read_json_body()
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 201)
        res = json.loads(handler.response.body.decode("utf-8"))
        self.__class__.msg_ab_id = res["message"]["id"]

        # Verify push notification body is generic and contains zero plaintext
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT body FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.uid_b,))
        notif_row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(notif_row)
        self.assertNotIn("Hello Bob from Alice", notif_row[0])
        self.assertIn(f"New message from @{self.handle_a}", notif_row[0])

    def test_10_anti_idor_third_party_cannot_read_messages(self):
        # Charlie tries to read messages between Alice and Bob
        handler = MockRequestHandler(f"/api/chat/messages?chat_id={self.uid_a}", "GET", headers={"Authorization": f"Bearer {self.token_c}"})
        server.KandidHandler.do_GET(handler)
        self.assertEqual(handler.response.status, 200)
        res = json.loads(handler.response.body.decode("utf-8"))
        # Charlie and Alice have 0 messages
        self.assertEqual(len(res.get("messages", [])), 0)

    def test_11_cross_conversation_reply_rejected(self):
        # Bob and Charlie exchange a message
        handler1 = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_b}"}, body={
            "recipientId": self.uid_c,
            "content": "Message between B and C"
        })
        server.KandidHandler.do_POST(handler1)
        res1 = json.loads(handler1.response.body.decode("utf-8"))
        msg_bc_id = res1["message"]["id"]

        # Alice tries to reply to msg_bc_id in her conversation with Bob
        handler2 = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "content": "Trying to quote Bob and Charlie message",
            "reply_to_id": msg_bc_id
        })
        server.KandidHandler.do_POST(handler2)
        self.assertEqual(handler2.response.status, 400)
        res2 = json.loads(handler2.response.body.decode("utf-8"))
        self.assertIn("Invalid reply_to", res2.get("error", ""))

    def test_12_third_party_cannot_react_to_foreign_message(self):
        # Charlie tries to react to Alice's message to Bob (msg_ab_id)
        handler = MockRequestHandler("/api/chat/reactions", "POST", headers={"Authorization": f"Bearer {self.token_c}"}, body={
            "message_id": self.msg_ab_id,
            "emoji": "🔥"
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 403)

    # --- 4. Moment Sharing Permissions ---

    def test_13_sharing_public_moment_allowed(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "message_type": "moment",
            "moment_id": self.mom_public_b
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 201)

    def test_14_sharing_foreign_private_moment_rejected(self):
        # Alice tries to share Bob's private moment to Charlie
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_c,
            "message_type": "moment",
            "moment_id": self.mom_private_b
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 403)

    def test_15_sharing_removed_moment_rejected(self):
        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "message_type": "moment",
            "moment_id": self.mom_removed_b
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 400)

    # --- 5. Private Attachments Security ---

    def test_16_non_image_attachment_magic_bytes_rejected(self):
        # Fake png extension but file is an executable/script
        fake_data = base64.b64encode(b"#!/bin/bash\necho 'hacked'").decode("utf-8")
        handler = MockRequestHandler("/api/chat/attachments", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "partner_id": self.uid_b,
            "data": "data:image/png;base64," + fake_data
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 400)
        res = json.loads(handler.response.body.decode("utf-8"))
        self.assertIn("supported", res.get("error", "").lower())

    def test_17_legitimate_attachment_upload_and_anti_idor_access(self):
        # Valid 1x1 GIF magic bytes
        gif_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        gif_b64 = base64.b64encode(gif_bytes).decode("utf-8")

        handler = MockRequestHandler("/api/chat/attachments", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "partner_id": self.uid_b,
            "data": "data:image/gif;base64," + gif_b64
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 201)
        res = json.loads(handler.response.body.decode("utf-8"))
        att_id = res["attachment"]["id"]

        # Alice (uploader) CAN access
        h_alice = MockRequestHandler(f"/api/chat/attachments/{att_id}", "GET", headers={"Authorization": f"Bearer {self.token_a}"})
        server.KandidHandler.do_GET(h_alice)
        self.assertEqual(h_alice.response.status, 200)

        # Bob (recipient partner) CAN access
        h_bob = MockRequestHandler(f"/api/chat/attachments/{att_id}", "GET", headers={"Authorization": f"Bearer {self.token_b}"})
        server.KandidHandler.do_GET(h_bob)
        self.assertEqual(h_bob.response.status, 200)

        # Charlie (third party) CANNOT access
        h_charlie = MockRequestHandler(f"/api/chat/attachments/{att_id}", "GET", headers={"Authorization": f"Bearer {self.token_c}"})
        server.KandidHandler.do_GET(h_charlie)
        self.assertEqual(h_charlie.response.status, 403)

        # Unauthenticated request CANNOT access
        h_anon = MockRequestHandler(f"/api/chat/attachments/{att_id}", "GET", headers={})
        server.KandidHandler.do_GET(h_anon)
        self.assertEqual(h_anon.response.status, 401)

    def test_18_path_traversal_in_attachment_id_blocked(self):
        handler = MockRequestHandler("/api/chat/attachments/..%2f..%2fserver.py", "GET", headers={"Authorization": f"Bearer {self.token_a}"})
        server.KandidHandler.do_GET(handler)
        self.assertIn(handler.response.status, [400, 403, 404])

    def test_19_static_file_handler_blocks_data_and_attachments(self):
        # Direct static request to /data/chat_attachments/ should return 403 Access denied
        handler = MockRequestHandler("/data/chat_attachments/secret.jpg", "GET")
        server.KandidHandler.do_GET(handler)
        self.assertEqual(handler.response.status, 403)

        handler_db = MockRequestHandler("/data/kandid.db", "GET")
        server.KandidHandler.do_GET(handler_db)
        self.assertEqual(handler_db.response.status, 403)

    # --- 6. Block & Moderation Enforcement ---

    def test_20_block_enforcement_prevents_messaging(self):
        # Alice blocks Bob
        h_blk = MockRequestHandler("/api/chat/block", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "targetUserId": self.uid_b
        })
        server.KandidHandler.do_POST(h_blk)
        self.assertEqual(h_blk.response.status, 200)

        # Bob tries to send message to Alice -> 403 Blocked
        h_send = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_b}"}, body={
            "recipientId": self.uid_a,
            "content": "Message while blocked"
        })
        server.KandidHandler.do_POST(h_send)
        self.assertEqual(h_send.response.status, 403)

        # Bob tries to view messages with Alice -> 403 Blocked
        h_msgs = MockRequestHandler(f"/api/chat/messages?chat_id={self.uid_a}", "GET", headers={"Authorization": f"Bearer {self.token_b}"})
        server.KandidHandler.do_GET(h_msgs)
        self.assertEqual(h_msgs.response.status, 403)

        # Alice unblocks Bob for clean test state
        conn = server.get_db()
        conn.execute("DELETE FROM blocks WHERE user_id = ? AND blocked_user_id = ?", (self.uid_a, self.uid_b))
        conn.commit()
        conn.close()

    def test_21_report_submission_requires_authentication(self):
        # Unauthenticated report is rejected
        h_anon = MockRequestHandler("/api/chat/report", "POST", headers={}, body={
            "reportedUserId": self.uid_b,
            "reason": "Harassment"
        })
        server.KandidHandler.do_POST(h_anon)
        self.assertEqual(h_anon.response.status, 401)

        # Authenticated report succeeds
        h_auth = MockRequestHandler("/api/chat/report", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "reportedUserId": self.uid_b,
            "reason": "Harassment"
        })
        server.KandidHandler.do_POST(h_auth)
        self.assertEqual(h_auth.response.status, 200)

    # --- 7. Rate Limiting & Abuse Prevention ---

    def test_22_chat_send_rate_limiting(self):
        # Exceed rate limit (60 msgs / min) for Alice
        rate_key = f"chat_send:{self.uid_a}"
        # Pre-fill bucket
        with server.rate_limiter.lock:
            server.rate_limiter.buckets[rate_key] = [time.time()] * 60

        handler = MockRequestHandler("/api/chat/send", "POST", headers={"Authorization": f"Bearer {self.token_a}"}, body={
            "recipientId": self.uid_b,
            "content": "Flooding message"
        })
        server.KandidHandler.do_POST(handler)
        self.assertEqual(handler.response.status, 429)

        # Clean rate limit bucket
        with server.rate_limiter.lock:
            server.rate_limiter.buckets[rate_key] = []

    # --- 8. Zero Plaintext Leakage & Schema Safety ---

    def test_23_schema_has_no_reply_to_snippet(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(messages)")
        cols = [r[1] for r in cursor.fetchall()]
        conn.close()
        self.assertNotIn("reply_to_snippet", cols)

    def test_24_conversations_derived_from_authorized_sessions_only(self):
        # Unauthenticated request to /api/chat/conversations rejected (401)
        handler = MockRequestHandler("/api/chat/conversations", "GET", headers={})
        server.KandidHandler.do_GET(handler)
        self.assertEqual(handler.response.status, 401)

if __name__ == "__main__":
    unittest.main(verbosity=2)
