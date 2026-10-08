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
import uuid
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler

USER1_TOKEN = "tok_test_user1_att"
USER2_TOKEN = "tok_test_user2_att"
USER3_TOKEN = "tok_test_user3_att"
USER4_TOKEN = "tok_test_user4_att"

class TestIWasTherePerspective(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_i_was_there_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_test.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        # Create test users
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_att1", "att1@example.test", "att1_handle", "Attendee One", "hash", "salt", "North City University", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_att2", "att2@example.test", "att2_handle", "Attendee Two", "hash", "salt", "North City University", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_att3", "att3@example.test", "att3_handle", "Attendee Three", "hash", "salt", "North City University", "student"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, email_verified, is_onboarded) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
            ("u_att4", "att4@example.test", "att4_handle", "Attendee Four", "hash", "salt", "North City University", "student"),
        )

        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_att1", USER1_TOKEN, "u_att1", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_att2", USER2_TOKEN, "u_att2", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_att3", USER3_TOKEN, "u_att3", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_att4", USER4_TOKEN, "u_att4", future_iso, now_iso),
        )

        # Create public community
        cls.comm_id = "comm_event_1"
        cursor.execute(
            "INSERT INTO communities (id, name, type, visibility, members_count, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.comm_id, "Campus Festival", "Campus", "public", 3, "u_att1")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')",
            (cls.comm_id, "u_att1")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')",
            (cls.comm_id, "u_att2")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')",
            (cls.comm_id, "u_att3")
        )

        # Create private community (u_att1 is creator, u_att2 is member, u_att4 is NOT a member)
        cls.priv_comm_id = "comm_priv_1"
        cursor.execute(
            "INSERT INTO communities (id, name, type, visibility, members_count, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.priv_comm_id, "Secret Society", "Campus", "private", 2, "u_att1")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'creator', 'active')",
            (cls.priv_comm_id, "u_att1")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')",
            (cls.priv_comm_id, "u_att2")
        )

        # Create primary event moment
        cls.moment_id = "post_event_primary_1"
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, campus, caption, main_img, pip_img, is_private, primary_community_id, moderation_status, created_at)
            VALUES (?, 'u_att1', 'Attendee One', 'att1_handle', 'North City University', 'Festival Opening Moment', '/uploads/main_1.jpg', '/uploads/pip_1.jpg', 0, ?, 'active', ?)
        """, (cls.moment_id, cls.comm_id, now_iso))


        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
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

    def test_01_anonymous_cannot_mark_attendance(self):
        status, res = self._request(f"/api/moment/{self.moment_id}/i-was-there", method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status, 401)
        self.assertFalse(res.get("success"))

    def test_02_anonymous_cannot_create_perspective(self):
        status, res = self._request("/api/moments/capture", method="POST", body={"caption": "Anonymous perspective", "cluster_id": "cls_dummy"})
        self.assertEqual(status, 401)

    def test_03_creator_alone_attendance_count_is_zero(self):
        # Instantiate cluster for the event
        conn = server.get_db()
        cluster = server.create_or_get_moment_cluster(conn, {"id": self.moment_id, "primary_community_id": self.comm_id, "user_id": "u_att1"}, "u_att1")
        cluster_id = cluster["id"]
        conn.close()

        # Before any user taps "I Was There", creator alone exists as participation_type='creator'
        status, res = self._request(f"/api/cluster/{cluster_id}", token=USER1_TOKEN, method="GET")
        self.assertEqual(status, 200)
        cls_obj = res.get("cluster", {})
        # MUST be 0 since creator alone does NOT count as explicit I Was There attendance
        self.assertEqual(cls_obj.get("attendance_count"), 0)
        self.assertFalse(cls_obj.get("is_attended"))

        # In eligibility query, attendance_count must also be 0
        status_elig, res_elig = self._request(f"/api/moment/{self.moment_id}/eligibility", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_elig, 200)
        self.assertEqual(res_elig.get("attendance_count"), 0)
        self.assertFalse(res_elig.get("has_participated"))

    def test_04_one_explicit_i_was_there_and_idempotency(self):
        # 1. User 2 asserts participation
        status, res = self._request(f"/api/moment/{self.moment_id}/i-was-there", token=USER2_TOKEN, method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertFalse(res.get("already_participated"))
        self.assertEqual(res.get("attendance_count"), 1)
        self.assertTrue(res.get("is_attended"))
        cluster_id = res.get("cluster_id")
        self.assertTrue(bool(cluster_id))

        # Check cluster endpoint directly
        status_cls, res_cls = self._request(f"/api/cluster/{cluster_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_cls, 200)
        self.assertEqual(res_cls.get("cluster", {}).get("attendance_count"), 1)
        self.assertTrue(res_cls.get("cluster", {}).get("is_attended"))

        # 2. Duplicate assertion by User 2 (idempotent, no count increase)
        status2, res2 = self._request(f"/api/moment/{self.moment_id}/i-was-there", token=USER2_TOKEN, method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status2, 200)
        self.assertTrue(res2.get("success"))
        self.assertTrue(res2.get("already_participated"))
        self.assertEqual(res2.get("attendance_count"), 1)

    def test_05_perspective_creation_does_not_increase_attendance_count(self):
        # User 2 creates a perspective
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        conn.close()

        body = {
            "caption": "Perspective from User 2",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status_cap, res_cap = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(status_cap, 201)
        self.assertTrue(res_cap.get("success"))

        # Check cluster endpoint: perspectives_count = 1, attendance_count MUST STILL be 1
        status_cls, res_cls = self._request(f"/api/cluster/{cluster_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_cls, 200)
        cls_obj = res_cls.get("cluster", {})
        self.assertEqual(cls_obj.get("attendance_count"), 1)
        self.assertEqual(cls_obj.get("perspectives_count"), 1)
        self.assertTrue(cls_obj.get("is_attended"))

    def test_06_authenticated_user_without_i_was_there_can_create_perspective(self):
        # User 3 has NOT marked attendance for this cluster.
        # User 3 directly adds perspective -> MUST succeed (201)
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        conn.close()

        body = {
            "caption": "Perspective from User 3 without prior I Was There",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER3_TOKEN, method="POST", body=body)
        self.assertEqual(status, 201)
        self.assertTrue(res.get("success"))

        # User 3 does NOT automatically become a participant; attendance_count remains 1 (from User 2)
        status_cls, res_cls = self._request(f"/api/cluster/{cluster_id}", token=USER3_TOKEN, method="GET")
        self.assertEqual(status_cls, 200)
        cls_obj = res_cls.get("cluster", {})
        self.assertEqual(cls_obj.get("attendance_count"), 1)
        self.assertEqual(cls_obj.get("perspectives_count"), 2)
        self.assertFalse(cls_obj.get("is_attended"))  # User 3 has not marked attendance

    def test_07_user_can_later_mark_i_was_there(self):
        # User 3 now marks "I Was There" -> attendance_count increases from 1 to 2
        status, res = self._request(f"/api/moment/{self.moment_id}/i-was-there", token=USER3_TOKEN, method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("attendance_count"), 2)
        self.assertTrue(res.get("is_attended"))
        cluster_id = res["cluster_id"]

        # Check cluster endpoint
        status_cls, res_cls = self._request(f"/api/cluster/{cluster_id}", token=USER3_TOKEN, method="GET")
        self.assertEqual(status_cls, 200)
        cls_obj = res_cls.get("cluster", {})
        self.assertEqual(cls_obj.get("attendance_count"), 2)
        self.assertEqual(cls_obj.get("perspectives_count"), 2)
        self.assertTrue(cls_obj.get("is_attended"))

    def test_08_private_community_membership_restriction_enforced(self):
        # Create moment in private community
        conn = server.get_db()
        cursor = conn.cursor()
        moment_priv_id = "post_priv_event_1"
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, campus, caption, main_img, pip_img, is_private, primary_community_id, moderation_status, created_at)
            VALUES (?, 'u_att1', 'Attendee One', 'att1_handle', 'North City University', 'Private Gathering', '/uploads/main_priv.jpg', '/uploads/pip_priv.jpg', 0, ?, 'active', ?)
        """, (moment_priv_id, self.priv_comm_id, datetime.now().isoformat()))
        conn.commit()

        cluster = server.create_or_get_moment_cluster(conn, {"id": moment_priv_id, "primary_community_id": self.priv_comm_id, "user_id": "u_att1"}, "u_att1")
        cluster_id = cluster["id"]
        conn.close()

        # User 4 is NOT a member of the private community -> rejected with 403 COMMUNITY_RESTRICTED
        body = {
            "caption": "Unauthorized perspective",
            "cluster_id": cluster_id,
            "community_id": self.priv_comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body)
        self.assertEqual(status, 403)
        self.assertIn(res.get("code"), ["COMMUNITY_RESTRICTED", "COMMUNITY_MEMBERSHIP_REQUIRED"])

    def test_09_delete_perspective_preserves_attendance(self):
        # User 3 creates another moment to test isolated deletion
        conn = server.get_db()
        cursor = conn.cursor()
        moment2_id = "post_event_primary_2"
        cursor.execute("""
            INSERT INTO posts (id, user_id, author_name, author_handle, campus, caption, main_img, pip_img, is_private, primary_community_id, moderation_status, created_at)
            VALUES (?, 'u_att1', 'Attendee One', 'att1_handle', 'North City University', 'Concert Moment', '/uploads/main_2.jpg', '/uploads/pip_2.jpg', 0, ?, 'active', ?)
        """, (moment2_id, self.comm_id, datetime.now().isoformat()))
        conn.commit()

        cluster = server.create_or_get_moment_cluster(conn, {"id": moment2_id, "primary_community_id": self.comm_id, "user_id": "u_att1"}, "u_att1")
        cluster_id = cluster["id"]
        conn.close()

        # User 3 marks attendance on moment 2
        status, res = self._request("/api/moment/post_event_primary_2/i-was-there", token=USER3_TOKEN, method="POST", body={"moment_id": "post_event_primary_2"})
        self.assertEqual(status, 200)
        self.assertEqual(res.get("attendance_count"), 1)

        # User 3 creates perspective on moment 2
        body = {
            "caption": "Perspective to delete",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status_cap, res_cap = self._request("/api/moments/capture", token=USER3_TOKEN, method="POST", body=body)
        self.assertEqual(status_cap, 201)
        persp_id = res_cap["post"]["id"]

        # Verify cluster has attendance = 1, perspectives = 1
        status_cls1, res_cls1 = self._request(f"/api/cluster/{cluster_id}", token=USER3_TOKEN, method="GET")
        self.assertEqual(res_cls1.get("cluster", {}).get("attendance_count"), 1)
        self.assertEqual(res_cls1.get("cluster", {}).get("perspectives_count"), 1)

        # Non-author (User 1) deletion attempt is rejected with 403
        status_unauth, _ = self._request("/api/moments/delete", token=USER1_TOKEN, method="POST", body={"postId": persp_id})
        self.assertEqual(status_unauth, 403)

        # Author (User 3) deletes perspective
        status_del, res_del = self._request("/api/moments/delete", token=USER3_TOKEN, method="POST", body={"postId": persp_id})
        self.assertEqual(status_del, 200)
        self.assertTrue(res_del.get("success"))

        # Verify cluster perspectives = 0, BUT attendance_count STILL = 1 and user STILL attended
        status_cls2, res_cls2 = self._request(f"/api/cluster/{cluster_id}", token=USER3_TOKEN, method="GET")
        self.assertEqual(status_cls2, 200)
        cls_obj2 = res_cls2.get("cluster", {})
        self.assertEqual(cls_obj2.get("attendance_count"), 1)
        self.assertEqual(cls_obj2.get("perspectives_count"), 0)
        self.assertTrue(cls_obj2.get("is_attended"))

    def test_10_perspective_blocked_for_nonexistent_cluster(self):
        body = {
            "caption": "Nonexistent cluster perspective",
            "cluster_id": "cls_nonexistent_99999",
            "community_id": self.comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(status, 404)
        self.assertEqual(res.get("code"), "CLUSTER_NOT_FOUND")

    def test_11_perspective_excluded_from_feed_and_community_recent(self):
        # 1. Verify Feed does NOT contain public community moment (strict Community -> Feed isolation)
        status_feed, res_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed, 200)
        feed_moment_ids = [m["id"] for m in res_feed.get("feed", [])]
        self.assertNotIn(self.moment_id, feed_moment_ids)

        # 2. Create a perspective for the primary moment cluster
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        conn.close()

        body = {
            "caption": "Perspective for Feed Isolation Test",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status_cap, res_cap = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(status_cap, 201)
        persp_post_id = res_cap["post"]["id"]

        # 3. Verify Feed does NOT contain the perspective post or the community moment
        status_feed2, res_feed2 = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed2, 200)
        feed_moment_ids2 = [m["id"] for m in res_feed2.get("feed", [])]
        self.assertNotIn(persp_post_id, feed_moment_ids2)
        self.assertNotIn(self.moment_id, feed_moment_ids2)

        # 4. Verify Perspective is visible inside the Cluster modal/endpoint
        status_cls, res_cls = self._request(f"/api/cluster/{cluster_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_cls, 200)
        persp_ids = [p["id"] for p in res_cls.get("cluster", {}).get("perspectives", [])]
        self.assertIn(persp_post_id, persp_ids)

        # 5. Verify Community detail moments contains primary moment and does NOT contain perspective
        status_comm, res_comm = self._request(f"/api/community/detail?id={self.comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_comm, 200)
        comm_moment_ids = [m["id"] for m in res_comm.get("moments", [])]
        self.assertIn(self.moment_id, comm_moment_ids)
        self.assertNotIn(persp_post_id, comm_moment_ids)

    def test_12_public_community_non_member_can_create_perspective_without_joining(self):
        # User 4 is NOT a member of public community `comm_event_1`
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        cursor.execute("SELECT 1 FROM community_members WHERE community_id = ? AND user_id = ?", (self.comm_id, "u_att4"))
        self.assertIsNone(cursor.fetchone())
        conn.close()

        body = {
            "caption": "Public Perspective from Non-Member User 4",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body)
        self.assertEqual(status, 201)
        self.assertTrue(res.get("success"))

    def test_13_personal_posts_in_feed_and_community_posts_isolated_from_feed(self):
        # 1. Create ordinary personal post (no cluster, no community)
        body_personal = {
            "caption": "Ordinary Personal Post",
            "community": "Personal (Feed)",
            "circle": "campus"
        }
        status_p, res_p = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=body_personal)
        self.assertEqual(status_p, 201)
        personal_id = res_p["post"]["id"]

        # 2. Create ordinary community post (member posting to community, no cluster)
        body_comm = {
            "caption": "Ordinary Community Post",
            "community_id": self.comm_id,
            "circle": "campus"
        }
        status_c, res_c = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=body_comm)
        self.assertEqual(status_c, 201)
        comm_post_id = res_c["post"]["id"]

        # 3. Verify Feed isolation:
        # Personal post MUST appear in Feed
        # Community post MUST NOT appear in Feed
        status_feed, res_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed, 200)
        feed_ids = [m["id"] for m in res_feed.get("feed", [])]
        self.assertIn(personal_id, feed_ids)
        self.assertNotIn(comm_post_id, feed_ids)

        # 4. Verify Community post MUST appear inside Community detail
        status_comm, res_comm = self._request(f"/api/community/detail?id={self.comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_comm, 200)
        comm_ids = [m["id"] for m in res_comm.get("moments", [])]
        self.assertIn(comm_post_id, comm_ids)

    def test_14_user_can_create_another_perspective_after_deletion(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        conn.close()

        # User 1 creates perspective on own cluster
        body = {
            "caption": "First perspective from User 1",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status1, res1 = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=body)
        self.assertEqual(status1, 201)
        post1_id = res1["post"]["id"]

        # User 1 deletes it
        status_del, _ = self._request("/api/moments/delete", token=USER1_TOKEN, method="POST", body={"postId": post1_id})
        self.assertEqual(status_del, 200)

        # User 1 creates a new perspective on the same cluster -> MUST succeed
        body2 = {
            "caption": "Replacement perspective from User 1",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status2, res2 = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=body2)
        self.assertEqual(status2, 201)

    def test_15_public_community_non_member_cannot_create_ordinary_post(self):
        # 1. Non-member (User 4) tries to post ordinary community post (no cluster_id) -> MUST be 403
        body_non_member_ord = {
            "caption": "Unauthorized ordinary post attempt by non-member",
            "community_id": self.comm_id,
            "circle": "campus"
        }
        status_ord, res_ord = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body_non_member_ord)
        self.assertEqual(status_ord, 403)
        self.assertEqual(res_ord.get("code"), "COMMUNITY_MEMBERSHIP_REQUIRED")

        # 2. Non-member tries to bypass by sending non-existent cluster_id -> MUST be 404
        body_spoof_cls = {
            "caption": "Spoofed cluster_id bypass attempt",
            "community_id": self.comm_id,
            "cluster_id": "cls_invalid_spoof_999",
            "circle": "campus"
        }
        status_spoof, res_spoof = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body_spoof_cls)
        self.assertEqual(status_spoof, 404)
        self.assertEqual(res_spoof.get("code"), "CLUSTER_NOT_FOUND")

    # =========================================================================
    # EXACT 15-CASE TEST MATRIX VERIFICATION (SECTION 17)
    # =========================================================================

    def test_16_matrix_test_1_public_community_non_member_i_was_there_success(self):
        # Test 1: Non-member (User 4) -> I Was There on public event -> 200 success
        status, res = self._request(f"/api/moment/{self.moment_id}/i-was-there", token=USER4_TOKEN, method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("is_attended"))

    def test_17_matrix_test_3_non_member_i_was_there_twice_idempotent(self):
        # Test 3: Non-member (User 4) -> I Was There twice -> idempotent, no duplicate
        status, res = self._request(f"/api/moment/{self.moment_id}/i-was-there", token=USER4_TOKEN, method="POST", body={"moment_id": self.moment_id})
        self.assertEqual(status, 200)
        self.assertTrue(res.get("already_participated"))

        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = ? AND user_id = 'u_att4' AND participation_type = 'participant'", (cluster_id,))
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_18_matrix_test_4_i_was_there_only_no_perspective_created(self):
        # Test 4: I Was There only -> participant record exists, perspective record does NOT exist
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = ? AND user_id = 'u_att4' AND participation_type = 'participant'", (cluster_id,))
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = ? AND user_id = 'u_att4' AND participation_type = 'perspective'", (cluster_id,))
        # User 4 has perspective from test_12, so check on moment2 for User 2 who only marked I Was There
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = (SELECT cluster_id FROM posts WHERE id = 'post_event_primary_2') AND user_id = 'u_att3' AND participation_type = 'participant'", ())
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_19_matrix_test_9_private_community_non_member_i_was_there_blocked(self):
        # Test 9: Private Community Non-member (User 4) -> I Was There -> BLOCKED 403
        status, res = self._request("/api/moment/post_priv_event_1/i-was-there", token=USER4_TOKEN, method="POST", body={"moment_id": "post_priv_event_1"})
        self.assertEqual(status, 403)
        self.assertIn(res.get("code"), ["COMMUNITY_MEMBERSHIP_REQUIRED", "COMMUNITY_RESTRICTED"])

    def test_20_matrix_test_10_private_community_member_i_was_there_allowed(self):
        # Test 10: Private Community Member (User 2) -> I Was There -> ALLOWED 200
        status, res = self._request("/api/moment/post_priv_event_1/i-was-there", token=USER2_TOKEN, method="POST", body={"moment_id": "post_priv_event_1"})
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("is_attended"))

    def test_21_matrix_test_12_private_community_member_perspective_allowed(self):
        # Test 12: Private Community Member (User 2) -> Perspective -> ALLOWED 201
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = 'post_priv_event_1'", ())
        cluster_id = cursor.fetchone()[0]
        conn.close()

        body = {
            "caption": "Authorized private perspective from member User 2",
            "cluster_id": cluster_id,
            "community_id": self.priv_comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(status, 201)
        self.assertTrue(res.get("success"))

    def test_22_matrix_test_14_invalid_cluster_or_moment_id_i_was_there_404(self):
        # Test 14: Invalid cluster/moment id -> I Was There -> 404
        status, res = self._request("/api/moment/post_nonexistent_9999/i-was-there", token=USER2_TOKEN, method="POST", body={"moment_id": "post_nonexistent_9999"})
        self.assertEqual(status, 404)
        status2, res2 = self._request("/api/cluster/cls_nonexistent_9999/i-was-there", token=USER2_TOKEN, method="POST", body={"cluster_id": "cls_nonexistent_9999"})
        self.assertEqual(status2, 404)

    def test_23_matrix_test_15_attendance_count_counts_participants_only(self):
        # Test 15: Attendance count MUST count participation_type='participant' ONLY
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = 'post_priv_event_1'", ())
        cluster_id = cursor.fetchone()[0]
        # In priv cluster:
        # Creator exists (User 1)
        # Participant exists (User 2)
        # Perspective exists (User 2)
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = ? AND participation_type = 'creator'", (cluster_id,))
        creator_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM moment_cluster_members WHERE cluster_id = ? AND participation_type = 'perspective'", (cluster_id,))
        persp_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM moment_cluster_members WHERE cluster_id = ? AND participation_type = 'participant'", (cluster_id,))
        part_cnt = cursor.fetchone()[0]
        self.assertGreaterEqual(creator_cnt, 1)
        self.assertGreaterEqual(persp_cnt, 1)
        self.assertEqual(part_cnt, 1)
        conn.close()

        status, res = self._request(f"/api/cluster/{cluster_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status, 200)
        # attendance_count MUST be exactly part_cnt (1), not 1 + creator_cnt + persp_cnt
        self.assertEqual(res.get("cluster", {}).get("attendance_count"), 1)

    def test_24_public_community_non_member_can_view_detail(self):
        # 1. Non-member (User 4) can view public Community
        status, res = self._request(f"/api/community/detail?id={self.comm_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("campus", {}).get("id"), self.comm_id)

    def test_25_public_community_non_member_can_add_perspective(self):
        # 2. Non-member (User 4) can add Perspective to public cluster
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = ?", (self.moment_id,))
        cluster_id = cursor.fetchone()[0]
        conn.close()

        body = {
            "caption": "Non-member perspective in public event",
            "cluster_id": cluster_id,
            "community_id": self.comm_id
        }
        status, res = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body)
        self.assertEqual(status, 201)
        self.assertTrue(res.get("success"))
        new_post_id = res["post"]["id"]

        # 3. Perspective appears correctly in cluster
        status_c, res_c = self._request(f"/api/cluster/{cluster_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(status_c, 200)
        persp_ids = [p["id"] for p in res_c.get("cluster", {}).get("perspectives", [])]
        self.assertIn(new_post_id, persp_ids)

    def test_26_private_community_member_can_view_detail(self):
        # Private: Member (User 2) can view private Community
        status, res = self._request(f"/api/community/detail?id={self.priv_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("campus", {}).get("id"), self.priv_comm_id)

    def test_27_private_community_non_member_cannot_view_detail(self):
        # Private: Non-member (User 4) CANNOT view private Community
        status, res = self._request(f"/api/community/detail?id={self.priv_comm_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(status, 403)
        self.assertEqual(res.get("code"), "COMMUNITY_RESTRICTED")

        # Unauthenticated also rejected
        status_unauth, res_unauth = self._request(f"/api/community/detail?id={self.priv_comm_id}", method="GET")
        self.assertEqual(status_unauth, 401)

    def test_28_private_community_non_member_cannot_access_cluster_directly(self):
        # Private: Non-member (User 4) CANNOT access private cluster directly via cluster_id
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = 'post_priv_event_1'", ())
        cluster_id = cursor.fetchone()[0]
        conn.close()

        status, res = self._request(f"/api/cluster/{cluster_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(status, 403)
        self.assertEqual(res.get("code"), "COMMUNITY_RESTRICTED")

    def test_29_private_community_non_member_cannot_capture_perspective_with_cluster_id(self):
        # Private: Non-member (User 4) CANNOT create perspective using known/guessed cluster_id
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts WHERE id = 'post_priv_event_1'", ())
        cluster_id = cursor.fetchone()[0]
        conn.close()

        # UI bypass attempt: sends cluster_id with or without community_id
        body_bypass = {
            "caption": "Hostile perspective injected into private cluster by non-member",
            "cluster_id": cluster_id
        }
        status, res = self._request("/api/moments/capture", token=USER4_TOKEN, method="POST", body=body_bypass)
        self.assertEqual(status, 403)
        self.assertEqual(res.get("code"), "COMMUNITY_RESTRICTED")

    def test_30_feed_isolation_private_community_moments_not_in_feed_for_anyone(self):
        # Strict isolation: Private community moments stay inside community and do NOT appear in Feed for non-members
        status_non, res_non = self._request("/api/feed", token=USER4_TOKEN, method="GET")
        self.assertEqual(status_non, 200)
        feed_ids_non = [p["id"] for p in res_non.get("feed", [])]
        self.assertNotIn("post_priv_event_1", feed_ids_non)

        # Strict isolation: Even members do NOT see private community moments in global /api/feed
        status_mem, res_mem = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_mem, 200)
        feed_ids_mem = [p["id"] for p in res_mem.get("feed", [])]
        self.assertNotIn("post_priv_event_1", feed_ids_mem)

        # But member (User 2) DOES see it inside the Community detail endpoint
        status_comm, res_comm = self._request(f"/api/community/detail?id={self.priv_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_comm, 200)
        comm_ids = [p["id"] for p in res_comm.get("moments", [])]
        self.assertIn("post_priv_event_1", comm_ids)

    def test_31_public_clusters_does_not_leak_private_community_clusters(self):
        # Public clusters endpoint does NOT leak private community clusters
        status, res = self._request("/api/clusters/public", token=USER4_TOKEN, method="GET")
        self.assertEqual(status, 200)
        for c in res.get("clusters", []):
            self.assertNotEqual(c.get("community_id"), self.priv_comm_id)
            self.assertNotEqual(c.get("visibility"), "private")

    def test_32_feed_to_community_reverse_isolation(self):
        # Symmetrical isolation: Normal Feed/Open Journal post must NOT bleed into community detail
        body_feed_only = {
            "caption": "Pure Open Journal Moment",
            "community": "Open Journal"
        }
        status_oj, res_oj = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body_feed_only)
        self.assertEqual(status_oj, 201)
        oj_post_id = res_oj["post"]["id"]

        # Appears in global feed
        status_feed, res_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed, 200)
        feed_ids = [m["id"] for m in res_feed.get("feed", [])]
        self.assertIn(oj_post_id, feed_ids)

        # Does NOT appear in public community detail
        status_pub, res_pub = self._request(f"/api/community/detail?id={self.comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_pub, 200)
        pub_ids = [m["id"] for m in res_pub.get("moments", [])]
        self.assertNotIn(oj_post_id, pub_ids)

        # Does NOT appear in private community detail
        status_priv, res_priv = self._request(f"/api/community/detail?id={self.priv_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_priv, 200)
        priv_ids = [m["id"] for m in res_priv.get("moments", [])]
        self.assertNotIn(oj_post_id, priv_ids)

    def test_33_live_pulse_zero_eligible_activity_honest_empty_state(self):
        # A. Live Pulse with zero eligible activity -> honest 0/empty state (NOT clamped to 4)
        conn = server.get_db()
        cursor = conn.cursor()
        empty_comm_id = f"comm_pulse_empty_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Empty Pulse Space', 'Campus', 'Patna', 'Fresh empty test space', 'public', 1)
        """, (empty_comm_id,))
        conn.commit()
        conn.close()

        status, res = self._request(f"/api/community/pulse?id={empty_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        # Must be EXACT 0, not fake 4
        self.assertEqual(res.get("community", {}).get("active_count"), 0)
        self.assertEqual(res.get("pulse_state"), "QUIET RIGHT NOW")
        self.assertEqual(res.get("moments"), [])

    def test_34_live_pulse_exact_count_one_and_multiple(self):
        # B & C. Live Pulse with 1 and multiple eligible activities -> exact real count
        conn = server.get_db()
        cursor = conn.cursor()
        test_comm_id = f"comm_pulse_test_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Active Pulse Space', 'Campus', 'Patna', 'Active test space', 'public', 2)
        """, (test_comm_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (test_comm_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att3', 'member', 'active')", (test_comm_id,))
        conn.commit()
        conn.close()

        # Capture 1st moment
        body1 = {
            "caption": "Live Pulse Moment 1",
            "community_id": test_comm_id
        }
        s1, r1 = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body1)
        self.assertEqual(s1, 201)

        # Pulse count must be EXACT 1
        status_p1, res_p1 = self._request(f"/api/community/pulse?id={test_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_p1, 200)
        self.assertEqual(res_p1.get("community", {}).get("active_count"), 1)
        self.assertEqual(res_p1.get("pulse_state"), "LIVE NOW")
        self.assertEqual(len(res_p1.get("moments", [])), 1)

        # Capture 2nd moment
        body2 = {
            "caption": "Live Pulse Moment 2",
            "community_id": test_comm_id
        }
        s2, r2 = self._request("/api/moments/capture", token=USER3_TOKEN, method="POST", body=body2)
        self.assertEqual(s2, 201)

        # Pulse count must be EXACT 2
        status_p2, res_p2 = self._request(f"/api/community/pulse?id={test_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_p2, 200)
        self.assertEqual(res_p2.get("community", {}).get("active_count"), 2)
        self.assertEqual(res_p2.get("pulse_state"), "LIVE NOW")
        self.assertEqual(len(res_p2.get("moments", [])), 2)

    def test_35_live_pulse_stale_activity_not_counted_as_now(self):
        # D. Stale/old activity -> not counted as NOW
        conn = server.get_db()
        cursor = conn.cursor()
        stale_comm_id = f"comm_pulse_stale_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Stale Pulse Space', 'Campus', 'Patna', 'Stale test space', 'public', 1)
        """, (stale_comm_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (stale_comm_id,))
        conn.commit()
        conn.close()

        # Capture moment
        body = {
            "caption": "Stale Moment",
            "community_id": stale_comm_id
        }
        s, r = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(s, 201)
        stale_post_id = r["post"]["id"]

        # Artificially age the moment to 3 days ago in DB
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET created_at = ? WHERE id = ?", (three_days_ago, stale_post_id))
        conn.commit()
        conn.close()

        # Stale moment MUST NOT be counted as NOW
        status, res = self._request(f"/api/community/pulse?id={stale_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("community", {}).get("active_count"), 0)
        self.assertEqual(res.get("pulse_state"), "QUIET RIGHT NOW")
        self.assertEqual(res.get("moments"), [])

    def test_36_live_pulse_community_isolation(self):
        # E. Community isolation -> Community A activity does not affect Community B
        conn = server.get_db()
        cursor = conn.cursor()
        comm_a_id = f"comm_iso_a_{uuid.uuid4().hex[:6]}"
        comm_b_id = f"comm_iso_b_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Community Alpha', 'Campus', 'Patna', 'Space A', 'public', 1),
                   (? , 'Community Beta', 'Campus', 'Patna', 'Space B', 'public', 1)
        """, (comm_a_id, comm_b_id))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (comm_a_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (comm_b_id,))
        conn.commit()
        conn.close()

        # Add 1 moment to Community A only
        body = {
            "caption": "Alpha Only Moment",
            "community_id": comm_a_id
        }
        s, r = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body)
        self.assertEqual(s, 201)

        # Community A has 1 active moment
        status_a, res_a = self._request(f"/api/community/pulse?id={comm_a_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_a, 200)
        self.assertEqual(res_a.get("community", {}).get("active_count"), 1)

        # Community B has 0 active moments (zero leakage)
        status_b, res_b = self._request(f"/api/community/pulse?id={comm_b_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_b, 200)
        self.assertEqual(res_b.get("community", {}).get("active_count"), 0)
        self.assertEqual(res_b.get("pulse_state"), "QUIET RIGHT NOW")

    def test_37_live_pulse_feed_and_open_journal_isolation(self):
        # F. Normal Feed/Open Journal activity does not inflate Community Pulse
        conn = server.get_db()
        cursor = conn.cursor()
        comm_clean_id = f"comm_clean_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count)
            VALUES (?, 'Clean Pulse Space', 'Campus', 'Patna', 'Clean space', 'public', 1)
        """, (comm_clean_id,))
        conn.commit()
        conn.close()

        # Capture Open Journal post
        body_oj = {
            "caption": "Open Journal Feed Only Moment",
            "community": "Open Journal"
        }
        s_oj, r_oj = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body_oj)
        self.assertEqual(s_oj, 201)

        # Pulse of community remains strictly 0
        status, res = self._request(f"/api/community/pulse?id={comm_clean_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(res.get("community", {}).get("active_count"), 0)
        self.assertEqual(res.get("pulse_state"), "QUIET RIGHT NOW")

    def test_38_live_pulse_private_community_authorization(self):
        # G. Private Community authorization: non-member cannot retrieve private Pulse, member can
        # 1. Unauthenticated -> 401
        status_unauth, res_unauth = self._request(f"/api/community/pulse?id={self.priv_comm_id}", method="GET")
        self.assertEqual(status_unauth, 401)
        self.assertEqual(res_unauth.get("code"), "UNAUTHORIZED")

        # 2. Non-member (USER4) -> 403
        status_non, res_non = self._request(f"/api/community/pulse?id={self.priv_comm_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(status_non, 403)
        self.assertEqual(res_non.get("code"), "COMMUNITY_RESTRICTED")

        # 3. Active member (USER2) -> 200
        status_mem, res_mem = self._request(f"/api/community/pulse?id={self.priv_comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_mem, 200)
        self.assertTrue(res_mem.get("success"))
        self.assertEqual(res_mem.get("community", {}).get("id"), self.priv_comm_id)

    def test_39_live_pulse_deterministic_refresh(self):
        # H. Refresh/repeated API request -> same underlying data produces same count (no random/demo fluctuation)
        status1, res1 = self._request(f"/api/community/pulse?id={self.comm_id}", token=USER2_TOKEN, method="GET")
        status2, res2 = self._request(f"/api/community/pulse?id={self.comm_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(status1, 200)
        self.assertEqual(status2, 200)
        self.assertEqual(res1.get("community", {}).get("active_count"), res2.get("community", {}).get("active_count"))
        self.assertEqual(res1.get("pulse_state"), res2.get("pulse_state"))

    def test_40_step1_isolation_comprehensive_matrix(self):
        """
        Phase 1 / Step 1: Strict Community -> FOR YOU Feed Isolation Matrix
        Verifies:
        A. Normal personal Feed post appears in /api/feed
        B. Normal personal Feed post remains associated with personal Open Journal
        C. Public Community post absent from /api/feed
        D. Private Community post absent from /api/feed for:
           - unrelated user (USER4)
           - private Community member (USER2)
           - Community admin (USER1)
        E. Community moment absent from /api/feed
        F. Community Perspective absent from /api/feed
        G. Community cluster post absent from /api/feed
        H. Cross-community: Community A post absent from Community B
        I. Reverse isolation: normal personal Feed/Open Journal post absent from Community detail
        J. Direct API: GET /api/feed?circle=all strictly enforces the same isolation
        """
        conn = server.get_db()
        cursor = conn.cursor()

        # Set up two distinct test communities: Pub_A and Priv_B
        comm_a_id = f"comm_iso_pub_{uuid.uuid4().hex[:6]}"
        comm_b_id = f"comm_iso_priv_{uuid.uuid4().hex[:6]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count, creator_id)
            VALUES (?, 'Public Matrix Alpha', 'Campus', 'Metro', 'Public test space', 'public', 2, 'u_att1'),
                   (?, 'Private Matrix Beta', 'Campus', 'Metro', 'Private test space', 'private', 2, 'u_att1')
        """, (comm_a_id, comm_b_id))
        # User 1 is creator/admin for both
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att1', 'creator', 'active')", (comm_a_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att1', 'creator', 'active')", (comm_b_id,))
        # User 2 is active member of both
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (comm_a_id,))
        cursor.execute("INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, 'u_att2', 'member', 'active')", (comm_b_id,))
        # User 4 has NO relationship to comm_b_id (unrelated user)
        conn.commit()
        conn.close()

        # Step A & B: Capture normal personal Feed post
        p_body = {
            "caption": "Matrix Personal Feed Post by User 2",
            "community": "Personal (Feed)",
            "circle": "all"
        }
        s_p, r_p = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=p_body)
        self.assertEqual(s_p, 201)
        personal_id = r_p["post"]["id"]

        # Verification A: Normal personal Feed post appears in /api/feed
        s_f, r_f = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_f, 200)
        feed_ids = [m["id"] for m in r_f.get("feed", [])]
        self.assertIn(personal_id, feed_ids)

        # Verification B: Normal personal Feed post remains associated with personal Open Journal in DB
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, primary_community_id, context_community_id, is_private FROM posts WHERE id = ?", (personal_id,))
        p_row = cursor.fetchone()
        self.assertIsNotNone(p_row)
        self.assertEqual(p_row[0], "u_att2")  # owned by User 2
        self.assertEqual(p_row[1] or "", "")   # no primary community
        self.assertEqual(p_row[2] or "", "")   # no context community
        conn.close()

        # Step C: Capture public Community post
        c_body = {
            "caption": "Public Community Matrix Post",
            "community_id": comm_a_id,
            "circle": "all"
        }
        s_c, r_c = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=c_body)
        self.assertEqual(s_c, 201)
        pub_comm_id = r_c["post"]["id"]

        # Verification C: Public Community post absent from /api/feed
        s_f_pub, r_f_pub = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_f_pub, 200)
        feed_pub_ids = [m["id"] for m in r_f_pub.get("feed", [])]
        self.assertNotIn(pub_comm_id, feed_pub_ids)

        # Step D: Capture private Community post
        priv_body = {
            "caption": "Private Community Matrix Post",
            "community_id": comm_b_id,
            "circle": "all"
        }
        s_priv, r_priv = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=priv_body)
        self.assertEqual(s_priv, 201)
        priv_post_id = r_priv["post"]["id"]

        # Verification D: Private Community post absent from /api/feed for:
        # 1. Unrelated user (USER4)
        s_u4, r_u4 = self._request("/api/feed", token=USER4_TOKEN, method="GET")
        self.assertEqual(s_u4, 200)
        self.assertNotIn(priv_post_id, [m["id"] for m in r_u4.get("feed", [])])

        # 2. Private Community member (USER2)
        s_u2, r_u2 = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_u2, 200)
        self.assertNotIn(priv_post_id, [m["id"] for m in r_u2.get("feed", [])])

        # 3. Community admin/creator (USER1)
        s_u1, r_u1 = self._request("/api/feed", token=USER1_TOKEN, method="GET")
        self.assertEqual(s_u1, 200)
        self.assertNotIn(priv_post_id, [m["id"] for m in r_u1.get("feed", [])])

        # Step E: Community moment absent from /api/feed
        self.assertNotIn(pub_comm_id, [m["id"] for m in r_u1.get("feed", [])])
        self.assertNotIn(priv_post_id, [m["id"] for m in r_u1.get("feed", [])])

        # Step F & G: Community cluster post and Perspective
        # Create cluster on public community post
        s_iwt, r_iwt = self._request(f"/api/moment/{pub_comm_id}/i-was-there", token=USER1_TOKEN, method="POST", body={"moment_id": pub_comm_id})
        self.assertEqual(s_iwt, 200)
        cluster_id = r_iwt.get("cluster_id")
        self.assertTrue(cluster_id)

        # Capture perspective inside the community cluster
        persp_body = {
            "caption": "Perspective on Community Cluster",
            "cluster_id": cluster_id,
            "community_id": comm_a_id
        }
        s_persp, r_persp = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=persp_body)
        self.assertEqual(s_persp, 201)
        persp_post_id = r_persp["post"]["id"]

        # Verification F: Community Perspective absent from /api/feed
        s_f_persp, r_f_persp = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_f_persp, 200)
        self.assertNotIn(persp_post_id, [m["id"] for m in r_f_persp.get("feed", [])])

        # Verification G: Community cluster post absent from /api/feed
        self.assertNotIn(pub_comm_id, [m["id"] for m in r_f_persp.get("feed", [])])

        # Step H: Cross-community isolation: Community A post absent from Community B's feed/detail
        s_det_b, r_det_b = self._request(f"/api/community/detail?id={comm_b_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_det_b, 200)
        det_b_ids = [m["id"] for m in r_det_b.get("moments", [])]
        self.assertNotIn(pub_comm_id, det_b_ids)
        self.assertNotIn(persp_post_id, det_b_ids)
        self.assertIn(priv_post_id, det_b_ids)

        # Step E: Capture personal post with campus-name coincidence matching Community A
        e_body = {
            "caption": "Campus String Coincidence Post by User 3",
            "community": "Personal (Feed)",
            "campus": "Public Matrix Alpha",
            "circle": "all"
        }
        s_e, r_e = self._request("/api/moments/capture", token=USER3_TOKEN, method="POST", body=e_body)
        self.assertEqual(s_e, 201)
        coincidence_post_id = r_e["post"]["id"]

        # Step H: Cross-community isolation: Community A post absent from Community B's feed/detail
        s_det_b, r_det_b = self._request(f"/api/community/detail?id={comm_b_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_det_b, 200)
        det_b_ids = [m["id"] for m in r_det_b.get("moments", [])]
        self.assertNotIn(pub_comm_id, det_b_ids)
        self.assertNotIn(persp_post_id, det_b_ids)
        self.assertIn(priv_post_id, det_b_ids)

        # Step I: Reverse isolation: normal personal Feed posts absent from Community detail/context
        s_det_a, r_det_a = self._request(f"/api/community/detail?id={comm_a_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_det_a, 200)
        det_a_ids = [m["id"] for m in r_det_a.get("moments", [])]
        self.assertNotIn(personal_id, det_a_ids)
        self.assertNotIn(coincidence_post_id, det_a_ids)
        self.assertIn(pub_comm_id, det_a_ids)

        # Campus parameter lookup also excludes personal coincidence post
        s_det_by_campus, r_det_by_campus = self._request(f"/api/community/detail?campus=Public%20Matrix%20Alpha", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_det_by_campus, 200)
        det_by_campus_ids = [m["id"] for m in r_det_by_campus.get("moments", [])]
        self.assertNotIn(coincidence_post_id, det_by_campus_ids)
        self.assertNotIn(personal_id, det_by_campus_ids)

        # Step J: Direct API: GET /api/feed?circle=all caller matrix
        # 1. Unauthenticated caller
        s_unauth, r_unauth = self._request("/api/feed?circle=all", method="GET")
        self.assertEqual(s_unauth, 200)
        unauth_feed_ids = [m["id"] for m in r_unauth.get("feed", [])]
        self.assertIn(personal_id, unauth_feed_ids)          # A visible
        self.assertIn(coincidence_post_id, unauth_feed_ids)  # E visible
        self.assertNotIn(pub_comm_id, unauth_feed_ids)       # B hidden
        self.assertNotIn(priv_post_id, unauth_feed_ids)      # C hidden
        self.assertNotIn(persp_post_id, unauth_feed_ids)     # D hidden

        # 2-6. Authenticated callers (Normal user, Member, Unrelated user, Admin)
        for tok in (USER4_TOKEN, USER2_TOKEN, USER1_TOKEN):
            s_all, r_all = self._request("/api/feed?circle=all", token=tok, method="GET")
            self.assertEqual(s_all, 200)
            all_feed_ids = [m["id"] for m in r_all.get("feed", [])]
            self.assertIn(personal_id, all_feed_ids)          # A visible
            self.assertIn(coincidence_post_id, all_feed_ids)  # E visible
            self.assertNotIn(pub_comm_id, all_feed_ids)       # B hidden
            self.assertNotIn(priv_post_id, all_feed_ids)      # C hidden
            self.assertNotIn(persp_post_id, all_feed_ids)     # D hidden

        # Private Community Authorization Matrix on /api/community/detail:
        # Unauthenticated -> 401
        s_unauth_priv, r_unauth_priv = self._request(f"/api/community/detail?id={comm_b_id}", method="GET")
        self.assertEqual(s_unauth_priv, 401)
        self.assertEqual(r_unauth_priv.get("code"), "UNAUTHORIZED")

        # Authenticated non-member (USER4) -> 403
        s_non_priv, r_non_priv = self._request(f"/api/community/detail?id={comm_b_id}", token=USER4_TOKEN, method="GET")
        self.assertEqual(s_non_priv, 403)
        self.assertEqual(r_non_priv.get("code"), "COMMUNITY_RESTRICTED")

        # Approved member (USER2) -> 200, sees legitimate content
        s_mem_priv, r_mem_priv = self._request(f"/api/community/detail?id={comm_b_id}", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_mem_priv, 200)
        self.assertIn(priv_post_id, [m["id"] for m in r_mem_priv.get("moments", [])])

        # Owner/admin (USER1) -> 200, sees legitimate content
        s_admin_priv, r_admin_priv = self._request(f"/api/community/detail?id={comm_b_id}", token=USER1_TOKEN, method="GET")
        self.assertEqual(s_admin_priv, 200)
        self.assertIn(priv_post_id, [m["id"] for m in r_admin_priv.get("moments", [])])

    def test_41_community_areas_strict_isolation_and_empty_state(self):
        """
        Phase 1 / Step 2 Remediation:
        - Community A has an area post (Engineering Block).
        - Community B has zero area posts.
        - Community A's areas must NOT appear in Community B.
        - Community B returns areas = [] and active_areas_count = 0 (never 1).
        - Personal post with campus = Community B name and location_city = Campus Quad
          must NOT appear as an Area in Community B.
        - Personal post remains normal Feed/Open Journal post.
        """
        conn = server.get_db()
        cursor = conn.cursor()
        comm_a_id = f"comm_area_a_{uuid.uuid4().hex[:6]}"
        comm_b_id = f"comm_area_b_{uuid.uuid4().hex[:6]}"
        comm_b_name = f"Area Test Community Beta {uuid.uuid4().hex[:4]}"
        cursor.execute("""
            INSERT INTO communities (id, name, type, city, description, visibility, members_count, creator_id)
            VALUES (?, 'Area Test Community Alpha', 'Campus', 'Metro', 'Alpha space', 'public', 1, 'u_att1'),
                   (?, ?, 'Campus', 'Metro', 'Beta space', 'public', 1, 'u_att1')
        """, (comm_a_id, comm_b_id, comm_b_name))
        conn.commit()
        conn.close()

        # 1. Capture Area post in Community A
        body_a = {
            "caption": "Engineering Lab Session in Comm A",
            "community_id": comm_a_id,
            "location_city": "Engineering Block",
            "circle": "all"
        }
        s_a, r_a = self._request("/api/moments/capture", token=USER1_TOKEN, method="POST", body=body_a)
        self.assertEqual(s_a, 201)

        # 2. Inspect Community B detail (should have 0 areas, active_areas_count = 0)
        s_b, r_b = self._request(f"/api/community/detail?id={comm_b_id}", token=USER1_TOKEN, method="GET")
        self.assertEqual(s_b, 200)
        self.assertEqual(r_b.get("areas"), [])
        self.assertEqual(r_b.get("pulse", {}).get("active_areas_count"), 0)
        self.assertEqual(r_b.get("timeline", {}).get("present", {}).get("active_areas_count"), 0)

        # 3. Inspect Community A detail (should have 1 area: Engineering Block, active_areas_count = 1)
        s_det_a, r_det_a = self._request(f"/api/community/detail?id={comm_a_id}", token=USER1_TOKEN, method="GET")
        self.assertEqual(s_det_a, 200)
        areas_a = r_det_a.get("areas", [])
        self.assertEqual(len(areas_a), 1)
        self.assertEqual(areas_a[0]["name"], "Engineering Block")
        self.assertEqual(areas_a[0]["momentsCount"], 1)
        self.assertEqual(r_det_a.get("pulse", {}).get("active_areas_count"), 1)

        # 4. Create personal collision post matching Community B name with location_city
        body_collision = {
            "caption": "Personal post with campus collision",
            "community": "Personal (Feed)",
            "campus": comm_b_name,
            "location_city": "Campus Quad",
            "circle": "all"
        }
        s_col, r_col = self._request("/api/moments/capture", token=USER2_TOKEN, method="POST", body=body_collision)
        self.assertEqual(s_col, 201)
        col_post_id = r_col["post"]["id"]

        # 5. Confirm collision post does NOT appear in Community B's Areas or moments
        s_b2, r_b2 = self._request(f"/api/community/detail?id={comm_b_id}", token=USER1_TOKEN, method="GET")
        self.assertEqual(s_b2, 200)
        self.assertEqual(r_b2.get("areas"), [])
        self.assertEqual(r_b2.get("pulse", {}).get("active_areas_count"), 0)
        b2_moment_ids = [m["id"] for m in r_b2.get("moments", [])]
        self.assertNotIn(col_post_id, b2_moment_ids)

        # 6. Confirm personal post remains in normal Feed
        s_feed, r_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(s_feed, 200)
        feed_ids = [m["id"] for m in r_feed.get("feed", [])]
        self.assertIn(col_post_id, feed_ids)

if __name__ == "__main__":
    unittest.main()



