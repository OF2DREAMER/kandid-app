#!/usr/bin/env python3
"""
Unit and integration tests for chat-photo attachment URL validation and access control.

Tests:
  1. Unit tests for is_safe_chat_media_url predicate
  2. Integration tests for POST /api/chat/send media_url validation
  3. Upload -> send -> authorized retrieval lifecycle
  4. Unauthorized / non-participant attachment access rejection
"""

import base64
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

import server
from server import KandidHandler, is_safe_chat_media_url, init_db, hash_password


class ChatPhotoAttachmentUrlUnitTest(unittest.TestCase):
    """Pure predicate unit tests for is_safe_chat_media_url."""

    def test_valid_chat_attachment_url_accepted(self):
        self.assertTrue(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef"))
        self.assertTrue(is_safe_chat_media_url("/api/chat/attachments/att_aaaaaaaaaaaaaaaa"))
        self.assertTrue(is_safe_chat_media_url("  /api/chat/attachments/att_0123456789abcdef  "))

    def test_valid_https_url_accepted(self):
        self.assertTrue(is_safe_chat_media_url("https://example.com/photo.jpg"))
        self.assertTrue(is_safe_chat_media_url("https://cdn.kandid.app/images/123.png"))

    def test_malformed_and_wrong_format_attachment_urls_rejected(self):
        # Empty or missing ID
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments"))
        # Short / wrong length ID
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_123"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcde"))   # 15 chars
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef0"))  # 17 chars
        # Uppercase hex rejected
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789ABCDEF"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_ABCDEF0123456789"))
        # Missing att_ prefix
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/0123456789abcdef"))
        # Extra path segments
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef/view"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef/"))
        # Query parameters
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef?token=xyz"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef?foo=bar"))
        # Fragment
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef#preview"))

    def test_arbitrary_relative_paths_rejected(self):
        self.assertFalse(is_safe_chat_media_url("/uploads/moment_123.jpg"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/messages"))
        self.assertFalse(is_safe_chat_media_url("/static/img/logo.png"))
        self.assertFalse(is_safe_chat_media_url("photo.jpg"))

    def test_traversal_attempts_rejected(self):
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/../etc/passwd"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/att_0123456789abcdef/../../etc/passwd"))
        self.assertFalse(is_safe_chat_media_url("/api/chat/attachments/%2e%2e/passwd"))

    def test_protocol_relative_and_prohibited_schemes_rejected(self):
        self.assertFalse(is_safe_chat_media_url("//evil.com/photo.jpg"))
        self.assertFalse(is_safe_chat_media_url("http://example.com/photo.jpg"))
        self.assertFalse(is_safe_chat_media_url("javascript:alert(1)"))
        self.assertFalse(is_safe_chat_media_url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="))
        self.assertFalse(is_safe_chat_media_url("ftp://example.com/photo.jpg"))
        self.assertFalse(is_safe_chat_media_url("file:///etc/passwd"))

    def test_empty_or_non_string_rejected(self):
        self.assertFalse(is_safe_chat_media_url(""))
        self.assertFalse(is_safe_chat_media_url("   "))
        self.assertFalse(is_safe_chat_media_url(None))
        self.assertFalse(is_safe_chat_media_url(12345))


class ChatPhotoAttachmentUrlIntegrationTest(unittest.TestCase):
    """End-to-end integration tests using in-process HTTP server and disposable database."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_chat_photo_test_")
        cls._orig_db_file = server.DB_FILE
        cls._orig_static_dir = server.STATIC_DIR
        cls._orig_env_db = os.environ.get("DATABASE_URL")

        # Force isolated SQLite
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        server.DATABASE_URL = None
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.STATIC_DIR = cls._tmpdir

        # Initialize test database
        init_db()

        # Seed two test users and sessions
        conn = server.get_db()
        pw_hash, pw_salt = hash_password("Password123!")

        conn.execute("""
            INSERT INTO users (id, name, handle, email, password_hash, salt, role, email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("u_alice", "Alice", "alice", "alice@example.com", pw_hash, pw_salt, "user", 1, "2026-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO users (id, name, handle, email, password_hash, salt, role, email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("u_bob", "Bob", "bob", "bob@example.com", pw_hash, pw_salt, "user", 1, "2026-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO users (id, name, handle, email, password_hash, salt, role, email_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("u_eve", "Eve", "eve", "eve@example.com", pw_hash, pw_salt, "user", 1, "2026-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, ("tok_alice", "u_alice", "2026-01-01T00:00:00", "2030-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, ("tok_bob", "u_bob", "2026-01-01T00:00:00", "2030-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, ("tok_eve", "u_eve", "2026-01-01T00:00:00", "2030-01-01T00:00:00"))

        conn.execute("""
            INSERT INTO friendships (id, user_id, friend_id, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("fr_alice_bob", "u_alice", "u_bob", "connected", "2026-01-01T00:00:00"))

        conn.commit()
        conn.close()

        # Start HTTP server on ephemeral port
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), KandidHandler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._server.shutdown()
            cls._server.server_close()
        except Exception:
            pass

        server.DB_FILE = cls._orig_db_file
        server.STATIC_DIR = cls._orig_static_dir
        if cls._orig_env_db:
            os.environ["DATABASE_URL"] = cls._orig_env_db

        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _api_request(self, path, method="GET", body=None, token="tok_alice"):
        url = f"http://127.0.0.1:{self._port}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp_data = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return resp.status, json.loads(resp_data.decode("utf-8"))
                return resp.status, resp_data
        except urllib.error.HTTPError as err:
            err_data = err.read()
            try:
                parsed = json.loads(err_data.decode("utf-8"))
            except Exception:
                parsed = err_data.decode("utf-8")
            return err.code, parsed

    def test_send_with_valid_chat_attachment_url_succeeds(self):
        # Alice sends valid attachment URL to Bob
        valid_att = "/api/chat/attachments/att_0123456789abcdef"
        status, data = self._api_request("/api/chat/send", method="POST", body={
            "receiverId": "u_bob",
            "message_type": "photo",
            "media_url": valid_att,
            "content": "Look at this photo"
        }, token="tok_alice")

        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message", {}).get("media_url"), valid_att)

    def test_send_with_valid_https_url_succeeds(self):
        https_url = "https://images.unsplash.com/photo-1517841905240-472988babdf9"
        status, data = self._api_request("/api/chat/send", method="POST", body={
            "receiverId": "u_bob",
            "message_type": "photo",
            "media_url": https_url,
            "content": "HTTPS photo"
        }, token="tok_alice")

        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message", {}).get("media_url"), https_url)

    def test_send_with_malformed_attachment_urls_rejected_with_400(self):
        invalid_urls = [
            "/api/chat/attachments/",
            "/api/chat/attachments/att_short",
            "/api/chat/attachments/att_0123456789ABCDEF",  # uppercase
            "/api/chat/attachments/att_0123456789abcdef?query=1",
            "/api/chat/attachments/att_0123456789abcdef#hash",
            "/api/chat/attachments/att_0123456789abcdef/extra",
            "/uploads/test.jpg",
            "/api/chat/messages",
            "//evil.com/photo.jpg",
            "http://insecure.com/photo.jpg",
            "javascript:alert(1)",
            "data:image/png;base64,abc",
            "ftp://example.com/test.jpg"
        ]

        for bad_url in invalid_urls:
            with self.subTest(bad_url=bad_url):
                status, data = self._api_request("/api/chat/send", method="POST", body={
                    "receiverId": "u_bob",
                    "message_type": "photo",
                    "media_url": bad_url,
                    "content": "Photo"
                }, token="tok_alice")

                self.assertEqual(status, 400, f"Expected 400 for {bad_url}, got {status}")
                self.assertFalse(data.get("success"))
                self.assertIn("Invalid media_url", data.get("error", ""))

    def test_normal_text_message_unaffected(self):
        status, data = self._api_request("/api/chat/send", method="POST", body={
            "receiverId": "u_bob",
            "content": "Hello Bob, standard text message"
        }, token="tok_alice")

        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message", {}).get("content"), "Hello Bob, standard text message")
        self.assertIsNone(data.get("message", {}).get("media_url"))

    def test_upload_send_and_authorized_retrieval_flow(self):
        # 1. Alice uploads an attachment intended for Bob
        # Create a small valid 1x1 transparent PNG
        tiny_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        b64_png = "data:image/png;base64," + base64.b64encode(tiny_png).decode("utf-8")

        status, upload_data = self._api_request("/api/chat/attachments", method="POST", body={
            "partner_id": "u_bob",
            "data": b64_png,
            "mime_type": "image/png"
        }, token="tok_alice")

        self.assertEqual(status, 201)
        self.assertTrue(upload_data.get("success"))
        attachment_url = upload_data.get("attachment", {}).get("url")
        self.assertTrue(attachment_url.startswith("/api/chat/attachments/att_"))

        # 2. Alice sends message referencing this attachment
        status, send_data = self._api_request("/api/chat/send", method="POST", body={
            "receiverId": "u_bob",
            "message_type": "photo",
            "media_url": attachment_url,
            "content": "Here is the photo"
        }, token="tok_alice")

        self.assertEqual(status, 201)
        self.assertTrue(send_data.get("success"))

        # 3. Authorized recipient (Bob) can retrieve the attachment
        status, file_bytes = self._api_request(attachment_url, method="GET", token="tok_bob")
        self.assertEqual(status, 200)
        self.assertEqual(file_bytes, tiny_png)

        # 4. Authorized sender (Alice) can retrieve the attachment
        status, file_bytes_alice = self._api_request(attachment_url, method="GET", token="tok_alice")
        self.assertEqual(status, 200)
        self.assertEqual(file_bytes_alice, tiny_png)

        # 5. Unauthorized third-party (Eve) cannot retrieve the attachment (403 Access denied)
        status, eve_data = self._api_request(attachment_url, method="GET", token="tok_eve")
        self.assertEqual(status, 403)
        self.assertFalse(eve_data.get("success"))

        # 6. Unauthenticated request rejected (401 Unauthorized)
        status, unauth_data = self._api_request(attachment_url, method="GET", token=None)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
