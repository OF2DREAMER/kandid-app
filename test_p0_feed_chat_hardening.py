"""P0 hardening tests: public community feed query (P0-A) and chat expiration
worker (P0-B).

Runs on SQLite for speed. A companion module (test_p0_real_postgres.py)
exercises the same query and worker code paths against a real disposable
PostgreSQL instance, which is the only environment where the two original
defects actually reproduced.
"""

import json
import os
import shutil
import socket
import tempfile
import unittest
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta

import server
from server import KandidHandler

TOKEN_MAIN = "tok_p0_main"
TOKEN_OTHER = "tok_p0_other"


def _now_str(offset_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")


def _insert_post(cursor, pid, primary="", context="", is_private=0, created_at=None,
                 moderation="active", uid="u_p0_2", handle="user2", name="User Two"):
    if created_at is None:
        created_at = _now_str(-60)
    cursor.execute(
        """
        INSERT OR REPLACE INTO posts (
            id, user_id, author_handle, author_name, main_img, pip_img, caption,
            primary_community_id, context_community_id, circle, is_private,
            created_at, moderation_status
        ) VALUES (?, ?, ?, ?, 'https://example.com/m.jpg', 'https://example.com/p.jpg', 'cap',
                  ?, ?, 'campus', ?, ?, ?)
        """,
        (pid, uid, handle, name, primary, context, is_private, created_at, moderation),
    )


class P0FeedAndWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_p0_test_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_p0.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()

        for uid, email, handle, name in [
            ("u_p0_1", "p0_1@test.com", "p0one", "P0 One"),
            ("u_p0_2", "p0_2@test.com", "user2", "User Two"),
        ]:
            cursor.execute(
                "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, "
                "email_verified, is_onboarded, account_status) "
                "VALUES (?, ?, ?, ?, 'h', 's', 'North City University', 'student', 1, 1, 'active')",
                (uid, email, handle, name),
            )
        cursor.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) "
            "VALUES ('s_p0_1', 'u_p0_1', ?, '2099-01-01T00:00:00Z')",
            (TOKEN_MAIN,),
        )

        cls.pub_a = "p0_pub_a"
        cls.pub_b = "p0_pub_b"
        cls.pub_named = "p0_name_match"
        cls.priv = "p0_priv"
        cls.secret = "p0_secret"
        cls.removed = "p0_removed"
        cursor.execute(
            """
            INSERT INTO communities (id, name, type, city, description, visibility, members_count, moderation_status)
            VALUES (?, 'Public Arts Collective', 'Interest', 'Delhi', '', 'public', 10, 'active'),
                   (?, 'Public Tech Commons', 'Campus', 'Delhi', '', 'public', 15, 'active'),
                   (?, 'Name Matched Space', 'Interest', 'Delhi', '', 'public', 3, 'active'),
                   (?, 'Hidden Vault', 'Interest', 'Delhi', '', 'private', 5, 'active'),
                   (?, 'Secret Vault', 'Interest', 'Delhi', '', 'secret', 5, 'active'),
                   (?, 'Removed Space', 'Interest', 'Delhi', '', 'public', 5, 'removed')
            """,
            (cls.pub_a, cls.pub_b, cls.pub_named, cls.priv, cls.secret, cls.removed),
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        if os.path.exists(cls._tmpdir):
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------ utils
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
            req += f"Authorization: Bearer {token}\r\n"
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
        status = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 500
        data = {}
        if body_part:
            try:
                data = json.loads(body_part.decode("utf-8", errors="replace"))
            except Exception:
                data = {"raw": body_part.decode("utf-8", errors="replace")}
        return status, data

    def _feed(self, view="moments", token=TOKEN_MAIN, extra=""):
        return self._req(f"/api/community/public-feed?view={view}{extra}", token=token)

    def _cleanup_posts(self):
        conn = server.get_db()
        conn.execute("DELETE FROM posts")
        conn.commit()
        conn.close()

    # ------------------------------------------------------- P0-A: view shape
    def test_p0a_pulse_and_moments_both_return_200(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_shape_1", primary=self.pub_a, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        for view in ("pulse", "moments"):
            status, res = self._feed(view)
            self.assertEqual(status, 200, f"{view} must not error")
            self.assertTrue(res.get("success"))
            self.assertIn("moments", res)
            self.assertIn("pulse", res)

    def test_p0a_primary_only_attribution(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_primary_only", primary=self.pub_a, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        for view in ("pulse", "moments"):
            _, res = self._feed(view)
            rows = [m for m in res.get("moments", []) if m["id"] == "p0_primary_only"]
            self.assertEqual(len(rows), 1, f"{view}: exactly one row for primary-only post")
            self.assertEqual(rows[0]["community_id"], self.pub_a)
            self.assertEqual(rows[0]["community_name"], "Public Arts Collective")
            self.assertEqual(rows[0]["community_visibility"], "public")

    def test_p0a_context_only_attribution(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_context_only", primary="", context=self.pub_b, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        for view in ("pulse", "moments"):
            _, res = self._feed(view)
            rows = [m for m in res.get("moments", []) if m["id"] == "p0_context_only"]
            self.assertEqual(len(rows), 1, f"{view}: context-only post appears once")
            self.assertEqual(rows[0]["community_id"], self.pub_b)
            self.assertEqual(rows[0]["community_name"], "Public Tech Commons")

    def test_p0a_context_community_specified_by_name(self):
        """Community references may be a name (legacy rows) as well as an id."""
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_context_by_name", primary="", context="Name Matched Space", created_at=_now_str(-30))
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        rows = [m for m in res.get("moments", []) if m["id"] == "p0_context_by_name"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["community_id"], self.pub_named)

    def test_p0a_both_communities_no_duplicate_and_primary_preferred(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_both", primary=self.pub_a, context=self.pub_b, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        for view in ("pulse", "moments"):
            _, res = self._feed(view)
            rows = [m for m in res.get("moments", []) if m["id"] == "p0_both"]
            self.assertEqual(len(rows), 1, f"{view}: primary+context must not duplicate")
            self.assertEqual(rows[0]["community_id"], self.pub_a, f"{view}: primary community preferred")

    def test_p0a_author_and_community_metadata_integrity(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_meta", primary=self.pub_a, created_at=_now_str(-30),
                     uid="u_p0_2", handle="user2", name="User Two")
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        row = next(m for m in res["moments"] if m["id"] == "p0_meta")
        self.assertEqual(row["author_name"], "User Two")
        self.assertEqual(row["author_handle"], "user2")
        self.assertEqual(row["community_name"], "Public Arts Collective")
        self.assertEqual(row["community_icon"] is not None, True)
        self.assertEqual(row["community_city"], "Delhi")
        self.assertEqual(row["community_type"], "Interest")
        self.assertIn("realmojis", row)
        self.assertIn("timeAgo", row)
        self.assertIn("area_tag", row)
        # The frontend community override fields must still be present.
        self.assertEqual(row["primary_community_id"], self.pub_a)
        self.assertEqual(row["primary_community_name"], "Public Arts Collective")

    def test_p0a_private_and_secret_communities_excluded(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_priv_post", primary=self.priv, created_at=_now_str(-30))
        _insert_post(cursor, "p0_secret_post", primary=self.secret, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        for view in ("pulse", "moments"):
            _, res = self._feed(view)
            ids = [m["id"] for m in res.get("moments", [])]
            self.assertNotIn("p0_priv_post", ids)
            self.assertNotIn("p0_secret_post", ids)

    def test_p0a_private_context_excludes_post_even_with_public_primary(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_pub_priv_ctx", primary=self.pub_a, context=self.priv, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("p0_pub_priv_ctx", ids)

    def test_p0a_moderated_post_and_community_excluded(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_removed_post", primary=self.pub_a, created_at=_now_str(-30), moderation="removed")
        _insert_post(cursor, "p0_in_removed_comm", primary=self.removed, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("p0_removed_post", ids)
        self.assertNotIn("p0_in_removed_comm", ids)

    def test_p0a_is_private_moment_excluded(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_is_private", primary=self.pub_a, is_private=1, created_at=_now_str(-30))
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("p0_is_private", ids)

    def test_p0a_ordering_newest_first(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        _insert_post(cursor, "p0_order_old", primary=self.pub_a, created_at="2026-01-01 00:00:00")
        _insert_post(cursor, "p0_order_new", primary=self.pub_a, created_at="2026-01-02 00:00:00")
        conn.commit()
        conn.close()

        _, res = self._feed("moments")
        ids = [m["id"] for m in res["moments"]]
        self.assertLess(ids.index("p0_order_new"), ids.index("p0_order_old"))

    def test_p0a_pagination_cursor_has_no_duplicates(self):
        self._cleanup_posts()
        conn = server.get_db()
        cursor = conn.cursor()
        for i in range(4):
            _insert_post(cursor, f"p0_page_{i}", primary=self.pub_a,
                         created_at=f"2026-02-0{i + 1} 00:00:00")
        conn.commit()
        conn.close()

        seen = []
        cursor_val = ""
        for _ in range(5):
            extra = f"&limit=2&cursor={urllib.parse.quote(cursor_val)}" if cursor_val else "&limit=2"
            _, res = self._feed("moments", extra=extra)
            page = res.get("moments", [])
            seen.extend(m["id"] for m in page)
            if not res.get("has_more"):
                break
            cursor_val = res.get("next_cursor") or ""
            if not cursor_val:
                break

        paged = [i for i in seen if i.startswith("p0_page_")]
        self.assertEqual(len(paged), len(set(paged)), "pagination must not repeat rows")
        self.assertEqual(set(paged), {f"p0_page_{i}" for i in range(4)})

    # --------------------------------------------------- P0-B: worker behaviour
    def _msg(self, mid, sender_state="active", receiver_state="active",
             s_exp=None, r_exp=None, media=None, deleted_everyone=0):
        conn = server.get_db()
        conn.execute(
            "INSERT OR REPLACE INTO messages (id, sender_id, receiver_id, content, "
            "sender_state, receiver_state, trash_expires_at_sender, trash_expires_at_receiver, "
            "is_deleted_for_everyone, media_url) VALUES (?, 'u_p0_1', 'u_p0_2', 'hi', ?, ?, ?, ?, ?, ?)",
            (mid, sender_state, receiver_state, s_exp, r_exp, deleted_everyone, media),
        )
        conn.commit()
        conn.close()

    def _msg_state(self, mid):
        conn = server.get_db()
        row = conn.execute(
            "SELECT sender_state, receiver_state, trash_expires_at_sender, trash_expires_at_receiver "
            "FROM messages WHERE id = ?", (mid,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _run_cycle(self):
        conn = server.get_db()
        files = server._run_chat_expiration_cycle(conn)
        conn.commit()
        conn.close()
        return files

    def _clear_messages(self):
        conn = server.get_db()
        conn.execute("DELETE FROM messages")
        conn.commit()
        conn.close()

    def test_p0b_expired_sender_transitions_to_deleted(self):
        self._clear_messages()
        self._msg("m_exp_s", sender_state="in_trash", s_exp=_now_str(-60))
        self._run_cycle()
        st = self._msg_state("m_exp_s")
        self.assertEqual(st["sender_state"], "deleted")
        self.assertIsNone(st["trash_expires_at_sender"])

    def test_p0b_future_sender_left_in_trash(self):
        self._clear_messages()
        self._msg("m_fut_s", sender_state="in_trash", s_exp=_now_str(3600))
        self._run_cycle()
        st = self._msg_state("m_fut_s")
        self.assertEqual(st["sender_state"], "in_trash")
        self.assertIsNotNone(st["trash_expires_at_sender"])

    def test_p0b_expired_receiver_transitions_to_deleted(self):
        self._clear_messages()
        self._msg("m_exp_r", receiver_state="in_trash", r_exp=_now_str(-60))
        self._run_cycle()
        st = self._msg_state("m_exp_r")
        self.assertEqual(st["receiver_state"], "deleted")
        self.assertIsNone(st["trash_expires_at_receiver"])

    def test_p0b_future_receiver_left_in_trash(self):
        self._clear_messages()
        self._msg("m_fut_r", receiver_state="in_trash", r_exp=_now_str(3600))
        self._run_cycle()
        st = self._msg_state("m_fut_r")
        self.assertEqual(st["receiver_state"], "in_trash")
        self.assertIsNotNone(st["trash_expires_at_receiver"])

    def test_p0b_boundary_exactly_now_is_expired(self):
        """`<=` semantics are preserved: a timestamp equal to now is expired."""
        self._clear_messages()
        self._msg("m_now", sender_state="in_trash", s_exp=_now_str(0))
        self._run_cycle()
        self.assertEqual(self._msg_state("m_now")["sender_state"], "deleted")

    def test_p0b_null_empty_and_malformed_never_deleted(self):
        self._clear_messages()
        self._msg("m_null", sender_state="in_trash", s_exp=None, receiver_state="in_trash", r_exp=None)
        self._msg("m_empty", sender_state="in_trash", s_exp="", receiver_state="in_trash", r_exp="")
        self._msg("m_short", sender_state="in_trash", s_exp="1", receiver_state="in_trash", r_exp="1")
        self._msg("m_garbage", sender_state="in_trash", s_exp="not-a-date",
                  receiver_state="in_trash", r_exp="garbage value here")
        self._msg("m_zerodate", sender_state="in_trash", s_exp="0000-00-00 00:00:00",
                  receiver_state="in_trash", r_exp="0000-00-00 00:00:00")
        self._run_cycle()
        for mid in ("m_null", "m_empty", "m_short", "m_garbage", "m_zerodate"):
            st = self._msg_state(mid)
            self.assertEqual(st["sender_state"], "in_trash", f"{mid} sender must survive")
            self.assertEqual(st["receiver_state"], "in_trash", f"{mid} receiver must survive")

    def test_p0b_parse_helper_rejects_bad_values(self):
        self.assertIsNone(server._parse_message_utc_timestamp(None))
        self.assertIsNone(server._parse_message_utc_timestamp(""))
        self.assertIsNone(server._parse_message_utc_timestamp("2026-10"))
        self.assertIsNone(server._parse_message_utc_timestamp("2026-13-40 99:99:99"))
        self.assertIsNone(server._parse_message_utc_timestamp("0000-00-00 00:00:00"))
        self.assertIsNotNone(server._parse_message_utc_timestamp("2026-10-14 08:00:00"))

    def test_p0b_purge_requires_both_sides_and_returns_media(self):
        self._clear_messages()
        self._msg("m_one_side", sender_state="deleted", receiver_state="active")
        self._msg("m_both", sender_state="deleted", receiver_state="deleted", media="/uploads/chat_attachments/x.jpg")
        self._msg("m_everyone", sender_state="active", receiver_state="active",
                  deleted_everyone=1, media="/uploads/chat_attachments/y.jpg")
        files = self._run_cycle()
        self.assertIsNotNone(self._msg_state("m_one_side"), "one-sided delete must be retained")
        self.assertIsNone(self._msg_state("m_both"), "both-sides delete must be purged")
        # Deleted-for-everyone keeps its row (existing retention semantics) but
        # its media is scheduled for unlink.
        self.assertIsNotNone(self._msg_state("m_everyone"))
        self.assertIn("/uploads/chat_attachments/x.jpg", files)
        self.assertIn("/uploads/chat_attachments/y.jpg", files)

    def test_p0b_retention_keeps_trash_until_expiry(self):
        self._clear_messages()
        self._msg("m_keep", sender_state="in_trash", receiver_state="in_trash",
                  s_exp=_now_str(7200), r_exp=_now_str(7200))
        self._run_cycle()
        st = self._msg_state("m_keep")
        self.assertEqual(st["sender_state"], "in_trash")
        self.assertEqual(st["receiver_state"], "in_trash")

    def test_p0b_restored_message_is_not_expired_by_the_worker(self):
        """End to end: once POST /api/chat/messages/restore has run, a full
        expiry cycle must leave the message active and must not schedule its
        media for deletion (P1 review: a restore is never undone by the worker)."""
        self._clear_messages()
        media_url = "/uploads/chat_attachments/restored.jpg"
        self._msg("m_restored", sender_state="in_trash", s_exp=_now_str(-60), media=media_url)

        status, res = self._req("/api/chat/messages/restore", method="POST",
                                token=TOKEN_MAIN, body={"message_ids": ["m_restored"]})
        self.assertEqual(status, 200, res)
        self.assertTrue(res.get("success"))
        self.assertEqual(self._msg_state("m_restored")["sender_state"], "active")

        files = self._run_cycle()

        st = self._msg_state("m_restored")
        self.assertIsNotNone(st, "a restored message must never be purged")
        self.assertEqual(st["sender_state"], "active")
        self.assertIsNone(st["trash_expires_at_sender"])
        self.assertNotIn(media_url, files)

    def test_p0b_expiry_updates_re_check_trash_state_in_source(self):
        """Tripwire for the P1 review: within the expiration cycle both UPDATE
        statements must re-check the trash state (and the expiry they read), so a
        restore committing mid-cycle can never be overwritten. The behavioural
        proof on real PostgreSQL lives in test_p0_real_postgres
        (test_p1_restore_between_select_and_update_is_not_overwritten and its
        pre-fix control test_p1_legacy_unguarded_update_really_did_clobber_a_restore)."""
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
        with open(src_path, encoding="utf-8") as fh:
            src = fh.read()
        cycle = src[src.index("def _run_chat_expiration_cycle(conn):"):
                    src.index("def _chat_expiration_worker():")]
        self.assertIn("AND sender_state = 'in_trash' AND trash_expires_at_sender IS NOT NULL", cycle)
        self.assertIn("AND receiver_state = 'in_trash' AND trash_expires_at_receiver IS NOT NULL", cycle)
        self.assertNotIn("trash_expires_at_sender = NULL WHERE id = ?", cycle)
        self.assertNotIn("trash_expires_at_receiver = NULL WHERE id = ?", cycle)

    # --------------------------------------------- P0-B: connection lifecycle
    class _FakeCursor:
        def __init__(self, fail):
            self.fail = fail
            self.executed = []

        def execute(self, sql, params=None):
            if self.fail:
                raise RuntimeError("boom")
            self.executed.append(sql)
            return self

        def executemany(self, sql, seq):
            if self.fail:
                raise RuntimeError("boom")
            return self

        def fetchall(self):
            return []

    class _FakeConn:
        def __init__(self, fail=False):
            self.fail = fail
            self.committed = False
            self.rolled_back = False
            self.closed = False

        def cursor(self):
            return P0FeedAndWorkerTests._FakeCursor(self.fail)

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    def _one_worker_iteration(self, fake):
        original_get_db = server.get_db
        original_sleep = server.time.sleep

        class _StopLoop(Exception):
            pass

        def _stop(_seconds):
            raise _StopLoop()

        server.get_db = lambda: fake
        server.time.sleep = _stop
        try:
            server._chat_expiration_worker()
        except _StopLoop:
            pass
        finally:
            server.get_db = original_get_db
            server.time.sleep = original_sleep

    def test_p0b_worker_commits_and_closes_on_success(self):
        fake = self._FakeConn(fail=False)
        self._one_worker_iteration(fake)
        self.assertTrue(fake.committed, "successful cycle must commit")
        self.assertTrue(fake.closed, "connection must be closed on success")
        self.assertFalse(fake.rolled_back)

    def test_p0b_worker_rolls_back_and_closes_on_failure(self):
        fake = self._FakeConn(fail=True)
        self._one_worker_iteration(fake)
        self.assertTrue(fake.rolled_back, "failed transaction must roll back")
        self.assertTrue(fake.closed, "connection must be closed on failure")
        self.assertFalse(fake.committed, "failed cycle must not commit")


if __name__ == "__main__":
    unittest.main()
