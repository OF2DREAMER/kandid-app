#!/usr/bin/env python3
"""P0 hardening - REAL PostgreSQL integration tests.

These tests run the public community feed query and the chat expiration worker
against a genuine PostgreSQL server (bundled binaries via the optional
`pgserver` package). PostgreSQL is the only environment where the two audited
defects actually reproduce, so this module is the evidence that they are fixed:

  * P0-A: "SELECT p.*, u.*, c.* ... GROUP BY p.id" is rejected by PostgreSQL
    ("column u.name must appear in the GROUP BY clause ...").
  * P0-B: comparing the TEXT trash_expires_at_* columns with CURRENT_TIMESTAMP
    is rejected by PostgreSQL (text vs timestamp with time zone).
  * P1: the expiry UPDATE must not overwrite a message that the user restored
    between the cycle's SELECT and its write (see the deterministic race tests
    and their pre-fix control below).

Isolation / cleanup
-------------------
This module creates its OWN disposable PostgreSQL cluster in a unique
``mkdtemp()`` directory (``cleanup_mode="delete"``) and tears it down in a
module cleanup that also runs when a test or a setup step fails. It never
reads, stops, signals or deletes a shared/hardcoded path and never targets an
instance it did not start itself.

The module is skipped (never silently passed) when a real PostgreSQL server
cannot be started.

Run with:  python -m unittest test_p0_real_postgres
"""

import json
import os
import shutil
import socket
import tempfile
import unittest

import server
from server import KandidHandler

_TMP_BASE = None
_PGDATA = None
_PG = None
_PG_ERROR = None


def _pg_dsn():
    info = _PG.get_postmaster_info()
    return "postgresql://postgres:@/postgres?host=%s&port=%s" % (info.socket_dir, info.port)


def _cleanup_pg():
    global _PG
    pg, _PG = _PG, None
    if pg is not None:
        try:
            pg.cleanup()
        except Exception:
            pass
    if _TMP_BASE:
        base = os.path.abspath(_TMP_BASE)
        if (os.path.isdir(base)
                and os.path.dirname(base) == os.path.realpath(tempfile.gettempdir())
                and os.path.basename(base).startswith("kandid_p0_pg_")):
            shutil.rmtree(base, ignore_errors=True)


def tearDownModule():
    _cleanup_pg()


def setUpModule():
    global _TMP_BASE, _PGDATA, _PG, _PG_ERROR
    try:
        import pgserver  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "pgserver not installed: %s" % exc
        raise unittest.SkipTest(_PG_ERROR)

    try:
        _TMP_BASE = tempfile.mkdtemp(prefix="kandid_p0_pg_")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise unittest.SkipTest("could not create a temp directory: %r" % exc)
    _PGDATA = os.path.join(_TMP_BASE, "data")

    unittest.addModuleCleanup(_cleanup_pg)

    try:
        _PG = pgserver.get_server(_PGDATA, cleanup_mode="delete")
        _PG.ensure_postgres_running()
        import psycopg2
        c = psycopg2.connect(_pg_dsn())
        c.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        _PG_ERROR = "could not start an isolated disposable PostgreSQL: %r" % exc
        raise unittest.SkipTest(_PG_ERROR)


LEGACY_FEED_SQL = """
SELECT p.*,
       u.name as author_name,
       c.id as community_id
FROM posts p
JOIN communities c ON (
    (p.primary_community_id != '' AND p.primary_community_id IS NOT NULL AND (p.primary_community_id = c.id OR p.primary_community_id = c.name))
    OR (p.context_community_id != '' AND p.context_community_id IS NOT NULL AND (p.context_community_id = c.id OR p.context_community_id = c.name))
)
LEFT JOIN users u ON p.user_id = u.id
WHERE 1=1
GROUP BY p.id
ORDER BY p.created_at DESC
"""

LEGACY_EXPIRE_SQL = (
    "UPDATE messages SET sender_state = 'deleted', trash_expires_at_sender = NULL "
    "WHERE sender_state = 'in_trash' AND trash_expires_at_sender <= CURRENT_TIMESTAMP"
)

# The pre-fix expiry write: the id comes from a SELECT and the UPDATE re-checked
# nothing, so it overwrote whatever state the row had by then.
LEGACY_P1_EXPIRE_UPDATE = (
    "UPDATE messages SET sender_state = 'deleted', trash_expires_at_sender = NULL WHERE id = ?"
)

