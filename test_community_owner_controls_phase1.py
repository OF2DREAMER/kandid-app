#!/usr/bin/env python3
"""
Test Suite for Kindid Community Owner Controls — Phase 1.
Verifies:
1. Server-authoritative role resolution (owner, moderator, member, visitor).
2. Moderation reports and audit log authorization (owner & moderator pass; member & visitor 403).
3. Moderation actions authorization and hierarchy (moderator can hide/dismiss; cannot suspend owner or mod).
4. Community-scoped owner management (/api/community/manage?community_id=...) strictly for owners.
5. Member role assignment (/api/community/members/role) strictly for owners.
6. Cross-community unauthorized access rejection (anti-IDOR).
7. Permanent exclusion of Community monetization (/api/community/earnings -> 410 Gone).
"""

import os
os.environ["DATABASE_URL"] = ""
os.environ["ENVIRONMENT"] = "development"

import json
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler

TOKEN_OWNER = "tok_test_owner_p1"
TOKEN_MOD = "tok_test_mod_p1"
TOKEN_MEMBER = "tok_test_member_p1"
TOKEN_VISITOR = "tok_test_visitor_p1"
TOKEN_BETA_OWNER = "tok_test_beta_owner_p1"

class TestCommunityOwnerControlsPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_owner_p1_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Test users
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_owner_p1", "owner_p1@test.com", "owner_alpha", "Owner Alpha", "h", "s", "Alpha Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_mod_p1", "mod_p1@test.com", "mod_alpha", "Mod Alpha", "h", "s", "Alpha Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_mod2_p1", "mod2_p1@test.com", "mod2_alpha", "Mod2 Alpha", "h", "s", "Alpha Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_member_p1", "member_p1@test.com", "member_alpha", "Member Alpha", "h", "s", "Alpha Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_visitor_p1", "visitor_p1@test.com", "visitor_alpha", "Visitor Alpha", "h", "s", "Other Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_beta_owner_p1", "beta_p1@test.com", "owner_beta", "Owner Beta", "h", "s", "Beta Campus", "student"),
        )

        # 2. Test sessions
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_o1", "u_owner_p1", TOKEN_OWNER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_m1", "u_mod_p1", TOKEN_MOD, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_mem1", "u_member_p1", TOKEN_MEMBER, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_v1", "u_visitor_p1", TOKEN_VISITOR, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_bo1", "u_beta_owner_p1", TOKEN_BETA_OWNER, "2099-01-01T00:00:00Z"))

        # 3. Test communities
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_alpha", "Alpha Community", "Campus", "Main community alpha", "City Alpha", "u_owner_p1", "owner_alpha", "🎓", "public", 3),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_beta", "Beta Community", "Interest", "Separate space beta", "City Beta", "u_beta_owner_p1", "owner_beta", "🎨", "public", 1),
        )

        # 4. Set memberships
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_alpha", "u_owner_p1"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_alpha", "u_mod_p1"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'moderator', 'active')", ("comm_alpha", "u_mod2_p1"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_alpha", "u_member_p1"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_beta", "u_beta_owner_p1"))

        # 5. Test post in comm_alpha
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Alpha Community', ?)
        """, ("post_alpha_1", "u_member_p1", "member_alpha", "Member Alpha", "https://img.test/p1.jpg", "https://img.test/pip1.jpg", "Alpha campus spot", "comm_alpha", now_iso))

        # 6. Test safety report in comm_alpha
        cursor.execute("""
            INSERT INTO community_reports (id, community_id, reporter_id, target_type, target_id, reason, details, status)
            VALUES (?, ?, ?, 'moment', ?, 'Spam', 'Testing safety desk', 'pending')
        """, ("rep_alpha_1", "comm_alpha", "u_member_p1", "post_alpha_1"))

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
            parsed = json.loads(body_part)
        except Exception:
            parsed = body_part
        return status_code, parsed

    # ------------------------------------------------------------------------
    # 1. Role Resolution
    # ------------------------------------------------------------------------
    def test_01_role_resolution(self):
        conn = server.get_db()
        cursor = conn.cursor()

        self.assertEqual(server.get_user_community_role("comm_alpha", "u_owner_p1", cursor), "owner")
        self.assertEqual(server.get_user_community_role("comm_alpha", "u_mod_p1", cursor), "moderator")
        self.assertEqual(server.get_user_community_role("comm_alpha", "u_member_p1", cursor), "member")
        self.assertIsNone(server.get_user_community_role("comm_alpha", "u_visitor_p1", cursor))

        # Suspended user resolution
        cursor.execute("INSERT OR REPLACE INTO community_suspensions (id, community_id, user_id, reason) VALUES ('susp_t1', 'comm_alpha', 'u_member_p1', 'test')")
        self.assertIsNone(server.get_user_community_role("comm_alpha", "u_member_p1", cursor))
        cursor.execute("DELETE FROM community_suspensions WHERE id = 'susp_t1'")
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------------
    # 2. Moderation Reports Authorization
    # ------------------------------------------------------------------------
    def test_02_moderation_reports_access(self):
        # Owner can access
        code, body = self._req("/api/community/moderation/reports?community_id=comm_alpha", token=TOKEN_OWNER)
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))
        self.assertGreaterEqual(body.get("reports_count", 0), 1)

        # Moderator can access
        code, body = self._req("/api/community/moderation/reports?community_id=comm_alpha", token=TOKEN_MOD)
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))

        # Member is blocked (403)
        code, body = self._req("/api/community/moderation/reports?community_id=comm_alpha", token=TOKEN_MEMBER)
        self.assertEqual(code, 403)

        # Visitor is blocked (403)
        code, body = self._req("/api/community/moderation/reports?community_id=comm_alpha", token=TOKEN_VISITOR)
        self.assertEqual(code, 403)

        # Cross-community IDOR rejected (Owner of comm_beta cannot view comm_alpha reports)
        code, body = self._req("/api/community/moderation/reports?community_id=comm_alpha", token=TOKEN_BETA_OWNER)
        self.assertEqual(code, 403)

    # ------------------------------------------------------------------------
    # 3. Moderation Audit Log Authorization
    # ------------------------------------------------------------------------
    def test_03_moderation_audit_access(self):
        # Owner can access
        code, body = self._req("/api/community/moderation/audit?community_id=comm_alpha", token=TOKEN_OWNER)
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))

        # Moderator can access
        code, body = self._req("/api/community/moderation/audit?community_id=comm_alpha", token=TOKEN_MOD)
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))

        # Member is blocked (403)
        code, body = self._req("/api/community/moderation/audit?community_id=comm_alpha", token=TOKEN_MEMBER)
        self.assertEqual(code, 403)

        # Visitor is blocked (403)
        code, body = self._req("/api/community/moderation/audit?community_id=comm_alpha", token=TOKEN_VISITOR)
        self.assertEqual(code, 403)

        # Cross-community IDOR rejected
        code, body = self._req("/api/community/moderation/audit?community_id=comm_alpha", token=TOKEN_BETA_OWNER)
        self.assertEqual(code, 403)

    # ------------------------------------------------------------------------
    # 4. Moderation Actions & Role Hierarchy
    # ------------------------------------------------------------------------
    def test_04_moderation_actions_and_hierarchy(self):
        # Moderator can hide moment in community
        code, body = self._req("/api/community/moderation/action", method="POST", token=TOKEN_MOD, body={
            "community_id": "comm_alpha",
            "action": "hide",
            "target_type": "moment",
            "target_id": "post_alpha_1"
        })
        self.assertEqual(code, 200)

        # Moderator CANNOT suspend community owner (blocked with 400 CANNOT_SUSPEND_OWNER)
        code, body = self._req("/api/community/moderation/action", method="POST", token=TOKEN_MOD, body={
            "community_id": "comm_alpha",
            "action": "suspend",
            "target_type": "user",
            "target_id": "u_owner_p1"
        })
        self.assertEqual(code, 400)
        self.assertEqual(body.get("code"), "CANNOT_SUSPEND_OWNER")

        # Moderator CANNOT suspend another moderator (blocked with 403 CANNOT_SUSPEND_MODERATOR)
        code, body = self._req("/api/community/moderation/action", method="POST", token=TOKEN_MOD, body={
            "community_id": "comm_alpha",
            "action": "suspend",
            "target_type": "user",
            "target_id": "u_mod2_p1"
        })
        self.assertEqual(code, 403)
        self.assertEqual(body.get("code"), "CANNOT_SUSPEND_MODERATOR")

        # Ordinary member cannot perform moderation action (403)
        code, body = self._req("/api/community/moderation/action", method="POST", token=TOKEN_MEMBER, body={
            "community_id": "comm_alpha",
            "action": "dismiss",
            "report_id": "rep_alpha_1"
        })
        self.assertEqual(code, 403)

        # Cross-community rejection (Moderator of comm_alpha cannot act on comm_beta)
        code, body = self._req("/api/community/moderation/action", method="POST", token=TOKEN_MOD, body={
            "community_id": "comm_beta",
            "action": "dismiss",
            "report_id": "rep_alpha_1"
        })
        self.assertEqual(code, 403)

    # ------------------------------------------------------------------------
    # 5. Community-Scoped Owner Management (/api/community/manage)
    # ------------------------------------------------------------------------
    def test_05_community_scoped_owner_manage(self):
        # Owner can access scoped community manage
        code, body = self._req("/api/community/manage?community_id=comm_alpha", token=TOKEN_OWNER)
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))
        comm = body.get("community", {})
        self.assertEqual(comm.get("id"), "comm_alpha")
        self.assertEqual(comm.get("role"), "owner")
        self.assertFalse(comm.get("monetization_enabled"))
        self.assertIn("moderators", comm)
        self.assertIsInstance(comm["moderators"], list)
        self.assertGreaterEqual(comm.get("moderators_count", 0), 1)

        # Moderator CANNOT access owner manage (403 OWNER_REQUIRED)
        code, body = self._req("/api/community/manage?community_id=comm_alpha", token=TOKEN_MOD)
        self.assertEqual(code, 403)
        self.assertEqual(body.get("code"), "OWNER_REQUIRED")

        # Member CANNOT access owner manage (403 OWNER_REQUIRED)
        code, body = self._req("/api/community/manage?community_id=comm_alpha", token=TOKEN_MEMBER)
        self.assertEqual(code, 403)

        # Visitor CANNOT access owner manage (403 OWNER_REQUIRED)
        code, body = self._req("/api/community/manage?community_id=comm_alpha", token=TOKEN_VISITOR)
        self.assertEqual(code, 403)

        # Cross-community rejection: Owner of comm_beta querying comm_alpha gets 403
        code, body = self._req("/api/community/manage?community_id=comm_alpha", token=TOKEN_BETA_OWNER)
        self.assertEqual(code, 403)

    # ------------------------------------------------------------------------
    # 6. Member Role Assignment (/api/community/members/role)
    # ------------------------------------------------------------------------
    def test_06_member_role_assignment(self):
        # Owner promotes member to moderator
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_OWNER, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_member_p1",
            "role": "moderator"
        })
        self.assertEqual(code, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("role"), "moderator")

        # Verify DB and role resolution updated
        conn = server.get_db()
        cursor = conn.cursor()
        self.assertEqual(server.get_user_community_role("comm_alpha", "u_member_p1", cursor), "moderator")

        # Owner demotes back to member
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_OWNER, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_member_p1",
            "role": "member"
        })
        self.assertEqual(code, 200)
        self.assertEqual(server.get_user_community_role("comm_alpha", "u_member_p1", cursor), "member")
        conn.close()

        # Moderator CANNOT assign roles (403 OWNER_REQUIRED)
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_MOD, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_member_p1",
            "role": "moderator"
        })
        self.assertEqual(code, 403)
        self.assertEqual(body.get("code"), "OWNER_REQUIRED")

        # Member CANNOT assign roles (403 OWNER_REQUIRED)
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_MEMBER, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_mod_p1",
            "role": "member"
        })
        self.assertEqual(code, 403)

        # Owner cannot demote self or change owner role (400 CANNOT_MODIFY_SELF)
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_OWNER, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_owner_p1",
            "role": "member"
        })
        self.assertEqual(code, 400)
        self.assertEqual(body.get("code"), "CANNOT_MODIFY_SELF")

        # Cross-community rejection (Owner of comm_beta cannot assign roles in comm_alpha)
        code, body = self._req("/api/community/members/role", method="POST", token=TOKEN_BETA_OWNER, body={
            "community_id": "comm_alpha",
            "target_user_id": "u_member_p1",
            "role": "moderator"
        })
        self.assertEqual(code, 403)

    # ------------------------------------------------------------------------
    # 7. Permanent Monetization Exclusion
    # ------------------------------------------------------------------------
    def test_07_permanent_monetization_exclusion(self):
        # /api/community/earnings returns 410 Gone unconditionally
        code, body = self._req("/api/community/earnings", token=TOKEN_OWNER)
        self.assertEqual(code, 410)
        self.assertEqual(body.get("code"), "COMMUNITY_MONETIZATION_EXCLUDED")

        code, body = self._req("/api/community/earnings?community_id=comm_alpha", token=TOKEN_OWNER)
        self.assertEqual(code, 410)
        self.assertEqual(body.get("code"), "COMMUNITY_MONETIZATION_EXCLUDED")

        code, body = self._req("/api/community/earnings?community_id=comm_alpha", token=TOKEN_MOD)
        self.assertEqual(code, 410)

        # /api/creator/dashboard does not return community earnings
        code, body = self._req("/api/creator/dashboard", token=TOKEN_OWNER)
        self.assertEqual(code, 200)
        self.assertNotIn("earnings", body)
        overview = body.get("overview", {})
        self.assertNotIn("earnings", overview)
        self.assertNotIn("gross_volume", overview)

if __name__ == "__main__":
    unittest.main()
