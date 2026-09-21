#!/usr/bin/env python3
"""
Focused regression test for D4-05: onboarding session expiry enforcement.

BEFORE: onboarding_sessions rows are created with a 24h `expires_at`, and the
RESUME_ONBOARDING lookup (Google auth) already filters `expires_at > ?`. But:
  - POST /api/onboarding/complete   -> SELECT ... WHERE id = ?        (no expiry filter)
  - POST /api/onboarding/update-step-> UPDATE ... WHERE id = ?         (no expiry filter)
so an expired session id could still (a) complete onboarding, creating a user,
auth identity and 365-day session, or (b) mutate the stale session row.

AFTER: both statements add `AND expires_at > ?` bound to
datetime.now().isoformat() — the same ISO format the row is written with and
the same predicate the existing RESUME lookup uses.

Tests run against the REAL routes over HTTP with an isolated SQLite database,
and assert NEGATIVE SIDE EFFECTS (no user / no auth identity / no session row
created; update-step row untouched) — not just HTTP status codes.

Read-only w.r.t. the developer DB: DB_FILE/DATABASE_URL are redirected to a
disposable copy for the whole test class.
"""

import json
import os
import shutil
import sqlite3
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

EXPIRED_MSG = "Onboarding session expired or not found. Please start over."


class OnboardingExpiryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_d4_05_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_d4_05.db")
        server.init_db()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
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

    # ---- helpers -------------------------------------------------------------
    @classmethod
    def _db(cls):
        conn = sqlite3.connect(server.DB_FILE, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def _seed_session(cls, sid, expires_at, email, subject, step=1, handle="", city=""):
        conn = cls._db()
        conn.execute(
            """INSERT INTO onboarding_sessions
                   (id, provider, provider_subject, email, google_name, google_avatar,
                    step, chosen_handle, chosen_campus_id, chosen_campus_name, chosen_city, expires_at)
               VALUES (?, 'google', ?, ?, 'Tester', '', ?, ?, '', '', ?, ?)""",
            (sid, subject, email, step, handle, city, expires_at),
        )
        conn.commit()
        conn.close()

    @classmethod
    def _row(cls, sid):
        conn = cls._db()
        r = conn.execute("SELECT * FROM onboarding_sessions WHERE id = ?", (sid,)).fetchone()
        conn.close()
        return dict(r) if r else None

    @classmethod
    def _count(cls, sql, params=()):
        conn = cls._db()
        n = conn.execute(sql, params).fetchone()[0]
        conn.close()
        return n

    def _post(self, path, payload):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://{self.host}:{self.port}{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            return e.code, (json.loads(raw) if raw else {})

    def _get(self, path, token=None):
        req = urllib.request.Request(f"http://{self.host}:{self.port}{path}")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            return e.code, (json.loads(raw) if raw else {})

    def _iso(self, delta):
        return (datetime.now() + delta).isoformat()

    # ---- complete: expired sessions -------------------------------------------
    def test_01_expired_complete_returns_400_with_unchanged_message(self):
        self._seed_session("onb_exp_1", self._iso(timedelta(hours=-1)), "exp1@example.test", "subj-exp1")
        status, body = self._post("/api/onboarding/complete",
                                  {"session_id": "onb_exp_1", "handle": "expuser1", "name": "Exp One"})
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("error"), EXPIRED_MSG)

    def test_02_thirty_day_expired_complete_returns_400(self):
        self._seed_session("onb_exp_30", self._iso(timedelta(days=-30)), "exp30@example.test", "subj-exp30")
        status, body = self._post("/api/onboarding/complete",
                                  {"session_id": "onb_exp_30", "handle": "expuser30", "name": "Exp Thirty"})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error"), EXPIRED_MSG)

    def test_03_expired_complete_creates_no_user_no_session_no_auth_identity(self):
        self._seed_session("onb_exp_2", self._iso(timedelta(hours=-2)), "exp2@example.test", "subj-exp2")
        users_before = self._count("SELECT COUNT(*) FROM users")
        sessions_before = self._count("SELECT COUNT(*) FROM sessions")
        auth_before = self._count("SELECT COUNT(*) FROM auth_identities")

        status, _ = self._post("/api/onboarding/complete",
                               {"session_id": "onb_exp_2", "handle": "expuser2", "name": "Exp Two"})
        self.assertEqual(status, 400)

        self.assertEqual(self._count("SELECT COUNT(*) FROM users"), users_before)
        self.assertEqual(self._count("SELECT COUNT(*) FROM sessions"), sessions_before)
        self.assertEqual(self._count("SELECT COUNT(*) FROM auth_identities"), auth_before)
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE LOWER(email) = ?", ("exp2@example.test",)), 0)
        # expired row is intentionally NOT cleaned up (no cleanup in D4-05)
        self.assertIsNotNone(self._row("onb_exp_2"))

    def test_04_complete_missing_and_unknown_session_contracts_unchanged(self):
        status, body = self._post("/api/onboarding/complete", {})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error"), "Invalid onboarding session.")

        status, body = self._post("/api/onboarding/complete", {"session_id": "onb_does_not_exist", "handle": "nouser"})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error"), EXPIRED_MSG)

    def test_05_expiry_boundary_is_deterministic(self):
        # expires_at == now (fixture time) -> handler's now is >= that -> expired
        self._seed_session("onb_boundary", self._iso(timedelta(0)), "bnd@example.test", "subj-bnd")
        status, body = self._post("/api/onboarding/complete",
                                  {"session_id": "onb_boundary", "handle": "bnduser", "name": "Boundary"})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error"), EXPIRED_MSG)
        # expires_at 60s in the future -> clearly valid (no clock race)
        self._seed_session("onb_future60", self._iso(timedelta(seconds=60)), "fut60@example.test", "subj-fut60")
        status, body = self._post("/api/onboarding/complete",
                                  {"session_id": "onb_future60", "handle": "futuser60", "name": "Future Sixty"})
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

    # ---- complete: valid session ----------------------------------------------
    def test_06_valid_complete_succeeds_and_account_session_work(self):
        self._seed_session("onb_valid", self._iso(timedelta(hours=24)), "valid@example.test", "subj-valid",
                           step=2, handle="validhandle", city="Mumbai")
        status, body = self._post("/api/onboarding/complete", {
            "session_id": "onb_valid", "handle": "validhandle", "name": "Valid User",
            "campus_name": "Valid Campus", "campus_id": "c_v", "city": "Mumbai", "password": "pw123",
        })
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        token = body.get("token")
        self.assertTrue(token)

        # account really exists and the session token works against a real route
        self.assertEqual(self._count("SELECT COUNT(*) FROM users WHERE LOWER(handle) = ?", ("validhandle",)), 1)
        st, me = self._get("/api/me", token=token)
        self.assertEqual(st, 200)
        self.assertTrue(me.get("success"))
        self.assertEqual(me["user"]["handle"], "validhandle")

    def test_07_valid_complete_is_one_shot(self):
        self._seed_session("onb_oneshot", self._iso(timedelta(hours=24)), "oneshot@example.test", "subj-one",
                           handle="oneshothandle")
        st, body = self._post("/api/onboarding/complete",
                              {"session_id": "onb_oneshot", "handle": "oneshothandle", "name": "One Shot"})
        self.assertEqual(st, 200)
        self.assertIsNone(self._row("onb_oneshot"))  # temp session consumed
        st2, body2 = self._post("/api/onboarding/complete",
                                {"session_id": "onb_oneshot", "handle": "oneshot2", "name": "One Shot Again"})
        self.assertEqual(st2, 400)
        self.assertEqual(body2.get("error"), EXPIRED_MSG)

    # ---- update-step -----------------------------------------------------------
    def test_08_expired_update_step_rejected_and_row_not_mutated(self):
        self._seed_session("onb_upd_exp", self._iso(timedelta(hours=-3)), "updexp@example.test", "subj-updexp",
                           step=1, handle="original", city="Original City")
        before = self._row("onb_upd_exp")
        status, body = self._post("/api/onboarding/update-step", {
            "session_id": "onb_upd_exp", "step": 4, "handle": "hacked",
            "campus_id": "c_x", "campus_name": "Hacked Campus", "city": "Hacked City",
        })
        # D4-05 correction: expired session is explicitly REJECTED with 400.
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("error"), EXPIRED_MSG)
        after = self._row("onb_upd_exp")
        self.assertEqual(after, before, "expired session row must not be mutated")
        self.assertEqual(after["step"], 1)
        self.assertEqual(after["chosen_handle"], "original")
        self.assertEqual(after["chosen_city"], "Original City")
        self.assertEqual(after["chosen_campus_id"], "")

    def test_09_valid_update_step_still_works(self):
        self._seed_session("onb_upd_ok", self._iso(timedelta(hours=24)), "updok@example.test", "subj-updok",
                           step=1, handle="firsthandle")
        status, body = self._post("/api/onboarding/update-step", {
            "session_id": "onb_upd_ok", "step": 3, "handle": "secondhandle",
            "campus_id": "c_ok", "campus_name": "Okay Campus", "city": "Pune",
        })
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        row = self._row("onb_upd_ok")
        self.assertEqual(row["step"], 3)
        self.assertEqual(row["chosen_handle"], "secondhandle")
        self.assertEqual(row["chosen_campus_id"], "c_ok")
        self.assertEqual(row["chosen_campus_name"], "Okay Campus")
        self.assertEqual(row["chosen_city"], "Pune")

    def test_10_update_step_expiry_boundary_deterministic(self):
        # expires_at == now -> rejected (400), row untouched
        self._seed_session("onb_upd_bound", self._iso(timedelta(0)), "updbnd@example.test", "subj-updbnd",
                           step=1, handle="keepme")
        st, body = self._post("/api/onboarding/update-step", {"session_id": "onb_upd_bound", "step": 9, "handle": "nope"})
        self.assertEqual(st, 400)
        self.assertEqual(body.get("error"), EXPIRED_MSG)
        self.assertEqual(self._row("onb_upd_bound")["step"], 1)
        self.assertEqual(self._row("onb_upd_bound")["chosen_handle"], "keepme")
        # just inside the boundary (60s ahead) -> accepted (200) and mutated
        self._seed_session("onb_upd_inside", self._iso(timedelta(seconds=60)), "updin@example.test", "subj-updin",
                           step=1, handle="beforeswap")
        st2, body2 = self._post("/api/onboarding/update-step", {"session_id": "onb_upd_inside", "step": 2, "handle": "afterswap"})
        self.assertEqual(st2, 200)
        self.assertTrue(body2.get("success"))
        self.assertEqual(self._row("onb_upd_inside")["step"], 2)
        self.assertEqual(self._row("onb_upd_inside")["chosen_handle"], "afterswap")

    def test_11_update_step_missing_session_id_contract_unchanged(self):
        status, body = self._post("/api/onboarding/update-step", {"step": 2})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error"), "session_id is required")

    def test_12_expired_complete_has_no_community_side_effects(self):
        members_before = self._count("SELECT COUNT(*) FROM community_members")
        comms_before = self._count("SELECT COUNT(*) FROM communities")
        self._seed_session("onb_exp_comm", self._iso(timedelta(days=-1)), "expc@example.test", "subj-expc")
        status, _ = self._post("/api/onboarding/complete", {
            "session_id": "onb_exp_comm", "handle": "expcuser", "name": "Exp C",
            "campus_name": "Ghost Campus", "campus_id": "c_ghost", "city": "Nowhere",
        })
        self.assertEqual(status, 400)
        self.assertEqual(self._count("SELECT COUNT(*) FROM community_members"), members_before)
        self.assertEqual(self._count("SELECT COUNT(*) FROM communities"), comms_before)
        self.assertEqual(self._count("SELECT COUNT(*) FROM communities WHERE LOWER(name) = ?", ("ghost campus",)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