TOKEN_RESTORE = "tok_p0_real_pg_restore"


class _RestoreBeforeFirstUpdateCursor(object):
    """Cursor proxy that fires a callback just before the cycle's first UPDATE."""

    def __init__(self, real_cursor, owner):
        self._cursor = real_cursor
        self._owner = owner

    def execute(self, sql, params=None):
        return self._cursor.execute(sql, params)

    def executemany(self, sql, seq):
        if "UPDATE" in sql.upper():
            self._owner.run_restore_before_first_write()
        return self._cursor.executemany(sql, seq)

    def fetchall(self):
        return self._cursor.fetchall()


class RestoreBeforeFirstUpdateConn(object):
    """A real pooled connection that runs a committed restore mid-cycle.

    It reproduces the exact P1 interleaving

        SELECT expired ids  ->  POST /api/chat/messages/restore commits  ->  UPDATE

    deterministically (no sleeping, no timing assumptions): the restore is
    performed by the callback immediately before the cycle's first UPDATE is
    sent to PostgreSQL. Everything else is delegated to the real connection.
    """

    def __init__(self, real_conn, restore_fn):
        self._conn = real_conn
        self._restore_fn = restore_fn
        self.restore_calls = 0

    def cursor(self):
        return _RestoreBeforeFirstUpdateCursor(self._conn.cursor(), self)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def run_restore_before_first_write(self):
        if self.restore_calls == 0:
            self._restore_fn()
        self.restore_calls += 1


