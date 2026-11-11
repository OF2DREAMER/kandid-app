#!/usr/bin/env python3
"""Regression coverage for the capture destination's community attribution.

A capture has one publishing destination. The client may not attach a second
community ID that would grant the post visibility in a community the user did
not select or join. These tests use a disposable SQLite database and never call
a production database or an external media provider.
"""

import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

# Pin the test process before importing server so an ambient .env or production
# environment cannot select a real database or media provider.
_TEST_ENV = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "",
    "BREVO_API_KEY": "",
    "RESEND_API_KEY": "",
    "RENDER": "",
    "RENDER_SERVICE_ID": "",
    "SESSION_SECRET": "capture-context-test-session-secret-0123456789abcdef",
}
_ORIGINAL_ENV = {key: os.environ.get(key) for key in _TEST_ENV}
os.environ.update(_TEST_ENV)

import server  # noqa: E402  (environment must be pinned before import)

for _key in ("ENVIRONMENT", "BREVO_API_KEY", "RESEND_API_KEY"):
    os.environ.pop(_key, None)

_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def tearDownModule():
    for key, value in _ORIGINAL_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


class _Request(server.KandidHandler):
    """Invoke the real POST handler while replacing only the HTTP boundary."""

    def __init__(self, path, payload, token):
        raw = json.dumps(payload).encode("utf-8")
        self.path = path
        self.headers = {
            "Content-Length": str(len(raw)),
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        }
        self.rfile = io.BytesIO(raw)
        self.client_address = ("127.0.0.1", 32146)
        self.close_connection = False
        self.response = None

    def send_json(self, status, data):
        self.response = {"status": status, "body": data}
        return data


class TestCaptureContextValidation(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="kindid_capture_context_", suffix=".db")
        os.close(fd)
        self.addCleanup(self._cleanup)

        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""
        server.init_db()

        self.user_id = "u_capture_context"
        self.token = "token_capture_context"
        self.community_id = "comm_capture_context"
        self.other_community_id = "comm_other_context"

        password_hash, salt = server.hash_password("CaptureContextPassword123!")
        conn = server.get_db()
        try:
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, "
                "role, email_verified, is_onboarded, account_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'student', 1, 1, 'active')",
                (
                    self.user_id,
                    "capture.context@example.test",
                    "capture_context_user",
                    "Capture Context User",
                    password_hash,
                    salt,
                    "North City University",
                ),
            )
            conn.execute(
                "INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)",
                (
                    "sess_capture_context",
                    self.user_id,
                    self.token,
                    (datetime.now() + timedelta(days=1)).isoformat(),
                ),
            )
            conn.execute(
                "INSERT INTO communities (id, name, type, creator_id, visibility, members_count) "
                "VALUES (?, ?, 'Interest', 'u_someone_else', 'public', 2)",
                (self.community_id, "Capture Context Community"),
            )
            conn.execute(
                "INSERT INTO communities (id, name, type, creator_id, visibility, members_count) "
                "VALUES (?, ?, 'Interest', 'u_someone_else', 'public', 2)",
                (self.other_community_id, "Unselected Community"),
            )
            conn.execute(
                "INSERT INTO community_members (community_id, user_id, role, status) "
                "VALUES (?, ?, 'member', 'active')",
                (self.community_id, self.user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _cleanup(self):
        server.DB_FILE = _ORIGINAL_DB_FILE
        server.DATABASE_URL = _ORIGINAL_DATABASE_URL
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def _capture(self, payload):
        request = _Request("/api/moments/capture", payload, self.token)
        with patch("server.save_base64_image", return_value="/uploads/capture-test.png"):
            request.do_POST()
        self.assertIsNotNone(request.response, "handler produced no JSON response")
        return request.response

    def _payload(self, **overrides):
        payload = {
            "caption": "Capture context validation",
            "circle": "campus",
            "region": "all",
            "locationCity": "Near Quad",
            "community": "",
            "community_id": "",
            "primary_community_id": "",
            "context_community_id": "",
            "context_location": "Near Quad",
            "mainImg": "data:image/png;base64,AAAA",
            "pipImg": "data:image/png;base64,BBBB",
            "audioData": "",
            "audioDuration": "3.0s",
            "iso": "ISO 400",
            "aperture": "f/2.8",
            "shutter": "1/250s",
            "is_daily_mission": False,
            "event_id": "",
            "cluster_id": "",
        }
        payload.update(overrides)
        return payload

    def _stored_context(self, post_id):
        conn = server.get_db()
        try:
            row = conn.execute(
                "SELECT primary_community_id, context_community_id FROM posts WHERE id = ?",
                (post_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def test_conflicting_context_is_never_persisted(self):
        response = self._capture(
            self._payload(
                primary_community_id=self.community_id,
                community_id=self.community_id,
                context_community_id=self.other_community_id,
            )
        )

        self.assertEqual(response["status"], 201, response)
        post = response["body"]["post"]
        self.assertEqual(post["primary_community_id"], self.community_id)
        self.assertEqual(post["context_community_id"], "")
        stored = self._stored_context(post["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["primary_community_id"], self.community_id)
        self.assertEqual(stored["context_community_id"], "")

    def test_personal_capture_ignores_context_community_id(self):
        response = self._capture(
            self._payload(context_community_id=self.other_community_id)
        )

        self.assertEqual(response["status"], 201, response)
        post = response["body"]["post"]
        self.assertEqual(post["primary_community_id"], "")
        self.assertEqual(post["context_community_id"], "")
        stored = self._stored_context(post["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["primary_community_id"], "")
        self.assertEqual(stored["context_community_id"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
