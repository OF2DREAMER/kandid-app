#!/usr/bin/env python3
"""Regression and security tests for /api/user/change-password.

The suite uses a disposable SQLite database initialized by the server's own
schema. It never reads or writes production data.

Password whitespace semantics documented by these tests:
- Login, registration, reset-password, and change-password all trim leading and
  trailing whitespace before hashing or verifying it.
- The change-password remediation standardizes on that existing login behavior,
  so it can never store a password that the login form cannot reproduce.

Run: python3 -m unittest -v test_password_change
"""

import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import server


_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL


class _Request(server.KandidHandler):
    """Real handler invocation with only the HTTP response boundary replaced."""

    def __init__(self, path, payload, token=None):
        raw = json.dumps(payload).encode("utf-8")
        self.path = path
        self.headers = {
            "Content-Length": str(len(raw)),
            "Content-Type": "application/json",
        }
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.rfile = io.BytesIO(raw)
        self.client_address = ("127.0.0.1", 32145)
        self.close_connection = False
        self.response = None

    def send_json(self, status, data):
        self.response = {"status": status, "body": data}
        return data


class _FailureOnSessionDelete:
    """Connection proxy that makes the required session revocation fail."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def execute(self, sql, params=None):
        if "delete from sessions" in sql.lower():
            raise RuntimeError("simulated session revocation failure")
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()


class TestPasswordChange(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(
            prefix="kindid_password_change_", suffix=".db"
        )
        os.close(fd)
        self.addCleanup(self._cleanup)

        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""
        with server.rate_limiter.lock:
            server.rate_limiter.buckets.clear()

        server.init_db()

        self.user_id = "u_password_change"
        self.handle = "password_change_user"
        self.initial_password = "InitialPassword123!"
        self.new_password = "NewPassword456!"
        password_hash, salt = server.hash_password(self.initial_password)

        conn = server.get_db()
        try:
            conn.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.user_id,
                    "password.change@example.test",
                    self.handle,
                    "Password Change User",
                    password_hash,
                    salt,
                ),
            )
            expires_at = (datetime.now() + timedelta(days=1)).isoformat()
            created_at = datetime.now().isoformat()
            for token in ("token_password_change_current", "token_password_change_other"):
                conn.execute(
                    "INSERT INTO sessions (id, user_id, token, expires_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("sess_" + token, self.user_id, token, expires_at, created_at),
                )
            conn.commit()
        finally:
            conn.close()

    def _cleanup(self):
        _restore_server_globals()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def _request(self, path, payload, token=None):
        request = _Request(path, payload, token)
        request.do_POST()
        self.assertIsNotNone(request.response, "handler produced no JSON response")
        return request.response

    def _change(self, current_password, new_password, token="token_password_change_current"):
        return self._request(
            "/api/user/change-password",
            {
                "current_password": current_password,
                "new_password": new_password,
            },
            token=token,
        )

    def _login(self, password):
        return self._request(
            "/api/auth/login",
            {"identifier": self.handle, "password": password},
        )

    def _user_secret(self):
        conn = server.get_db()
        try:
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE id = ?",
                (self.user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _session_tokens(self):
        conn = server.get_db()
        try:
            rows = conn.execute(
                "SELECT token FROM sessions WHERE user_id = ? ORDER BY token",
                (self.user_id,),
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def _assert_secret_unchanged(self, expected):
        current = self._user_secret()
        self.assertIsNotNone(current)
        self.assertEqual(current["password_hash"], expected["password_hash"])
        self.assertEqual(current["salt"], expected["salt"])

    def test_01_correct_current_password_changes_and_revokes_sessions(self):
        before_sessions = self._session_tokens()
        self.assertEqual(len(before_sessions), 2)

        response = self._change(self.initial_password, self.new_password)

        self.assertEqual(response["status"], 200, response)
        self.assertTrue(response["body"].get("success"), response)
        self.assertIn("sign in again", response["body"].get("message", "").lower())

        secret = self._user_secret()
        self.assertTrue(
            server.verify_password(self.new_password, secret["salt"], secret["password_hash"])
        )
        self.assertFalse(
            server.verify_password(self.initial_password, secret["salt"], secret["password_hash"])
        )
        self.assertEqual(self._session_tokens(), [])
        self.assertIsNone(
            server.get_current_user(
                {"Authorization": "Bearer token_password_change_current"}
            )
        )

        new_login = self._login(self.new_password)
        self.assertEqual(new_login["status"], 200, new_login)
        old_login = self._login(self.initial_password)
        self.assertEqual(old_login["status"], 401, old_login)

    def test_02_incorrect_current_password_has_no_side_effects(self):
        before_secret = self._user_secret()
        before_sessions = self._session_tokens()

        response = self._change("WrongCurrentPassword123!", self.new_password)

        self.assertEqual(response["status"], 400, response)
        self.assertIn("Current password is incorrect", response["body"].get("error", ""))
        self._assert_secret_unchanged(before_secret)
        self.assertEqual(self._session_tokens(), before_sessions)

    def test_03_missing_or_invalid_session_is_rejected(self):
        before_secret = self._user_secret()
        before_sessions = self._session_tokens()

        missing = self._change(self.initial_password, self.new_password, token=None)
        invalid = self._change(
            self.initial_password,
            self.new_password,
            token="token_does_not_exist",
        )

        self.assertEqual(missing["status"], 401, missing)
        self.assertEqual(invalid["status"], 401, invalid)
        self._assert_secret_unchanged(before_secret)
        self.assertEqual(self._session_tokens(), before_sessions)

    def test_04_short_new_password_uses_existing_validation_response(self):
        before_secret = self._user_secret()
        before_sessions = self._session_tokens()

        response = self._change(self.initial_password, "short")

        self.assertEqual(response["status"], 400, response)
        self.assertIn(
            "at least 8 characters",
            response["body"].get("error", ""),
        )
        self._assert_secret_unchanged(before_secret)
        self.assertEqual(self._session_tokens(), before_sessions)

    def test_05_special_and_non_ascii_password_round_trip(self):
        password = "Pässwörd-Ω-🔐-1234"

        response = self._change(self.initial_password, password)

        self.assertEqual(response["status"], 200, response)
        secret = self._user_secret()
        self.assertTrue(
            server.verify_password(password, secret["salt"], secret["password_hash"])
        )
        login = self._login(password)
        self.assertEqual(login["status"], 200, login)

    def test_06_leading_and_trailing_whitespace_is_trimmed_consistently(self):
        """Change-password follows the same trimming as login and registration."""
        trimmed_password = "WhitespacePassword123!"
        submitted_password = "  " + trimmed_password + "  "
        submitted_current = "  " + self.initial_password + "  "

        response = self._change(submitted_current, submitted_password)

        self.assertEqual(response["status"], 200, response)
        secret = self._user_secret()
        self.assertTrue(
            server.verify_password(trimmed_password, secret["salt"], secret["password_hash"])
        )
        self.assertFalse(
            server.verify_password(submitted_password, secret["salt"], secret["password_hash"])
        )
        self.assertEqual(self._login(submitted_password)["status"], 200)
        self.assertEqual(self._login(trimmed_password)["status"], 200)

    def test_07_rate_limit_is_enforced_without_side_effects(self):
        before_secret = self._user_secret()
        before_sessions = self._session_tokens()

        # Five rejected attempts are the configured allowance; the sixth call
        # must be blocked even though it supplies the correct current password.
        for _ in range(5):
            rejected = self._change("WrongCurrentPassword123!", self.new_password)
            self.assertEqual(rejected["status"], 400, rejected)

        response = self._change(self.initial_password, self.new_password)

        self.assertEqual(response["status"], 429, response)
        self.assertEqual(
            response["body"].get("error_code"),
            "KANDID_RATE_LIMITED",
            response,
        )
        self._assert_secret_unchanged(before_secret)
        self.assertEqual(self._session_tokens(), before_sessions)

    def test_08_session_revocation_failure_never_reports_success(self):
        before_secret = self._user_secret()
        before_sessions = self._session_tokens()
        real_conn = server.get_db()
        failing_conn = _FailureOnSessionDelete(server.get_db())
        calls = iter([real_conn, failing_conn])

        with patch("server.get_db", side_effect=lambda: next(calls)):
            response = self._change(self.initial_password, self.new_password)

        self.assertEqual(response["status"], 500, response)
        self.assertFalse(response["body"].get("success"), response)
        self._assert_secret_unchanged(before_secret)
        self.assertEqual(self._session_tokens(), before_sessions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
