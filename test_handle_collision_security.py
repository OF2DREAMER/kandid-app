import unittest
import os
import sys
import tempfile
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import server

class TestHandleCollisionSecurity(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        server.DB_FILE = self.db_path
        server.DATABASE_URL = ""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                handle TEXT,
                name TEXT,
                campus TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS communities (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                description TEXT,
                city TEXT,
                creator_id TEXT,
                creator_handle TEXT,
                icon TEXT,
                visibility TEXT,
                members_count INTEGER
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS community_members (
                id TEXT PRIMARY KEY,
                community_id TEXT,
                user_id TEXT,
                role TEXT,
                status TEXT,
                joined_at TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS community_drops (
                id TEXT PRIMARY KEY,
                community_id TEXT,
                creator_id TEXT,
                creator_handle TEXT,
                title TEXT,
                status TEXT
            );
        """)

        # User A: True Owner (handle: "ceo", user_id: "user_owner_real")
        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_owner_real', 'owner@kandid.app', 'ceo', 'Real CEO Owner')")

        # User B: Attacker with case-colliding handle ("CEO", user_id: "user_attacker_case_collide")
        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_attacker_case_collide', 'attacker@kandid.app', 'CEO', 'Attacker Case Collide')")

        # User C: Normal non-owner user (handle: "alice", user_id: "user_normal_alice")
        cursor.execute("INSERT INTO users (id, email, handle, name) VALUES ('user_normal_alice', 'alice@example.com', 'alice', 'Normal Alice')")

        # Community created by User A (creator_id: "user_owner_real", creator_handle: "ceo")
        cursor.execute("""
            INSERT INTO communities (id, name, type, creator_id, creator_handle)
            VALUES ('comm_test_1', 'Test Community', 'Place', 'user_owner_real', 'ceo')
        """)

        # Drop created by User A
        cursor.execute("""
            INSERT INTO community_drops (id, community_id, creator_id, creator_handle, title)
            VALUES ('drop_test_1', 'comm_test_1', 'user_owner_real', 'ceo', 'Test Drop')
        """)

        conn.commit()
        conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_01_real_owner_has_owner_role(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        role = server.get_user_community_role("comm_test_1", "user_owner_real", cursor)
        conn.close()
        self.assertEqual(role, "owner")

    def test_02_case_colliding_user_does_not_get_owner_role(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        role = server.get_user_community_role("comm_test_1", "user_attacker_case_collide", cursor)
        conn.close()
        self.assertNotEqual(role, "owner")

    def test_03_normal_user_does_not_get_owner_role(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        role = server.get_user_community_role("comm_test_1", "user_normal_alice", cursor)
        conn.close()
        self.assertNotEqual(role, "owner")

    def test_04_drop_ownership_validation_authoritative(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Real owner -> True
        cursor.execute("SELECT * FROM community_drops WHERE id = ?", ("drop_test_1",))
        valid_owner, msg, drop = server.validate_drop_ownership("drop_test_1", "user_owner_real", cursor)
        self.assertTrue(valid_owner)

        # Case-colliding attacker -> False
        cursor.execute("SELECT * FROM community_drops WHERE id = ?", ("drop_test_1",))
        valid_attacker, msg, drop = server.validate_drop_ownership("drop_test_1", "user_attacker_case_collide", cursor)
        self.assertFalse(valid_attacker)


        conn.close()

if __name__ == "__main__":
    unittest.main()