class RealPostgresP0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = _pg_dsn()
        server.init_db()

        cls.pub_a = "pg_pub_a"
        cls.pub_b = "pg_pub_b"
        cls.priv = "pg_priv"
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts")
        cursor.execute("DELETE FROM messages")
        cursor.execute("DELETE FROM communities")
        cursor.execute("DELETE FROM users")
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt, campus, role, "
            "email_verified, is_onboarded, account_status) VALUES "
            "('pg_u1', 'pg1@test.com', 'pgone', 'PG One', 'h', 's', 'Campus', 'student', 1, 1, 'active')"
        )
        cursor.execute(
            "INSERT INTO sessions (id, user_id, token, expires_at) "
            "VALUES ('pg_sess_1', 'pg_u1', ?, '2099-01-01T00:00:00Z')",
            (TOKEN_RESTORE,),
        )
        cursor.execute(
            "INSERT INTO communities (id, name, type, city, description, visibility, members_count, moderation_status) "
            "VALUES ('pg_pub_a', 'PG Public A', 'Interest', 'Delhi', '', 'public', 5, 'active'), "
            "('pg_pub_b', 'PG Public B', 'Campus', 'Delhi', '', 'public', 5, 'active'), "
            "('pg_priv', 'PG Private', 'Interest', 'Delhi', '', 'private', 5, 'active')"
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DATABASE_URL = cls._orig_url

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

        body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
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
        t.join(timeout=5.0)

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

    def _insert_post(self, pid, primary="", context="", is_private=0, created_at="2026-10-14 08:00:00"):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_handle, author_name, main_img, pip_img, caption, "
            "primary_community_id, context_community_id, circle, is_private, created_at, moderation_status) "
            "VALUES (?, 'pg_u1', 'pgone', 'PG One', 'm', 'p', 'cap', ?, ?, 'campus', ?, ?, 'active')",
            (pid, primary, context, is_private, created_at),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------- seed SQL uses IN/OR sanity
    # -------------------------------------------------------- defect reproduction
    def test_p0a_legacy_group_by_query_is_rejected_by_postgres(self):
        """Proof the environment reproduces P0-A: the old OR-join + GROUP BY fails."""
        self._insert_post("pg_legacy_probe", primary=self.pub_a)
        conn = server.get_db()
        cursor = conn.cursor()
        raised = False
        try:
            cursor.execute(LEGACY_FEED_SQL)
            cursor.fetchall()
        except Exception:
            raised = True
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
        self.assertTrue(raised, "legacy GROUP BY query must be rejected on PostgreSQL")

    def test_p0b_legacy_current_timestamp_comparison_is_rejected_by_postgres(self):
        """Proof the environment reproduces P0-B: text <= CURRENT_TIMESTAMP fails."""
        conn = server.get_db()
        cursor = conn.cursor()
        raised = False
        try:
            cursor.execute(LEGACY_EXPIRE_SQL)
        except Exception:
            raised = True
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
        self.assertTrue(raised, "legacy CURRENT_TIMESTAMP comparison must be rejected on PostgreSQL")

    # --------------------------------------------------------------- P0-A fix
    def test_p0a_feed_endpoints_return_200_on_postgres(self):
        self._insert_post("pg_feed_1", primary=self.pub_a)
        for view in ("pulse", "moments"):
            status, res = self._req(f"/api/community/public-feed?view={view}")
            self.assertEqual(status, 200, f"{view} must succeed on PostgreSQL: {res}")
            self.assertTrue(res.get("success"))

    def test_p0a_primary_and_context_resolution_on_postgres(self):
        self._insert_post("pg_primary", primary=self.pub_a)
        self._insert_post("pg_context", context=self.pub_b)
        self._insert_post("pg_both", primary=self.pub_a, context=self.pub_b)

        _, res = self._req("/api/community/public-feed?view=moments")
        by_id = {}
        for m in res.get("moments", []):
            by_id.setdefault(m["id"], []).append(m)

        self.assertEqual(len(by_id.get("pg_primary", [])), 1)
        self.assertEqual(by_id["pg_primary"][0]["community_id"], self.pub_a)
        self.assertEqual(len(by_id.get("pg_context", [])), 1)
        self.assertEqual(by_id["pg_context"][0]["community_id"], self.pub_b)
        # primary + context must NOT duplicate, and must prefer primary
        self.assertEqual(len(by_id.get("pg_both", [])), 1)
        self.assertEqual(by_id["pg_both"][0]["community_id"], self.pub_a)

    def test_p0a_private_community_excluded_on_postgres(self):
        self._insert_post("pg_private_post", primary=self.priv)
        _, res = self._req("/api/community/public-feed?view=moments")
        ids = [m["id"] for m in res.get("moments", [])]
        self.assertNotIn("pg_private_post", ids)

    # --------------------------------------------------------------- P0-B fix
    def _msg(self, mid, sender_state="active", receiver_state="active", s_exp=None, r_exp=None,
             media=None):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (id, sender_id, receiver_id, content, sender_state, receiver_state, "
            "trash_expires_at_sender, trash_expires_at_receiver, is_deleted_for_everyone, media_url) "
            "VALUES (?, 'pg_u1', 'pg_u1', 'hi', ?, ?, ?, ?, 0, ?)",
            (mid, sender_state, receiver_state, s_exp, r_exp, media),
        )
        conn.commit()
        conn.close()

    def _state(self, mid):
        conn = server.get_db()
        row = conn.execute(
            "SELECT sender_state, receiver_state, trash_expires_at_sender, "
            "trash_expires_at_receiver FROM messages WHERE id = ?", (mid,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _restore_via_endpoint(self, message_id, token=TOKEN_RESTORE):
        """Perform the real user action: POST /api/chat/messages/restore."""
        status, res = self._req(
            "/api/chat/messages/restore", method="POST", token=token,
            body={"message_ids": [message_id]},
        )
        self.assertEqual(status, 200, "restore endpoint must succeed: %r" % (res,))
        self.assertTrue(res.get("success"), "restore must report success: %r" % (res,))

    def test_p0b_expiration_cycle_runs_on_postgres(self):
        self._msg("pg_exp_s", sender_state="in_trash", s_exp="2020-01-01 00:00:00")
        self._msg("pg_exp_r", receiver_state="in_trash", r_exp="2020-01-01 00:00:00")
        self._msg("pg_future", sender_state="in_trash", s_exp="2999-01-01 00:00:00")
        self._msg("pg_bad", sender_state="in_trash", s_exp="not-a-date")
        self._msg("pg_null", sender_state="in_trash", s_exp=None)

        conn = server.get_db()
        server._run_chat_expiration_cycle(conn)
        conn.commit()
        conn.close()

        self.assertEqual(self._state("pg_exp_s")["sender_state"], "deleted")
        self.assertEqual(self._state("pg_exp_r")["receiver_state"], "deleted")
        self.assertEqual(self._state("pg_future")["sender_state"], "in_trash")
        self.assertEqual(self._state("pg_bad")["sender_state"], "in_trash")
        self.assertEqual(self._state("pg_null")["sender_state"], "in_trash")

    # ------------------------------------------------- P1: SELECT/restore/UPDATE
    def test_p1_isolation_level_is_read_committed(self):
        """The race tests below rely on PostgreSQL re-evaluating the UPDATE
        predicate against the newest committed row version (READ COMMITTED).
        Assert that here instead of assuming it."""
        conn = server.get_db()
        row = conn.execute("SHOW transaction_isolation").fetchone()
        conn.close()
        self.assertEqual(dict(row)["transaction_isolation"], "read committed")

    def test_p1_legacy_unguarded_update_really_did_clobber_a_restore(self):
        """Control with teeth for the regression test below.

        Uses the PRE-FIX statement (id-only WHERE) with the same deterministic
        interleaving: the cycle's SELECT reads the id, the real restore endpoint
        commits, then the write runs. This shows the interleaving is real and
        detected in this environment, i.e. the fix - not the harness - is what
        protects the restored message.
        """
        mid = "pg_p1_legacy_clobber"
        self._msg(mid, sender_state="in_trash", s_exp="2020-01-01 00:00:00")

        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM messages WHERE sender_state = 'in_trash' "
            "AND trash_expires_at_sender IS NOT NULL"
        )
        ids = [row["id"] for row in cursor.fetchall()]
        self.assertIn(mid, ids, "the cycle's SELECT must have seen the message")

        self._restore_via_endpoint(mid)
        self.assertEqual(self._state(mid)["sender_state"], "active")

        cursor.executemany(LEGACY_P1_EXPIRE_UPDATE, [(i,) for i in ids])
        conn.commit()
        conn.close()

        state = self._state(mid)
        self.assertIsNotNone(state)
        self.assertEqual(
            state["sender_state"], "deleted",
            "pre-fix behaviour: the id-only UPDATE overwrites a completed restore",
        )

    def test_p1_restore_between_select_and_update_is_not_overwritten(self):
        """The regression: a restore that commits between the cycle's SELECT
        and its expiry UPDATE must survive untouched (P1 review finding).

        Deterministic - the real /api/chat/messages/restore endpoint is invoked
        from inside the running cycle, immediately before the first UPDATE.
        """
        mid = "pg_p1_race_restore"
        media_url = "/uploads/chat_attachments/pg_p1_race.jpg"
        self._msg(mid, sender_state="in_trash", s_exp="2020-01-01 00:00:00", media=media_url)

        cycle_conn = server.get_db()
        proxy = RestoreBeforeFirstUpdateConn(
            cycle_conn, lambda: self._restore_via_endpoint(mid)
        )
        try:
            media_to_delete = server._run_chat_expiration_cycle(proxy)
            cycle_conn.commit()
        finally:
            cycle_conn.close()

        self.assertEqual(
            proxy.restore_calls, 1,
            "the test must actually interleave a committed restore before the UPDATE",
        )
        state = self._state(mid)
        self.assertIsNotNone(state, "the restored message must still exist")
        self.assertEqual(
            state["sender_state"], "active",
            "the expiry UPDATE must not overwrite a completed restore",
        )
        self.assertIsNone(state["trash_expires_at_sender"])
        self.assertNotIn(media_url, media_to_delete,
                         "media of a restored message must not be scheduled for deletion")

    def test_p1_restored_message_survives_a_full_expiry_cycle(self):
        """End to end: restore a message first, then run a whole cycle; the
        message must survive as 'active' with its media untouched."""
        mid = "pg_p1_restored_survivor"
        media_url = "/uploads/chat_attachments/pg_p1_kept.jpg"
        self._msg(mid, sender_state="in_trash", receiver_state="in_trash",
                  s_exp="2020-01-01 00:00:00", r_exp="2020-01-01 00:00:00", media=media_url)

        self._restore_via_endpoint(mid)
        self.assertEqual(self._state(mid)["sender_state"], "active")

        conn = server.get_db()
        media_to_delete = server._run_chat_expiration_cycle(conn)
        conn.commit()
        conn.close()

        state = self._state(mid)
        self.assertIsNotNone(state, "a restored message must never be purged")
        self.assertEqual(state["sender_state"], "active")
        self.assertIsNone(state["trash_expires_at_sender"])
        self.assertNotIn(media_url, media_to_delete)


if __name__ == "__main__":
    unittest.main()
