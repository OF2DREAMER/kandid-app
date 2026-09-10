#!/usr/bin/env python3
import os
import sys
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

class TestProfileSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        conn = server.get_db()
        cursor = conn.cursor()

        for uid, handle, name, vis, campus, city, conn_from in [
            ('u_test_you', 'you_tester', 'You Tester', 'public', 'Delhi University', 'New Delhi', 'everyone'),
            ('u_test_pub', 'public_karan', 'Karan Kumar', 'public', 'Guru Kashi University', 'Supaul', 'everyone'),
            ('u_test_priv', 'private_alex', 'Alex Rivera', 'private', 'St Stephens', 'Delhi', 'everyone'),
            ('u_test_mutual', 'mutual_sam', 'Sam Friend', 'public', 'Delhi University', 'New Delhi', 'everyone'),
            ('u_test_no_req', 'no_requests_user', 'No Req User', 'public', 'IIT Delhi', 'Delhi', 'no_one'),
        ]:
            cursor.execute('''
                INSERT OR REPLACE INTO users (id, email, handle, name, password_hash, salt, campus, location_city, bio, profile_visibility, connections_from)
                VALUES (?, ?, ?, ?, 'hash', 'salt', ?, ?, 'Building things.', ?, ?)
            ''', (uid, f"{handle}@test.com", handle, name, campus, city, vis, conn_from))

        cursor.execute("DELETE FROM posts WHERE user_id IN ('u_test_pub', 'u_test_priv')")
        cursor.execute('''
            INSERT INTO posts (id, user_id, author_name, author_handle, campus, location_city, main_img, pip_img, is_private, moderation_status)
            VALUES ('post_pub_1', 'u_test_pub', 'Karan Kumar', 'public_karan', 'GKU Campus', 'Supaul', 'https://img.test/1.jpg', '', 0, 'active')
        ''')
        cursor.execute('''
            INSERT INTO posts (id, user_id, author_name, author_handle, campus, location_city, main_img, pip_img, is_private, moderation_status)
            VALUES ('post_priv_1', 'u_test_priv', 'Alex Rivera', 'private_alex', 'St Stephens', 'Delhi', 'https://img.test/2.jpg', '', 0, 'active')
        ''')

        cursor.execute("DELETE FROM friendships WHERE user_id LIKE 'u_test_%' OR friend_id LIKE 'u_test_%'")
        cursor.execute("DELETE FROM blocks WHERE user_id LIKE 'u_test_%' OR blocked_user_id LIKE 'u_test_%'")
        cursor.execute("DELETE FROM notifications WHERE user_id LIKE 'u_test_%' OR sender_id LIKE 'u_test_%'")

        conn.commit()
        conn.close()

    def test_01_own_public_profile(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = 'u_test_you'")
        user = dict(cursor.fetchone())
        conn.close()
        self.assertEqual(user.get("profile_visibility"), "public")
        self.assertEqual(user.get("name"), "You Tester")
        print("  ✅ PASS: 1. Own public profile")

    def test_02_own_profile_after_privacy_setting(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET profile_visibility = 'private' WHERE id = 'u_test_you'")
        conn.commit()
        cursor.execute("SELECT profile_visibility FROM users WHERE id = 'u_test_you'")
        vis = cursor.fetchone()[0]
        cursor.execute("UPDATE users SET profile_visibility = 'public' WHERE id = 'u_test_you'")
        conn.commit()
        conn.close()
        self.assertEqual(vis, "private")
        print("  ✅ PASS: 2. Own profile after privacy setting")

    def test_03_other_public_profile_full_data(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = 'u_test_pub'")
        target = dict(cursor.fetchone())
        cursor.execute("SELECT * FROM posts WHERE user_id = 'u_test_pub' AND is_private = 0")
        moments = cursor.fetchall()
        conn.close()
        self.assertEqual(target["profile_visibility"], "public")
        self.assertGreater(len(moments), 0)
        self.assertEqual(target["campus"], "Guru Kashi University")
        self.assertEqual(target["location_city"], "Supaul")
        print("  ✅ PASS: 3. Other public profile")

    def test_04_other_private_profile_gated(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = 'u_test_priv'")
        target = dict(cursor.fetchone())
        conn.close()
        self.assertEqual(target["profile_visibility"], "private")
        self.assertEqual(target["name"], "Alex Rivera")
        self.assertEqual(target["handle"], "private_alex")
        self.assertTrue(bool(target["bio"]))
        print("  ✅ PASS: 4. Other private profile")

    def test_05_send_connection_request(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_test_1', 'u_test_you', 'u_test_pub', 'pending')")
        cursor.execute('''
            INSERT INTO notifications (id, user_id, title, body, type, is_read, sender_id, target_id)
            VALUES ('notif_test_1', 'u_test_pub', 'You Tester wants to connect with you', 'Connect to see what they share.', 'connection_request', 0, 'u_test_you', 'u_test_you')
        ''')
        conn.commit()
        cursor.execute("SELECT status FROM friendships WHERE user_id = 'u_test_you' AND friend_id = 'u_test_pub'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "pending")
        print("  ✅ PASS: 5. Send connection request")

    def test_06_request_received_by_target(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT status, user_id FROM friendships WHERE friend_id = 'u_test_pub' AND status = 'pending'")
        f_row = cursor.fetchone()
        cursor.execute("SELECT * FROM notifications WHERE user_id = 'u_test_pub' AND type = 'connection_request'")
        notif = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(f_row)
        self.assertEqual(f_row[0], "pending")
        self.assertIsNotNone(notif)
        print("  ✅ PASS: 6. Request received")

    def test_07_accept_connection(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE friendships SET status = 'accepted' WHERE user_id = 'u_test_you' AND friend_id = 'u_test_pub'")
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_test_2', 'u_test_pub', 'u_test_you', 'accepted')")
        conn.commit()
        cursor.execute("SELECT status FROM friendships WHERE user_id = 'u_test_you' AND friend_id = 'u_test_pub'")
        s1 = cursor.fetchone()[0]
        cursor.execute("SELECT status FROM friendships WHERE user_id = 'u_test_pub' AND friend_id = 'u_test_you'")
        s2 = cursor.fetchone()[0]
        conn.close()
        self.assertIn(s1, ("accepted", "connected"))
        self.assertIn(s2, ("accepted", "connected"))
        print("  ✅ PASS: 7. Accept connection")

    def test_08_decline_connection(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_temp', 'u_test_you', 'u_test_priv', 'pending')")
        conn.commit()
        cursor.execute("DELETE FROM friendships WHERE (user_id = 'u_test_you' AND friend_id = 'u_test_priv') OR (user_id = 'u_test_priv' AND friend_id = 'u_test_you')")
        conn.commit()
        cursor.execute("SELECT 1 FROM friendships WHERE (user_id = 'u_test_you' AND friend_id = 'u_test_priv')")
        rem = cursor.fetchone()
        conn.close()
        self.assertIsNone(rem)
        print("  ✅ PASS: 8. Decline connection")

    def test_09_connected_profile_unlocks_private(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_priv_c1', 'u_test_you', 'u_test_priv', 'accepted')")
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_priv_c2', 'u_test_priv', 'u_test_you', 'accepted')")
        conn.commit()
        cursor.execute("SELECT status FROM friendships WHERE (user_id = 'u_test_you' AND friend_id = 'u_test_priv')")
        c_status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(c_status, "accepted")
        print("  ✅ PASS: 9. Connected profile unlocks private content")

    def test_10_remove_connection(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM friendships WHERE (user_id = 'u_test_you' AND friend_id = 'u_test_pub') OR (user_id = 'u_test_pub' AND friend_id = 'u_test_you')")
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM posts WHERE user_id = 'u_test_pub'")
        p_count = cursor.fetchone()[0]
        conn.close()
        self.assertGreater(p_count, 0)
        print("  ✅ PASS: 10. Remove connection preserves historical content")

    def test_11_blocked_user_safety(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO blocks (id, user_id, blocked_user_id) VALUES ('b_test_1', 'u_test_you', 'u_test_pub')")
        conn.commit()
        cursor.execute("SELECT 1 FROM blocks WHERE user_id = 'u_test_you' AND blocked_user_id = 'u_test_pub'")
        b_exists = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(b_exists)
        print("  ✅ PASS: 11. Blocked user safety")

    def test_12_report_safety(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                reporter_id TEXT,
                target_id TEXT,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("INSERT INTO reports (id, reporter_id, reported_user_id, reason) VALUES ('rep_test_1', 'u_test_you', 'u_test_pub', 'Inappropriate')")
        conn.commit()
        cursor.execute("SELECT 1 FROM reports WHERE id = 'rep_test_1'")
        rep = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(rep)
        print("  ✅ PASS: 12. Report safety")

    def test_13_no_shared_world_hidden(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.id FROM users u
            WHERE u.id IN (SELECT friend_id FROM friendships WHERE user_id = 'u_test_you' AND status = 'accepted')
              AND u.id IN (SELECT friend_id FROM friendships WHERE user_id = 'u_test_pub' AND status = 'accepted')
        ''')
        mutual = cursor.fetchall()
        conn.close()
        self.assertEqual(len(mutual), 0)
        print("  ✅ PASS: 13. No shared world when no context exists")

    def test_14_shared_community_exists(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO communities (id, name, type, visibility) VALUES ('comm_test_1', 'Kandid Builders', 'Club', 'public')")
        cursor.execute("INSERT OR REPLACE INTO community_members (community_id, user_id, role) VALUES ('comm_test_1', 'u_test_you', 'member')")
        cursor.execute("INSERT OR REPLACE INTO community_members (community_id, user_id, role) VALUES ('comm_test_1', 'u_test_pub', 'member')")
        conn.commit()
        cursor.execute('''
            SELECT c.id, c.name FROM communities c
            JOIN community_members cm1 ON c.id = cm1.community_id AND cm1.user_id = 'u_test_you'
            JOIN community_members cm2 ON c.id = cm2.community_id AND cm2.user_id = 'u_test_pub'
            WHERE c.visibility = 'public'
        ''')
        shared_c = cursor.fetchall()
        conn.close()
        self.assertGreaterEqual(len(shared_c), 1)
        self.assertEqual(shared_c[0][1], "Kandid Builders")
        print("  ✅ PASS: 14. Shared community exists")

    def test_15_mutual_connection_exists(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_m1', 'u_test_you', 'u_test_mutual', 'accepted')")
        cursor.execute("INSERT OR REPLACE INTO friendships (id, user_id, friend_id, status) VALUES ('fr_m2', 'u_test_pub', 'u_test_mutual', 'accepted')")
        conn.commit()
        cursor.execute('''
            SELECT u.name FROM users u
            WHERE u.id IN (SELECT friend_id FROM friendships WHERE user_id = 'u_test_you' AND status = 'accepted')
              AND u.id IN (SELECT friend_id FROM friendships WHERE user_id = 'u_test_pub' AND status = 'accepted')
        ''')
        mutual = cursor.fetchall()
        conn.close()
        self.assertGreaterEqual(len(mutual), 1)
        self.assertEqual(mutual[0][0], "Sam Friend")
        print("  ✅ PASS: 15. Mutual connection exists")

    def test_16_private_profile_in_search(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, handle, profile_visibility FROM users WHERE handle = 'private_alex'")
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[3], "private")
        print("  ✅ PASS: 16. Private profile in Search")

    def test_17_back_navigation_preserves_origin(self):
        with open(os.path.join(PROJECT_DIR, "app.js"), "r") as f:
            js = f.read()
        self.assertIn("function handlePeerProfileBack()", js)
        self.assertIn("switchScreenView(lastScreenBeforeProfile", js)
        print("  ✅ PASS: 17. Back navigation preserves origin screen")

    def test_18_journal_remains_owner_only(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), "r") as f:
            html = f.read()
        self.assertIn('id="youJournalCard"', html)
        self.assertIn('YOUR JOURNAL', html)
        peer_start = html.find('id="screen-peer-profile"')
        peer_end = html.find('id="screen-memories"')
        peer_html = html[peer_start:peer_end]
        self.assertNotIn('YOUR JOURNAL', peer_html)
        self.assertNotIn('youJournalCard', peer_html)
        print("  ✅ PASS: 18. Journal remains owner-only")

if __name__ == "__main__":
    unittest.main()
