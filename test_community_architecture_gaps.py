#!/usr/bin/env python3
"""
Test Suite for Kindid Community Architecture Gaps.
Verifies:
1. Community Settings (POST /api/community/settings):
   - Owner allowed; moderator/member/visitor 403.
   - Name collision rejection.
   - Private moment preservation on visibility toggle.
2. Member Management:
   - GET /api/community/members (real members list; private community gating).
   - POST /api/community/members/remove (hierarchy defense: mod cannot remove owner or mod; cannot remove self).
   - POST /api/community/invites/revoke (owner/inviter allowed; others 403).
3. Private Community Join Requests:
   - POST /api/community/join-request (pending request creation; public community instruction; suspension block).
   - GET /api/community/join-requests (owner/mod allowed; member 403).
   - POST /api/community/join-requests/review (approve adds active member; reject updates status).
4. Collective Memory Management:
   - Publishing with theme and year.
   - POST /api/community/memories/curate (edit title/story/theme/year).
   - POST /api/community/memories/delete (safe deletion: moments in posts table preserved).
5. Community Activity (GET /api/community/manage):
   - Real DB-derived counts for pending_join_requests_count and recent_moments_count.
6. Ownership Continuity:
   - POST /api/community/transfer-ownership (eligibility checks: target active member, not suspended; confirmation 'TRANSFER').
   - POST /api/community/close (archival with confirmation 'CLOSE').
   - POST /api/user/delete-account (safeguard preventing owner deletion when owning community with members).
"""

import os
os.environ["DATABASE_URL"] = ""
os.environ["ENVIRONMENT"] = "development"

import json
import shutil
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler

TOKEN_OWNER = "tok_test_owner_gap"
TOKEN_MOD = "tok_test_mod_gap"
TOKEN_MOD2 = "tok_test_mod2_gap"
TOKEN_MEMBER = "tok_test_member_gap"
TOKEN_VISITOR = "tok_test_visitor_gap"
TOKEN_CANDIDATE = "tok_test_candidate_gap"


class TestCommunityArchitectureGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_gap_test_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Test users
        users = [
            ("u_owner_gap", "owner_gap@test.com", "owner_gap", "Owner Gap", "student"),
            ("u_mod_gap", "mod_gap@test.com", "mod_gap", "Mod Gap", "student"),
            ("u_mod2_gap", "mod2_gap@test.com", "mod2_gap", "Mod 2 Gap", "student"),
            ("u_member_gap", "member_gap@test.com", "member_gap", "Member Gap", "student"),
            ("u_visitor_gap", "visitor_gap@test.com", "visitor_gap", "Visitor Gap", "student"),
            ("u_candidate_gap", "candidate_gap@test.com", "candidate_gap", "Candidate Gap", "student"),
        ]
        for uid, email, handle, name, role in users:
            cursor.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES (?, ?, ?, ?, 'h', 's', 'Campus Gap', ?, 1, 1, 'active')",
                (uid, email, handle, name, role),
            )

        # 2. Test sessions
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_o_gap", "u_owner_gap", TOKEN_OWNER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_m_gap", "u_mod_gap", TOKEN_MOD, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_m2_gap", "u_mod2_gap", TOKEN_MOD2, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_mem_gap", "u_member_gap", TOKEN_MEMBER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_vis_gap", "u_visitor_gap", TOKEN_VISITOR, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_cand_gap", "u_candidate_gap", TOKEN_CANDIDATE, "2099-01-01T00:00:00Z"))

        # 3. Test communities: comm_public and comm_private
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("comm_pub_gap", "Public Gap Space", "Interest", "Public discussion", "City Gap", "u_owner_gap", "owner_gap", "🌟", "public", 4),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("comm_priv_gap", "Private Gap Space", "Interest", "Private enclave", "City Gap", "u_owner_gap", "owner_gap", "🔒", "private", 3),
        )

        # 4. Memberships for comm_pub_gap
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_pub_gap", "u_owner_gap"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_pub_gap", "u_mod_gap"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_pub_gap", "u_mod2_gap"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_pub_gap", "u_member_gap"))

        # Memberships for comm_priv_gap
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_priv_gap", "u_owner_gap"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_priv_gap", "u_mod_gap"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_priv_gap", "u_member_gap"))

        # 5. Moments for comm_pub_gap
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, 'https://res.cloudinary.com/test/p1.jpg', 'https://res.cloudinary.com/test/pip1.jpg', 'Public moment 1', 0, 'comm_pub_gap', 'Public Gap Space', datetime('now', '-2 days'))
        """, ("post_pub_1", "u_member_gap", "member_gap", "Member Gap"))
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, 'https://res.cloudinary.com/test/p2.jpg', 'https://res.cloudinary.com/test/pip2.jpg', 'Private moment in space', 1, 'comm_pub_gap', 'Public Gap Space', datetime('now', '-1 days'))
        """, ("post_priv_in_pub", "u_member_gap", "member_gap", "Member Gap"))

        # 6. Community invite for comm_pub_gap
        cursor.execute("""
            INSERT INTO community_invites (id, invite_code, inviter_user_id, community_id, status)
            VALUES ('inv_gap_1', 'GAPINV123', 'u_mod_gap', 'comm_pub_gap', 'active')
        """)

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        if os.path.exists(cls._tmpdir):
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _req(self, path, method="GET", token=None, body=None):
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

        t = server.threading.Thread(target=run_handler)
        t.daemon = True
        t.start()

        body_bytes = b""
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")

        req = f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\nCookie: session_token={token}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "Connection: close\r\n\r\n"

        s2.sendall(req.encode("utf-8") + body_bytes)

        resp = b""
        while True:
            chunk = s2.recv(4096)
            if not chunk:
                break
            resp += chunk
        s2.close()
        t.join(timeout=2.0)

        header_part, _, body_part = resp.partition(b"\r\n\r\n")
        lines = header_part.decode("latin1", errors="replace").split("\r\n")
        status_code = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 500

        data = {}
        if body_part:
            try:
                data = json.loads(body_part.decode("utf-8", errors="replace"))
            except Exception:
                pass
        return status_code, data

    # -------------------------------------------------------------------------
    # Requirement A: Community Settings
    # -------------------------------------------------------------------------
    def test_settings_owner_allowed(self):
        status, data = self._req(
            "/api/community/settings",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "description": "Updated public description", "icon": "🚀"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("community", {}).get("description"), "Updated public description")
        self.assertEqual(data.get("community", {}).get("icon"), "🚀")

    def test_settings_non_owner_forbidden(self):
        for tok in (TOKEN_MOD, TOKEN_MEMBER, TOKEN_VISITOR):
            status, data = self._req(
                "/api/community/settings",
                method="POST",
                token=tok,
                body={"community_id": "comm_pub_gap", "description": "Hacked description"}
            )
            self.assertEqual(status, 403, f"Expected 403 for token {tok}")

    def test_settings_name_collision_rejected(self):
        status, data = self._req(
            "/api/community/settings",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "name": "Private Gap Space"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "NAME_EXISTS")

    def test_settings_visibility_switch_preserves_private_moments(self):
        # Toggle private space to public
        status, data = self._req(
            "/api/community/settings",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "visibility": "private"}
        )
        self.assertEqual(status, 200)
        # Verify private post post_priv_in_pub still has is_private = 1
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT is_private FROM posts WHERE id = 'post_priv_in_pub'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], 1, "Private moment must remain is_private = 1")

        # Toggle back to public
        self._req("/api/community/settings", method="POST", token=TOKEN_OWNER, body={"community_id": "comm_pub_gap", "visibility": "public"})

    # -------------------------------------------------------------------------
    # Requirement B: Member Management & Hierarchy Defense
    # -------------------------------------------------------------------------
    def test_members_list_real_db(self):
        status, data = self._req("/api/community/members?community_id=comm_pub_gap", token=TOKEN_MEMBER)
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        members = data.get("members", [])
        self.assertGreaterEqual(len(members), 4)
        handles = [m.get("handle") for m in members]
        self.assertIn("owner_gap", handles)
        self.assertIn("mod_gap", handles)
        self.assertIn("member_gap", handles)

    def test_members_list_private_community_gating(self):
        # Member can view
        status, data = self._req("/api/community/members?community_id=comm_priv_gap", token=TOKEN_MEMBER)
        self.assertEqual(status, 200)

        # Visitor not in private community gets 403
        status, data = self._req("/api/community/members?community_id=comm_priv_gap", token=TOKEN_VISITOR)
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "PRIVATE_COMMUNITY_RESTRICTED")

    def test_member_removal_hierarchy_defense(self):
        # 1. Mod CANNOT remove owner
        status, data = self._req(
            "/api/community/members/remove",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "target_user_id": "u_owner_gap"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "CANNOT_REMOVE_OWNER")

        # 2. Mod CANNOT remove another mod
        status, data = self._req(
            "/api/community/members/remove",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "target_user_id": "u_mod2_gap"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "MODERATOR_CANNOT_REMOVE_MODERATOR")

        # 3. User CANNOT remove self via this endpoint
        status, data = self._req(
            "/api/community/members/remove",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "target_user_id": "u_mod_gap"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CANNOT_REMOVE_SELF")

        # 4. Mod CAN remove regular member
        status, data = self._req(
            "/api/community/members/remove",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "target_user_id": "u_member_gap"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

        # Re-add u_member_gap for subsequent tests
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES ('comm_pub_gap', 'u_member_gap', 'member', 'active')")
        cur.execute("UPDATE communities SET members_count = members_count + 1 WHERE id = 'comm_pub_gap'")
        conn.commit()
        conn.close()

    def test_invite_revocation(self):
        # Member cannot revoke
        status, _ = self._req("/api/community/invites/revoke", method="POST", token=TOKEN_MEMBER, body={"community_id": "comm_pub_gap", "invite_code": "GAPINV123"})
        self.assertEqual(status, 403)

        # Inviter can revoke
        status, data = self._req("/api/community/invites/revoke", method="POST", token=TOKEN_MOD, body={"community_id": "comm_pub_gap", "invite_code": "GAPINV123"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

    # -------------------------------------------------------------------------
    # Requirement B & G: Private Community Join Requests
    # -------------------------------------------------------------------------
    def test_join_request_lifecycle(self):
        # 0. Candidate checks restricted private community before requesting
        status, data = self._req(
            "/api/community/detail?id=comm_priv_gap",
            method="GET",
            token=TOKEN_CANDIDATE
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "COMMUNITY_RESTRICTED")
        self.assertFalse(data.get("has_pending_request"))
        self.assertIsNone(data.get("join_request_status"))
        self.assertEqual(data.get("community_id"), "comm_priv_gap")
        self.assertEqual(data.get("community_name"), "Private Gap Space")
        self.assertNotIn("moments", data)
        self.assertNotIn("collective_memories", data)

        # 1. Candidate submits join request for private community
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_CANDIDATE,
            body={"community_id": "comm_priv_gap"}
        )
        self.assertIn(status, (200, 201))
        self.assertEqual(data.get("status"), "pending")

        # 1b. Candidate re-checks restricted screen (subsequent visit / page refresh)
        status, data = self._req(
            "/api/community/detail?id=comm_priv_gap",
            method="GET",
            token=TOKEN_CANDIDATE
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "COMMUNITY_RESTRICTED")
        self.assertTrue(data.get("has_pending_request"))
        self.assertEqual(data.get("join_request_status"), "pending")
        self.assertEqual(data.get("community_id"), "comm_priv_gap")
        self.assertNotIn("moments", data)

        # 1c. Duplicate submission while pending returns 200 with status pending
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_CANDIDATE,
            body={"community_id": "comm_priv_gap"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "pending")

        # 2. Public community rejects join-request (instructs direct join)
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_CANDIDATE,
            body={"community_id": "comm_pub_gap"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "COMMUNITY_IS_PUBLIC")

        # 3. Owner/mod views join requests
        status, data = self._req("/api/community/join-requests?community_id=comm_priv_gap", token=TOKEN_MOD)
        self.assertEqual(status, 200)
        reqs = data.get("requests", [])
        self.assertGreaterEqual(len(reqs), 1)
        target_req = next((r for r in reqs if r.get("user_id") == "u_candidate_gap"), None)
        self.assertIsNotNone(target_req)

        # 4. Mod approves request
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": target_req["id"], "action": "approve"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("action"), "approve")

        # Verify candidate is now active member
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT status FROM community_members WHERE community_id = 'comm_priv_gap' AND user_id = 'u_candidate_gap'")
        mem_row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(mem_row)
        self.assertEqual(mem_row[0], "active")

        # 4b. Subsequent visit by candidate now unlocks community completely
        status, data = self._req(
            "/api/community/detail?id=comm_priv_gap",
            method="GET",
            token=TOKEN_CANDIDATE
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("campus", {}).get("id"), "comm_priv_gap")
        self.assertTrue(data.get("campus", {}).get("is_joined"))

        # 5. Replay approval on already approved request -> 409
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": target_req["id"], "action": "approve"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(data.get("error"), "REQUEST_ALREADY_REVIEWED")

    def test_join_request_replay_and_security(self):
        # 1. Approved replay: insert pending, approve it, then replay
        conn = server.get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES ('u_replay_user', 'replay@test.com', 'replay_user', 'Replay User', 'h', 's', 'Campus Gap', 'student', 1, 1, 'active')")
            req_app_id = "req_test_app_replay"
            cur.execute("DELETE FROM community_join_requests WHERE community_id = 'comm_priv_gap' AND user_id = 'u_replay_user'")
            cur.execute("DELETE FROM community_members WHERE community_id = 'comm_priv_gap' AND user_id = 'u_replay_user'")
            cur.execute("INSERT INTO community_join_requests (id, community_id, user_id, status) VALUES (?, 'comm_priv_gap', 'u_replay_user', 'pending')", (req_app_id,))
            conn.commit()
        finally:
            conn.close()

        # Approve first time -> 200
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_app_id, "action": "approve"}
        )
        self.assertEqual(status, 200)

        # Count notifications
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = 'u_replay_user'")
        notif_count_before = cur.fetchone()[0]
        conn.close()

        # Replay approval on already approved -> 409 REQUEST_ALREADY_REVIEWED
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_app_id, "action": "approve"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(data.get("error"), "REQUEST_ALREADY_REVIEWED")

        # Replay rejection on already approved -> 409 REQUEST_ALREADY_REVIEWED
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_app_id, "action": "reject"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(data.get("error"), "REQUEST_ALREADY_REVIEWED")

        # Verify no duplicate notifications were created
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = 'u_replay_user'")
        notif_count_after = cur.fetchone()[0]
        conn.close()
        self.assertEqual(notif_count_after, notif_count_before)

        # 2. Rejected replay: insert pending, reject it, then replay
        conn = server.get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES ('u_reject_user', 'reject@test.com', 'reject_user', 'Reject User', 'h', 's', 'Campus Gap', 'student', 1, 1, 'active')")
            req_rej_id = "req_test_rej_replay"
            cur.execute("DELETE FROM community_join_requests WHERE community_id = 'comm_priv_gap' AND user_id = 'u_reject_user'")
            cur.execute("INSERT INTO community_join_requests (id, community_id, user_id, status) VALUES (?, 'comm_priv_gap', 'u_reject_user', 'pending')", (req_rej_id,))
            conn.commit()
        finally:
            conn.close()

        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_rej_id, "action": "reject"}
        )
        self.assertEqual(status, 200)

        # Replay rejection on already rejected -> 409 REQUEST_ALREADY_REVIEWED
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_rej_id, "action": "reject"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(data.get("error"), "REQUEST_ALREADY_REVIEWED")

        # Replay approval on already rejected -> 409 REQUEST_ALREADY_REVIEWED
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_rej_id, "action": "approve"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(data.get("error"), "REQUEST_ALREADY_REVIEWED")

        # 3. Unauthorized review: member and visitor cannot review
        conn = server.get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES ('u_auth_user', 'authuser@test.com', 'auth_user', 'Auth User', 'h', 's', 'Campus Gap', 'student', 1, 1, 'active')")
            req_auth_id = "req_test_auth_check"
            cur.execute("DELETE FROM community_join_requests WHERE community_id = 'comm_priv_gap' AND user_id = 'u_auth_user'")
            cur.execute("INSERT INTO community_join_requests (id, community_id, user_id, status) VALUES (?, 'comm_priv_gap', 'u_auth_user', 'pending')", (req_auth_id,))
            conn.commit()
        finally:
            conn.close()

        # Regular member gets 403
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MEMBER,
            body={"community_id": "comm_priv_gap", "request_id": req_auth_id, "action": "approve"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "FORBIDDEN")

        # Visitor gets 403
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_VISITOR,
            body={"community_id": "comm_priv_gap", "request_id": req_auth_id, "action": "approve"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "FORBIDDEN")

        # 4. Cross-Community request ID:
        # req_auth_id belongs to comm_priv_gap; trying to review with comm_pub_gap returns 404
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "request_id": req_auth_id, "action": "approve"}
        )
        self.assertEqual(status, 404)
        self.assertEqual(data.get("code"), "REQUEST_NOT_FOUND")

        # 5. Double review / replay safety:
        conn = server.get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT OR IGNORE INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES ('u_double_user', 'double@test.com', 'double_user', 'Double User', 'h', 's', 'Campus Gap', 'student', 1, 1, 'active')")
            req_dbl_id = "req_test_double_review"
            cur.execute("DELETE FROM community_join_requests WHERE community_id = 'comm_priv_gap' AND user_id = 'u_double_user'")
            cur.execute("DELETE FROM community_members WHERE community_id = 'comm_priv_gap' AND user_id = 'u_double_user'")
            cur.execute("INSERT INTO community_join_requests (id, community_id, user_id, status) VALUES (?, 'comm_priv_gap', 'u_double_user', 'pending')", (req_dbl_id,))
            conn.commit()
        finally:
            conn.close()

        # First review attempt succeeds
        status1, data1 = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_dbl_id, "action": "approve"}
        )
        self.assertEqual(status1, 200)

        # Immediate second review attempt fails with 409 REQUEST_ALREADY_REVIEWED
        status2, data2 = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_priv_gap", "request_id": req_dbl_id, "action": "approve"}
        )
        self.assertEqual(status2, 409)
        self.assertEqual(data2.get("error"), "REQUEST_ALREADY_REVIEWED")

        # Verify only 1 notification was dispatched to u_double_user
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = 'u_double_user'")
        notif_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM community_members WHERE community_id = 'comm_priv_gap' AND user_id = 'u_double_user'")
        member_count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(notif_count, 1, "Exactly one notification must be generated")
        self.assertEqual(member_count, 1, "User must only be added as member once")

    # -------------------------------------------------------------------------
    # Requirement D: Collective Memory Management
    # -------------------------------------------------------------------------
    def test_collective_memory_curate_and_safe_delete(self):
        # 1. Publish collective memory with theme and year
        status, data = self._req(
            "/api/community/memories/publish",
            method="POST",
            token=TOKEN_OWNER,
            body={
                "community_id": "comm_pub_gap",
                "title": "Spring Festival 2026",
                "story": "Celebration on campus",
                "theme": "Campus Festival",
                "year": "2026",
                "moment_ids": ["post_pub_1"]
            }
        )
        self.assertEqual(status, 201)
        mem = data.get("memory", {})
        mem_id = mem.get("id")
        self.assertTrue(mem_id)
        self.assertEqual(mem.get("theme"), "Campus Festival")
        self.assertEqual(mem.get("year"), "2026")

        # 2. Curate collective memory (edit)
        status, data = self._req(
            "/api/community/memories/curate",
            method="POST",
            token=TOKEN_MOD,
            body={
                "memory_id": mem_id,
                "title": "Spring Festival 2026 - Extended",
                "theme": "Festival & Arts"
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("memory", {}).get("title"), "Spring Festival 2026 - Extended")
        self.assertEqual(data.get("memory", {}).get("theme"), "Festival & Arts")

        # 3. Delete collective memory safely
        status, data = self._req(
            "/api/community/memories/delete",
            method="POST",
            token=TOKEN_MOD,
            body={"memory_id": mem_id}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

        # Verify memory deleted but underlying post 'post_pub_1' remains intact in posts
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM collective_memories WHERE id = ?", (mem_id,))
        self.assertIsNone(cur.fetchone())
        cur.execute("SELECT 1 FROM posts WHERE id = 'post_pub_1'")
        self.assertIsNotNone(cur.fetchone(), "Underlying post in posts table must NOT be deleted!")
        conn.close()

    # -------------------------------------------------------------------------
    # Requirement E: Real Activity Metrics
    # -------------------------------------------------------------------------
    def test_community_activity_counts_real_db(self):
        status, data = self._req("/api/community/manage?community_id=comm_pub_gap", token=TOKEN_OWNER)
        self.assertEqual(status, 200)
        comm = data.get("community", {})
        self.assertIn("members_count", comm)
        self.assertIn("moderators_count", comm)
        self.assertIn("pending_reports_count", comm)
        self.assertIn("pending_join_requests_count", comm)
        self.assertIn("recent_moments_count", comm)
        self.assertGreaterEqual(comm.get("recent_moments_count", 0), 1)

    # -------------------------------------------------------------------------
    # Requirement F: Ownership Continuity & Safe Account Deletion
    # -------------------------------------------------------------------------
    def test_transfer_ownership(self):
        # Mod cannot transfer
        status, _ = self._req(
            "/api/community/transfer-ownership",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "new_owner_user_id": "u_mod_gap", "confirmation": "TRANSFER"}
        )
        self.assertEqual(status, 403)

        # Requires confirmation string 'TRANSFER'
        status, data = self._req(
            "/api/community/transfer-ownership",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "new_owner_user_id": "u_mod_gap", "confirmation": "WRONG"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CONFIRMATION_REQUIRED")

        # Owner transfers to mod
        status, data = self._req(
            "/api/community/transfer-ownership",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_pub_gap", "new_owner_user_id": "u_mod_gap", "confirmation": "TRANSFER"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

        # Verify new owner in DB
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT creator_id FROM communities WHERE id = 'comm_pub_gap'")
        self.assertEqual(cur.fetchone()[0], "u_mod_gap")
        conn.close()

        # Transfer back to owner for subsequent tests
        self._req(
            "/api/community/transfer-ownership",
            method="POST",
            token=TOKEN_MOD,
            body={"community_id": "comm_pub_gap", "new_owner_user_id": "u_owner_gap", "confirmation": "TRANSFER"}
        )

    def test_controlled_community_closure(self):
        # Close requires confirmation 'CLOSE'
        status, data = self._req(
            "/api/community/close",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_priv_gap", "confirmation": "NO"}
        )
        self.assertEqual(status, 400)

        # Owner closes community
        status, data = self._req(
            "/api/community/close",
            method="POST",
            token=TOKEN_OWNER,
            body={"community_id": "comm_priv_gap", "confirmation": "CLOSE", "reason": "End of semester"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT status, moderation_status FROM communities WHERE id = 'comm_priv_gap'")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "closed")
        self.assertEqual(row[1], "archived")

    def test_safe_account_deletion_blocks_if_active_owner(self):
        # u_owner_gap owns active community comm_pub_gap which has other members
        status, data = self._req(
            "/api/user/delete-account",
            method="POST",
            token=TOKEN_OWNER,
            body={"confirmation": "DELETE"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CANNOT_DELETE_ACCOUNT_OWNS_COMMUNITIES")


TOKEN_INV_OWNER = "tok_inv_owner_sec"
TOKEN_INV_MOD = "tok_inv_mod_sec"
TOKEN_INV_MEMBER = "tok_inv_member_sec"
TOKEN_INV_OUTSIDER = "tok_inv_outsider_sec"
TOKEN_INV_CAND2 = "tok_inv_cand2_sec"


class TestPrivateCommunityInvitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_inv_test_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_inv_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()

        # Users
        users = [
            ("u_inv_owner", "inv_owner@test.com", "inv_owner", "Inv Owner", "student"),
            ("u_inv_mod", "inv_mod@test.com", "inv_mod", "Inv Mod", "student"),
            ("u_inv_member", "inv_member@test.com", "inv_member", "Inv Member", "student"),
            ("u_inv_outsider", "inv_outsider@test.com", "inv_outsider", "Inv Outsider", "student"),
            ("u_inv_cand2", "candidate2@test.com", "candidate_two", "Candidate Two", "student"),
        ]
        for uid, email, handle, name, role in users:
            cursor.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded, account_status) VALUES (?, ?, ?, ?, 'h', 's', 'Campus Inv', ?, 1, 1, 'active')",
                (uid, email, handle, name, role),
            )

        # Sessions
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_inv_o", "u_inv_owner", TOKEN_INV_OWNER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_inv_m", "u_inv_mod", TOKEN_INV_MOD, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_inv_mem", "u_inv_member", TOKEN_INV_MEMBER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_inv_out", "u_inv_outsider", TOKEN_INV_OUTSIDER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_inv_c2", "u_inv_cand2", TOKEN_INV_CAND2, "2099-01-01T00:00:00Z"))

        # Communities: comm_priv_inv (private), comm_pub_inv (public)
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("comm_priv_inv", "Private Invite Hub", "Interest", "Private enclave for members only", "City Inv", "u_inv_owner", "inv_owner", "🔒", "private", 2),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            ("comm_pub_inv", "Public Invite Hub", "Interest", "Public space for everyone", "City Inv", "u_inv_owner", "inv_owner", "🌐", "public", 1),
        )

        # Memberships for comm_priv_inv
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_priv_inv", "u_inv_owner"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_priv_inv", "u_inv_mod"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_priv_inv", "u_inv_member"))

        # Memberships for comm_pub_inv
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_pub_inv", "u_inv_owner"))

        # Private moment inside private community
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, 'https://res.cloudinary.com/test/secret.jpg', 'https://res.cloudinary.com/test/secret_pip.jpg', 'Top secret private moment', 1, 'comm_priv_inv', 'Private Invite Hub', datetime('now', '-1 hours'))
        """, ("post_secret_inv", "u_inv_owner", "inv_owner", "Inv Owner"))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        if os.path.exists(cls._tmpdir):
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _req(self, path, method="GET", token=None, body=None):
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

        t = server.threading.Thread(target=run_handler)
        t.daemon = True
        t.start()

        body_bytes = b""
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")

        req = f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\nCookie: session_token={token}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "Connection: close\r\n\r\n"

        s2.sendall(req.encode("utf-8") + body_bytes)

        resp = b""
        while True:
            chunk = s2.recv(4096)
            if not chunk:
                break
            resp += chunk
        s2.close()
        t.join(timeout=2.0)

        header_part, _, body_part = resp.partition(b"\r\n\r\n")
        lines = header_part.decode("utf-8", errors="replace").split("\r\n")
        status_code = int(lines[0].split(" ")[1]) if lines and " " in lines[0] else 500

        data = {}
        if body_part:
            try:
                data = json.loads(body_part.decode("utf-8"))
            except Exception:
                data = {"raw": body_part.decode("utf-8", errors="replace")}
        return status_code, data

    def test_01_owner_creates_private_invite(self):
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv"}
        )
        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("invite_code"))
        self.assertEqual(data.get("invite", {}).get("max_uses"), 1)
        self.assertEqual(data.get("invite", {}).get("community_id"), "comm_priv_inv")
        self.assertIn("/invite/", data.get("full_invite_url", ""))
        self.__class__.single_use_code = data["invite_code"]

    def test_02_unauthorized_users_cannot_create_private_invite(self):
        # Regular member 403
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_MEMBER,
            body={"community_id": "comm_priv_inv"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "FORBIDDEN")

        # Non-member 403
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OUTSIDER,
            body={"community_id": "comm_priv_inv"}
        )
        self.assertEqual(status, 403)

        # Unauthenticated 401
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=None,
            body={"community_id": "comm_priv_inv"}
        )
        self.assertEqual(status, 401)

    def test_03_preview_endpoint_returns_safe_minimal_metadata(self):
        code = self.__class__.single_use_code
        status, data = self._req(f"/api/invite/preview?code={code}")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("is_valid"))
        comm = data.get("community", {})
        self.assertEqual(comm.get("name"), "Private Invite Hub")
        self.assertTrue(comm.get("is_private"))
        # Security verification: no moments, pulse, memories or members leaked
        self.assertNotIn("moments", comm)
        self.assertNotIn("pulse", comm)
        self.assertNotIn("memories", comm)
        self.assertNotIn("members", comm)
        self.assertNotIn("posts", data)
        self.assertNotIn("secret.jpg", json.dumps(data))

    def test_04_invite_management_endpoint_authorization_and_data(self):
        # Owner can view
        status, data = self._req("/api/community/invites?community_id=comm_priv_inv", token=TOKEN_INV_OWNER)
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        invites = data.get("invites", [])
        self.assertGreaterEqual(len(invites), 1)
        target = [i for i in invites if i["invite_code"] == self.__class__.single_use_code][0]
        self.assertEqual(target["status"], "active")
        self.assertEqual(target["accepted_count"], 0)
        self.assertEqual(target["max_uses"], 1)

        # Moderator can view
        status, data = self._req("/api/community/invites?community_id=comm_priv_inv", token=TOKEN_INV_MOD)
        self.assertEqual(status, 200)

        # Regular member cannot view (403)
        status, data = self._req("/api/community/invites?community_id=comm_priv_inv", token=TOKEN_INV_MEMBER)
        self.assertEqual(status, 403)

        # Outsider cannot view (403)
        status, data = self._req("/api/community/invites?community_id=comm_priv_inv", token=TOKEN_INV_OUTSIDER)
        self.assertEqual(status, 403)

    def test_05_candidate_submits_join_request_with_invite_code(self):
        code = self.__class__.single_use_code
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_OUTSIDER,
            body={"community_id": "comm_priv_inv", "invite_code": code}
        )
        self.assertEqual(status, 201)
        self.assertEqual(data.get("status"), "pending")

        # Verify DB has invite_code stored
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, invite_code, status FROM community_join_requests WHERE community_id = 'comm_priv_inv' AND user_id = 'u_inv_outsider'")
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], code)
        self.assertEqual(row[2], "pending")
        self.__class__.join_request_id = row[0]

    def test_06_pending_request_state_on_refresh(self):
        status, data = self._req("/api/community/detail?id=comm_priv_inv", token=TOKEN_INV_OUTSIDER)
        self.assertEqual(status, 403)
        self.assertEqual(data.get("code"), "COMMUNITY_RESTRICTED")
        self.assertTrue(data.get("has_pending_request"))
        self.assertEqual(data.get("join_request_status"), "pending")

    def test_07_owner_approves_request_and_invite_usage_increments(self):
        req_id = self.__class__.join_request_id
        status, data = self._req(
            "/api/community/join-requests/review",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv", "request_id": req_id, "action": "approve"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))

        # Verify invite accepted_count incremented
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT accepted_count, max_uses FROM community_invites WHERE invite_code = ?", (self.__class__.single_use_code,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], 1)

        # Candidate can now view private community details
        status, data = self._req("/api/community/detail?id=comm_priv_inv", token=TOKEN_INV_OUTSIDER)
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("campus", {}).get("name"), "Private Invite Hub")

    def test_08_invalid_expired_and_revoked_invites_rejected(self):
        # Invalid non-existent code
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": "NONEXISTENT_CODE"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "INVITE_INVALID")

        # Expired invite code
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO community_invites (id, invite_code, inviter_user_id, community_id, expires_at, max_uses, accepted_count, status)
            VALUES ('inv_exp', 'EXPIRED_CODE', 'u_inv_owner', 'comm_priv_inv', '2020-01-01T00:00:00Z', 5, 0, 'active')
        """)
        # Revoked invite code
        cur.execute("""
            INSERT INTO community_invites (id, invite_code, inviter_user_id, community_id, expires_at, max_uses, accepted_count, status)
            VALUES ('inv_rev', 'REVOKED_CODE', 'u_inv_owner', 'comm_priv_inv', '2099-01-01T00:00:00Z', 5, 0, 'revoked')
        """)
        conn.commit()
        conn.close()

        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": "EXPIRED_CODE"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "INVITE_EXPIRED")

        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": "REVOKED_CODE"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "INVITE_REVOKED")

    def test_09_single_use_enforcement(self):
        # Code from test 01 has accepted_count=1 and max_uses=1 -> exhausted
        code = self.__class__.single_use_code
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": code}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "INVITE_MAX_USES")

        # Preview also reports invalid
        status, data = self._req(f"/api/invite/preview?code={code}")
        self.assertEqual(status, 200)
        self.assertFalse(data.get("is_valid"))

    def test_10_cross_community_mismatch_rejected(self):
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_pub_inv"}
        )
        pub_code = data["invite_code"]

        # Using pub_code to join comm_priv_inv
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": pub_code}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "INVITE_COMMUNITY_MISMATCH")

    def test_11_already_member_cannot_use_invite(self):
        # u_inv_outsider was approved and is now active member
        status, data = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_OUTSIDER,
            body={"community_id": "comm_priv_inv"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "ALREADY_MEMBER")

    def test_12_authorized_revocation_immediately_deactivates_invite(self):
        # Create new invite
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv"}
        )
        code = data["invite_code"]

        # Member tries to revoke -> 403
        status, rdata = self._req(
            "/api/community/invites/revoke",
            method="POST",
            token=TOKEN_INV_MEMBER,
            body={"community_id": "comm_priv_inv", "invite_code": code}
        )
        self.assertEqual(status, 403)

        # Owner revokes -> 200
        status, rdata = self._req(
            "/api/community/invites/revoke",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv", "invite_code": code}
        )
        self.assertEqual(status, 200)
        self.assertTrue(rdata.get("success"))

        # Subsequent join request -> 400 INVITE_REVOKED
        status, jdata = self._req(
            "/api/community/join-request",
            method="POST",
            token=TOKEN_INV_CAND2,
            body={"community_id": "comm_priv_inv", "invite_code": code}
        )
        self.assertEqual(status, 400)
        self.assertEqual(jdata.get("code"), "INVITE_REVOKED")

    def test_13_invite_by_username_creates_notification(self):
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv", "target_handle": "candidate_two"}
        )
        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("invited_user", {}).get("handle"), "candidate_two")

        # Verify notification created
        conn = server.get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, type, user_id FROM notifications WHERE user_id = 'u_inv_cand2' AND type = 'community_invite'")
        notif = cur.fetchone()
        conn.close()
        self.assertIsNotNone(notif)

        # Inviting already active member -> 400 ALREADY_MEMBER
        status, data = self._req(
            "/api/invite/create",
            method="POST",
            token=TOKEN_INV_OWNER,
            body={"community_id": "comm_priv_inv", "target_handle": "inv_member"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "ALREADY_MEMBER")


if __name__ == "__main__":
    unittest.main()
