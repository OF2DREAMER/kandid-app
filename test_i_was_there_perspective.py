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
from datetime import datetime, timedelta

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

        # Create private community (u_att4 is NOT a member)
        cls.priv_comm_id = "comm_priv_1"
        cursor.execute(
            "INSERT INTO communities (id, name, type, visibility, members_count, creator_id) VALUES (?, ?, ?, ?, ?, ?)",
            (cls.priv_comm_id, "Secret Society", "Campus", "private", 1, "u_att1")
        )
        cursor.execute(
            "INSERT INTO community_members (community_id, user_id, role, status) VALUES (?, ?, 'member', 'active')",
            (cls.priv_comm_id, "u_att1")
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
        # 1. Verify Feed contains primary moment
        status_feed, res_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed, 200)
        feed_moment_ids = [m["id"] for m in res_feed.get("feed", [])]
        self.assertIn(self.moment_id, feed_moment_ids)

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

        # 3. Verify Feed does NOT contain the perspective post
        status_feed2, res_feed2 = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed2, 200)
        feed_moment_ids2 = [m["id"] for m in res_feed2.get("feed", [])]
        self.assertNotIn(persp_post_id, feed_moment_ids2)
        self.assertIn(self.moment_id, feed_moment_ids2)

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

    def test_13_ordinary_community_and_personal_posts_remain_in_feed(self):
        # 1. Create ordinary personal post (no cluster)
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

        # 3. Verify both appear in Feed
        status_feed, res_feed = self._request("/api/feed", token=USER2_TOKEN, method="GET")
        self.assertEqual(status_feed, 200)
        feed_ids = [m["id"] for m in res_feed.get("feed", [])]
        self.assertIn(personal_id, feed_ids)
        self.assertIn(comm_post_id, feed_ids)

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

if __name__ == "__main__":
    unittest.main()



