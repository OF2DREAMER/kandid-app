#!/usr/bin/env python3
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

OWNER_TOKEN = "tok_test_owner"
MEMBER_TOKEN = "tok_test_member"
OUTSIDER_TOKEN = "tok_test_outsider"
ADMIN_TOKEN = "tok_test_admin"

class TestCollectiveMemoryV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_cmem_v1_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Create test users
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_owner", "owner@example.test", "owner_curator", "Community Owner", "hash", "salt", "Pub Uni", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_member", "member@example.test", "member_user", "Community Member", "hash", "salt", "Pub Uni", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_outsider", "outsider@example.test", "outsider_user", "Outsider User", "hash", "salt", "Other Campus", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_admin", "admin@example.test", "admin_user", "Global Admin", "hash", "salt", "HQ", "admin"),
        )

        # 2. Create test sessions
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_1", "u_owner", OWNER_TOKEN, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_2", "u_member", MEMBER_TOKEN, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_3", "u_outsider", OUTSIDER_TOKEN, "2099-01-01T00:00:00Z"))
        cursor.execute("INSERT INTO sessions (id, user_id, token, expires_at) VALUES (?, ?, ?, ?)", ("s_4", "u_admin", ADMIN_TOKEN, "2099-01-01T00:00:00Z"))

        # 3. Create test communities (1 public, 1 private, 1 other, 1 duplicate same-name community)
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_pub_1", "Campus Photography", "Interest", "Shots of campus life", "City", "u_owner", "owner_curator", "📸", "public", 5),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_priv_1", "Secret Architecture Circle", "Interest", "Private studio projects", "City", "u_owner", "owner_curator", "🏛️", "private", 2),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_other_1", "Other Campus Lab", "Place", "Lab spaces", "Other City", "u_outsider", "outsider_user", "🔬", "public", 1),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, description, city, creator_id, creator_handle, icon, visibility, members_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("comm_pub_2_other", "City B Photography", "Interest", "Separate space in City B", "Other City", "u_outsider", "outsider_user", "📸", "public", 1),
        )

        # 4. Set memberships
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_pub_1", "u_owner"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_pub_1", "u_member"))

        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_priv_1", "u_owner"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')", ("comm_priv_1", "u_member"))

        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_other_1", "u_outsider"))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", ("comm_pub_2_other", "u_outsider"))

        # 5. Create test posts in communities
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Campus Photography', ?)
        """, ("post_pub_1", "u_owner", "owner_curator", "Community Owner", "https://img.test/p1.jpg", "https://img.test/pip1.jpg", "Morning golden hour at the quad", "comm_pub_1", now_iso))

        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Campus Photography', ?)
        """, ("post_pub_2", "u_member", "member_user", "Community Member", "https://img.test/p2.jpg", "https://img.test/pip2.jpg", "Campus library stairs view", "comm_pub_1", now_iso))

        # Perspective post for post_pub_1 in a cluster
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Campus Photography', ?)
        """, ("post_pub_1_persp", "u_member", "member_user", "Community Member", "https://img.test/p1_persp.jpg", "https://img.test/pip3.jpg", "Different angle of the morning quad", "comm_pub_1", now_iso))

        cursor.execute("""
            INSERT INTO moment_clusters (id, originator_moment_id, originator_user_id, community_id, cluster_type, created_at)
            VALUES (?, ?, ?, ?, 'context', ?)
        """, ("cls_pub_1", "post_pub_1", "u_owner", "comm_pub_1", now_iso))

        cursor.execute("UPDATE posts SET cluster_id = ? WHERE id = ?", ("cls_pub_1", "post_pub_1"))

        cursor.execute("""
            INSERT INTO moment_cluster_members (id, cluster_id, user_id, moment_id, participation_type, joined_at)
            VALUES (?, ?, ?, ?, 'perspective', ?)
        """, ("mcm_1", "cls_pub_1", "u_member", "post_pub_1_persp", now_iso))

        # Post in private community
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Secret Architecture Circle', ?)
        """, ("post_priv_1", "u_owner", "owner_curator", "Community Owner", "https://img.test/priv1.jpg", "https://img.test/pippriv1.jpg", "Confidential studio mockup", "comm_priv_1", now_iso))

        # Post in other community
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Other Campus Lab', ?)
        """, ("post_other_1", "u_outsider", "outsider_user", "Outsider User", "https://img.test/oth1.jpg", "https://img.test/pipoth1.jpg", "Robotics lab build", "comm_other_1", now_iso))

        # Post in different community B but with campus name set to 'Campus Photography'
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'Campus Photography', ?)
        """, ("post_samename_b", "u_outsider", "outsider_user", "Outsider User", "https://img.test/sameb.jpg", "https://img.test/pipsameb.jpg", "City B photography walk", "comm_pub_2_other", now_iso))

        # Private personal post with matching campus name
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, '', 'Campus Photography', ?)
        """, ("post_personal_priv", "u_owner", "owner_curator", "Community Owner", "https://img.test/pers_priv.jpg", "https://img.test/pippers.jpg", "Private journal entry", now_iso))

        # Post with conflicting context_community_id
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, context_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'comm_other_1', 'comm_other_1', 'Campus Photography', ?)
        """, ("post_conflict_context", "u_owner", "owner_curator", "Community Owner", "https://img.test/conf.jpg", "https://img.test/pipconf.jpg", "Conflicting context post", now_iso))

        # Safe legacy public moment with no community IDs
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, context_community_id, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '', 'Campus Photography', ?)
        """, ("post_legacy_pub", "u_owner", "owner_curator", "Community Owner", "https://img.test/leg.jpg", "https://img.test/pipleg.jpg", "Legacy quad sunset", now_iso))

        # Moderated post in comm_pub_1
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, is_private, primary_community_id, moderation_status, campus, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'comm_pub_1', 'removed', 'Campus Photography', ?)
        """, ("post_mod_removed", "u_owner", "owner_curator", "Community Owner", "https://img.test/mod.jpg", "https://img.test/pipmod.jpg", "Spam post", now_iso))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        if os.path.exists(cls._tmpdir):
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, token=None, method="GET", body=None):
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

    def test_01_schema_initialization_collective_memory_moments(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(collective_memory_moments)")
        cols = {row[1] for row in cursor.fetchall()}
        self.assertIn("id", cols)
        self.assertIn("memory_id", cols)
        self.assertIn("moment_id", cols)
        self.assertIn("sort_order", cols)
        self.assertIn("created_at", cols)
        conn.close()

    def test_02_publish_unauthenticated_returns_401(self):
        status, data = self._request("/api/community/memories/publish", method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Quad Golden Hour Archive",
            "moment_ids": ["post_pub_1"]
        })
        self.assertEqual(status, 401)
        self.assertFalse(data.get("success"))

    def test_03_publish_unauthorized_member_returns_403(self):
        # Regular member (not owner/admin) cannot publish
        status, data = self._request("/api/community/memories/publish", token=MEMBER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Member Attempt Archive",
            "moment_ids": ["post_pub_1"]
        })
        self.assertEqual(status, 403)
        self.assertFalse(data.get("success"))

    def test_04_publish_outsider_returns_403(self):
        status, data = self._request("/api/community/memories/publish", token=OUTSIDER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Outsider Archive",
            "moment_ids": ["post_pub_1"]
        })
        self.assertEqual(status, 403)

    def test_05_publish_cross_community_moment_rejected(self):
        # Owner of comm_pub_1 tries to include a moment from comm_other_1
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Cross Community Attempt",
            "moment_ids": ["post_pub_1", "post_other_1"]
        })
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CROSS_COMMUNITY_MOMENT")

    def test_06_publish_missing_or_empty_moments_rejected(self):
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Empty Moments Archive",
            "moment_ids": []
        })
        self.assertEqual(status, 400)

    def test_07_publish_success_by_owner_with_multiple_moments(self):
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "First Semester Highlights 2026",
            "story": "A collection of beautiful campus moments captured together.",
            "moment_ids": ["post_pub_1", "post_pub_2", "post_pub_1"] # Contains dupe to test deduplication
        })

        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("moments_count"), 2)
        memory = data.get("memory", {})
        self.assertTrue(memory.get("id", "").startswith("mem_"))
        self.assertEqual(memory.get("title"), "First Semester Highlights 2026")
        self.assertEqual(memory.get("community_id"), "comm_pub_1")

        # Save ID for detail testing
        self.__class__.published_pub_memory_id = memory["id"]

    def test_08_memory_detail_retrieval_and_perspectives_linking(self):
        mem_id = getattr(self.__class__, "published_pub_memory_id", None)
        self.assertIsNotNone(mem_id)

        # Public memory detail accessible to unauthenticated visitor
        status, data = self._request(f"/api/community/memories/detail?id={mem_id}", method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["memory"]["title"], "First Semester Highlights 2026")

        moments = data.get("moments", [])
        self.assertEqual(len(moments), 2)
        m1 = next(m for m in moments if m["id"] == "post_pub_1")
        self.assertEqual(m1["perspectives_count"], 1)
        self.assertEqual(len(m1["perspectives"]), 1)
        self.assertEqual(m1["perspectives"][0]["id"], "post_pub_1_persp")

    def test_09_private_community_memory_authorization(self):
        # 1. Publish memory in private community by owner
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_priv_1",
            "title": "Confidential Architecture Exhibition",
            "story": "Private works in progress",
            "moment_ids": ["post_priv_1"]
        })
        self.assertEqual(status, 201)
        priv_mem_id = data["memory"]["id"]

        # 2. Unauthenticated visitor cannot view private memory -> 401
        status, _ = self._request(f"/api/community/memories/detail?id={priv_mem_id}", method="GET")
        self.assertEqual(status, 401)

        # 3. Non-member outsider cannot view private memory -> 403
        status, _ = self._request(f"/api/community/memories/detail?id={priv_mem_id}", token=OUTSIDER_TOKEN, method="GET")
        self.assertEqual(status, 403)

        # 4. Authorized private community member can view private memory -> 200
        status, res_data = self._request(f"/api/community/memories/detail?id={priv_mem_id}", token=MEMBER_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(res_data.get("success"))
        self.assertEqual(len(res_data.get("moments", [])), 1)

    def test_10_admin_can_publish_and_view_any_community_memory(self):
        status, data = self._request("/api/community/memories/publish", token=ADMIN_TOKEN, method="POST", body={
            "community_id": "comm_other_1",
            "title": "Admin Curated Lab Archive",
            "moment_ids": ["post_other_1"]
        })
        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))

    def test_11_reject_moment_from_same_name_different_community_id(self):
        # Even though campus name is 'Campus Photography', post_samename_b has primary_community_id='comm_pub_2_samename'
        # Publishing it into comm_pub_1 must be rejected.
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Same Name Conflict Attempt",
            "moment_ids": ["post_samename_b"]
        })
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CROSS_COMMUNITY_MOMENT")

    def test_12_reject_private_personal_post_with_matching_campus_name(self):
        # Personal private post (is_private=1) cannot be archived even if campus matches
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Private Personal Post Archive Attempt",
            "moment_ids": ["post_personal_priv"]
        })
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "PRIVATE_MOMENT_RESTRICTED")

    def test_13_reject_post_with_conflicting_context_community_id(self):
        # Post has context_community_id='comm_other_1'
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Conflicting Context Attempt",
            "moment_ids": ["post_conflict_context"]
        })
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "CROSS_COMMUNITY_MOMENT")

    def test_14_accept_safe_legacy_public_moment_with_no_community_id(self):
        # Public moment (is_private=0) with no community IDs and matching campus name should be accepted
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Legacy Quad Moments",
            "story": "Historic campus moments",
            "moment_ids": ["post_legacy_pub"]
        })
        self.assertEqual(status, 201)
        self.assertTrue(data.get("success"))

    def test_15_reject_moderated_moment(self):
        # Moderated / removed moment should be rejected
        status, data = self._request("/api/community/memories/publish", token=OWNER_TOKEN, method="POST", body={
            "community_id": "comm_pub_1",
            "title": "Moderated Post Attempt",
            "moment_ids": ["post_mod_removed"]
        })
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "MOMENT_MODERATED")

if __name__ == "__main__":
    unittest.main()
