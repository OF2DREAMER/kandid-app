#!/usr/bin/env python3
"""
pg8000 tuple-row compatibility coverage for PostgreSQL.

Failure being pinned:
  server.PostgresConnectionWrapper.cursor() asks psycopg2 for DictCursor rows.
  pg8000 has no DictCursor, so the wrapper fell back to a plain tuple cursor and
  every ``dict(row)`` / ``row["col"]`` access on the request path raised
  (get_current_user() -> dict(row) surfaced first). PostgresCursorWrapper now
  normalises tuple rows into PostgresRowMapping, a dict subclass that also
  supports positional indexing, so both drivers expose one row contract.

  A. PostgresCursorWrapper row contract (fake cursors: shapes, NULLs, aliases,
     duplicate names, no silent empties).
  B. Real psycopg2 vs real pg8000 rows, authentication and
     POST /api/moments/capture against a disposable PostgreSQL database.
  C. Pooled connection / cursor lifecycle on success and on exception.

The integration classes never touch a non-loopback host or a database whose name
does not end in "_test". Without KANDID_TEST_POSTGRES_URL they skip; when the URL
is present a missing driver fails loudly instead of skipping.

Run (both drivers installed):
  KANDID_TEST_POSTGRES_URL=postgresql://user@127.0.0.1:5432/kindid_pg8000_test \
      python3 test_pg8000_row_shape.py -v
"""

import collections.abc
import contextlib
import importlib
import json
import os
import socket
import sys
import threading
import unittest
import urllib.parse
import uuid

# Configure the environment BEFORE importing server (project convention).
os.environ.pop("DATABASE_URL", None)
os.environ["ENVIRONMENT"] = "development"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler, PostgresCursorWrapper, PostgresRowMapping

PG_URL = os.environ.get("KANDID_TEST_POSTGRES_URL")
PG_SKIP_REASON = (
    "set KANDID_TEST_POSTGRES_URL to a disposable PostgreSQL database to run the"
    " pg8000 compatibility checks"
)

MEDIA_MAIN = "/uploads/pg8000_main.jpg"
MEDIA_PIP = "/uploads/pg8000_pip.jpg"

_MISSING = object()


def _description(*names):
    """A pg8000-shaped cursor.description (name is the only field we read)."""
    return [(name, 25, None, None, None, None, None) for name in names]


class FakeCursor(object):
    """Minimal DB-API cursor: returns whatever rows it was given."""

    def __init__(self, description, rows):
        self.description = description
        self._rows = list(rows)

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self):
        rows, self._rows = self._rows, []
        return iter(rows)


class MappingShapedRow(collections.abc.Mapping):
    """A non-dict, mapping-shaped row (a third-party cursor implementation).

    Real psycopg2 DictRow rows are exercised in
    test_real_dictrow_row_contract.py; a hand-written ``dict`` stand-in is not
    used here because it would misrepresent their sequence behaviour.
    """

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        if isinstance(key, int):
            raise TypeError("integer subscripts are not supported")
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class ARowContract(unittest.TestCase):
    """The wrapper row contract, independent of any live database."""

    def test_01_pg8000_tuple_rows_become_dict_mappings(self):
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [("u1", "u1@example.test")])
        )
        row = cursor.fetchone()
        self.assertIsInstance(row, PostgresRowMapping)
        self.assertIsInstance(row, dict)
        self.assertEqual(dict(row), {"id": "u1", "email": "u1@example.test"})
        self.assertEqual(row["email"], "u1@example.test")

    def test_02_fetchall_and_iteration_keep_column_value_alignment(self):
        rows = [("u1", "a@example.test"), ("u2", "b@example.test")]
        cursor = PostgresCursorWrapper(FakeCursor(_description("id", "email"), rows))
        fetched = cursor.fetchall()
        self.assertEqual(
            [dict(r) for r in fetched],
            [
                {"id": "u1", "email": "a@example.test"},
                {"id": "u2", "email": "b@example.test"},
            ],
        )

        cursor = PostgresCursorWrapper(FakeCursor(_description("id", "email"), rows))
        iterated = list(cursor)
        self.assertEqual([r["id"] for r in iterated], ["u1", "u2"])
        self.assertEqual([r["email"] for r in iterated], ["a@example.test", "b@example.test"])

    def test_03_null_values_are_preserved(self):
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "avatar_url"), [("u1", None)])
        )
        row = cursor.fetchone()
        self.assertIsNone(row["avatar_url"])
        self.assertIn("avatar_url", row)
        self.assertEqual(dict(row), {"id": "u1", "avatar_url": None})

    def test_04_aliased_and_duplicate_columns(self):
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("display_name"), [("Alias Handle",)])
        )
        self.assertEqual(cursor.fetchone()["display_name"], "Alias Handle")

        # psycopg2's DictCursor keeps the LAST value for a duplicated column
        # name while positional access still sees the original position.
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "id"), [("first", "second")])
        )
        row = cursor.fetchone()
        self.assertEqual(row["id"], "second")
        self.assertEqual(row[0], "first")
        self.assertEqual(row[1], "second")
        self.assertEqual(len(row), 1)

    def test_05_mapping_shaped_rows_pass_through_unchanged(self):
        # The pass-through rule is capability-based, so any non-dict row that
        # already exposes keys()/column subscripts survives untouched instead
        # of being silently re-typed.
        original = MappingShapedRow({"id": "u1", "email": "u1@example.test"})
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [original])
        )
        self.assertIs(cursor.fetchone(), original)
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [original])
        )
        self.assertIs(cursor.fetchall()[0], original)

    def test_06_statements_without_description_return_no_rows(self):
        cursor = PostgresCursorWrapper(FakeCursor(None, [("ignored",)]))
        self.assertIsNone(cursor.fetchone())
        self.assertEqual(cursor.fetchall(), [])
        self.assertEqual(list(cursor), [])

    def test_07_row_supports_dictrow_style_access(self):
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [("u1", "u1@example.test")])
        )
        row = cursor.fetchone()
        self.assertEqual(row[0], "u1")
        self.assertEqual(row[-1], "u1@example.test")
        self.assertEqual(list(row.keys()), ["id", "email"])
        self.assertEqual(row.get("missing"), None)
        self.assertEqual(dict(row), {"id": "u1", "email": "u1@example.test"})

    def test_08_description_row_length_mismatch_raises(self):
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [("only-one-value",)])
        )
        with self.assertRaises(ValueError):
            cursor.fetchone()

        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id"), [("a", "b", "c")])
        )
        with self.assertRaises(ValueError):
            cursor.fetchall()

    def test_09_bytes_column_names_are_decoded(self):
        description = [(b"id", 25, None, None, None, None, None)]
        cursor = PostgresCursorWrapper(FakeCursor(description, [("u1",)]))
        row = cursor.fetchone()
        self.assertEqual(row["id"], "u1")
        self.assertEqual(dict(row), {"id": "u1"})

    # -- R2: mapping-shaped rows must never become positional rows ---------
    def test_10_mapping_row_with_unresolvable_column_is_rejected(self):
        # keys() succeeds, but the described first column is absent. The row is
        # mapping-shaped, so its iteration yields KEYS; converting it would
        # silently store "id"/"email" as the column values.
        original = MappingShapedRow({"id": "u1", "email": "u1@example.test"})
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("user_id", "user_email"), [original])
        )
        with self.assertRaises(server.PostgresRowShapeError) as ctx:
            cursor.fetchone()
        self.assertIn("user_id", str(ctx.exception))
        self.assertIn("MappingShapedRow", str(ctx.exception))
        # The row itself was neither mutated nor consumed.
        self.assertEqual(
            dict(original), {"id": "u1", "email": "u1@example.test"}
        )

        # fetchall() and iteration take the same path, not a silent fallback.
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("user_id"), [original])
        )
        with self.assertRaises(server.PostgresRowShapeError):
            cursor.fetchall()
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("user_id"), [original])
        )
        with self.assertRaises(server.PostgresRowShapeError):
            list(cursor)

    def test_11_mapping_row_lookup_errors_are_not_swallowed(self):
        # Only "column absent" errors are classified. A defect inside the row
        # implementation must surface as itself, never as a normalisation
        # decision and never as a rewritten row.
        class ExplodingRow(MappingShapedRow):
            def __getitem__(self, key):
                raise RuntimeError("row lookup blew up")

        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id"), [ExplodingRow({"id": 1})])
        )
        with self.assertRaises(RuntimeError) as ctx:
            cursor.fetchone()
        self.assertNotIsInstance(ctx.exception, server.PostgresRowShapeError)
        self.assertIn("blew up", str(ctx.exception))

    def test_12_equal_width_key_mismatch_never_converts_keys_to_values(self):
        # Same apparent width, different keys: the dangerous case, because a
        # positional conversion would succeed structurally while losing every
        # value (it would store the keys instead).
        original = MappingShapedRow({"first": 1, "second": 2})
        self.assertEqual(len(original), 2)
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("one", "two"), [original])
        )
        with self.assertRaises(server.PostgresRowShapeError):
            cursor.fetchone()
        # No PostgresRowMapping was produced from the keys.
        self.assertEqual(list(original.values()), [1, 2])
        self.assertEqual(list(original.keys()), ["first", "second"])

    def test_13_unnamed_first_column_preserves_the_mapping_row(self):
        # An empty column name cannot be probed; preserving the row is the only
        # safe choice (converting could still turn keys into values).
        original = MappingShapedRow({"": "v"})
        cursor = PostgresCursorWrapper(FakeCursor([("",)], [original]))
        self.assertIs(cursor.fetchone(), original)

    def test_14_malformed_description_raises_a_descriptive_error(self):
        cursor = PostgresCursorWrapper(FakeCursor([123], [("v",)]))
        with self.assertRaises(server.PostgresRowShapeError) as ctx:
            cursor.fetchone()
        self.assertIn("description", str(ctx.exception).lower())

    def test_15_valid_mapping_row_and_tuple_row_keep_their_shapes(self):
        # The R2 fix must not disturb the happy paths: a matching mapping row is
        # returned as-is, and a bare pg8000 row is still normalised.
        mapping_row = MappingShapedRow({"id": "u1", "email": "u1@example.test"})
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [mapping_row])
        )
        self.assertIs(cursor.fetchone(), mapping_row)

        tuple_row = ("u1", "u1@example.test")
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "email"), [tuple_row])
        )
        normalised = cursor.fetchone()
        self.assertIsInstance(normalised, PostgresRowMapping)
        self.assertEqual(dict(normalised), {"id": "u1", "email": "u1@example.test"})

    def test_16_iteration_yields_positional_values(self):
        # A normalised pg8000 row replaces a tuple, so it has to iterate its
        # VALUES in positional order. A plain dict subclass iterates keys,
        # which silently turned list(row)/tuple(row) into column names and
        # broke callers that treat a row as a sequence.
        cursor = PostgresCursorWrapper(
            FakeCursor(
                _description("id", "email", "score"),
                [("u1", "u1@example.test", 7)],
            )
        )
        row = cursor.fetchone()
        self.assertEqual(list(row), ["u1", "u1@example.test", 7])
        self.assertEqual(tuple(row), ("u1", "u1@example.test", 7))
        self.assertEqual([value for value in row], ["u1", "u1@example.test", 7])
        self.assertEqual(list(reversed(list(row))), [7, "u1@example.test", "u1"])

        # fetchall and cursor iteration agree with fetchone.
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("a", "b"), [(1, 2), (3, 4)])
        )
        self.assertEqual([list(r) for r in cursor.fetchall()], [[1, 2], [3, 4]])
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("a", "b"), [(1, 2), (3, 4)])
        )
        self.assertEqual([list(r) for r in cursor], [[1, 2], [3, 4]])

        # Duplicate column names collapse in the mapping, never in iteration:
        # every position survives, in order, including the shadowed one.
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "id", "n"), [("first", "second", 3)])
        )
        dup = cursor.fetchone()
        self.assertEqual(list(dup), ["first", "second", 3])
        self.assertEqual(tuple(dup), ("first", "second", 3))
        first, second, third = dup
        self.assertEqual((first, second, third), ("first", "second", 3))

        # Keyed, positional, .get() and dict() access are unchanged.
        self.assertEqual(dup["id"], "second")
        self.assertEqual(dup[0], "first")
        self.assertEqual(dup[1], "second")
        self.assertEqual(dict(dup), {"id": "second", "n": 3})
        self.assertIsNone(dup.get("missing"))

        # len() keeps the unique-key count it had before: only "id" and "n".
        self.assertEqual(len(dup), 2)
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "id"), [("first", "second")])
        )
        self.assertEqual(len(cursor.fetchone()), 1)

        # NULL values iterate as None, not as anything else.
        cursor = PostgresCursorWrapper(
            FakeCursor(_description("id", "gone"), [("u2", None)])
        )
        null_row = cursor.fetchone()
        self.assertEqual(list(null_row), ["u2", None])
        self.assertEqual(tuple(null_row), ("u2", None))


def _request(path, token, body, timeout=30.0):
    """Drive the REAL handler over a socket pair. Returns (status, payload)."""
    s1, s2 = socket.socketpair()

    class DummyServer(object):
        pass

    def run_handler():
        try:
            KandidHandler(s1, ("127.0.0.1", 12345), DummyServer())
        except BaseException:
            pass
        finally:
            try:
                s1.close()
            except Exception:
                pass

    thread = threading.Thread(target=run_handler, daemon=True)
    thread.start()

    raw_body = json.dumps(body).encode("utf-8")
    raw_request = (
        f"POST {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        f"Authorization: Bearer {token}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(raw_body)}\r\n\r\n"
    ).encode("utf-8") + raw_body

    s2.settimeout(timeout)
    s2.sendall(raw_request)
    try:
        s2.shutdown(socket.SHUT_WR)
    except OSError:
        pass

    chunks = []
    while True:
        try:
            chunk = s2.recv(8192)
        except socket.timeout:
            break
        if not chunk:
            break
        chunks.append(chunk)
    s2.close()
    thread.join(timeout=timeout)

    raw = b"".join(chunks).decode("utf-8", "replace")
    head, _, body_text = raw.partition("\r\n\r\n")
    status_line = head.splitlines()[0] if head else "HTTP/1.1 0"
    status = int(status_line.split()[1])
    try:
        payload = json.loads(body_text)
    except Exception:
        payload = body_text
    return status, payload


class PgDriverTestBase(unittest.TestCase):
    """Shared dispose-only-PostgreSQL fixture for the driver parity classes."""

    _created_users = []
    _original_url = None
    _original_env = None

    @classmethod
    def setUpClass(cls):
        if not PG_URL:
            raise unittest.SkipTest(PG_SKIP_REASON)
        parsed = urllib.parse.urlsplit(PG_URL)
        host = (parsed.hostname or "").strip().lower()
        dbname = (parsed.path or "").lstrip("/")
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(
                "refusing to run: KANDID_TEST_POSTGRES_URL must point at a loopback/"
                f"disposable host (got {host!r})"
            )
        if not dbname.endswith("_test"):
            raise AssertionError(
                "refusing to run: database name must end with '_test' (got %r)" % dbname
            )
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise AssertionError(
                "psycopg2 is required for the driver-parity baseline: %s "
                "(install psycopg2-binary)" % exc
            )
        try:
            import pg8000  # noqa: F401
        except ImportError as exc:
            raise AssertionError(
                "pg8000 is required for the pg8000 compatibility checks: %s "
                "(install pg8000)" % exc
            )
        os.environ["DB_POOL_MAX"] = os.environ.get("DB_POOL_MAX", "8")
        cls._original_url = server.DATABASE_URL
        cls._original_env = os.environ.get("ENVIRONMENT")
        server.DATABASE_URL = PG_URL
        os.environ["ENVIRONMENT"] = "development"
        cls._reset_pool()
        server.init_db()
        import pg8000
        import psycopg2
        print(
            "\n[PG] host=%s db=%s psycopg2=%s pg8000=%s"
            % (host, dbname, psycopg2.__version__, pg8000.__version__)
        )

    @classmethod
    def tearDownClass(cls):
        try:
            conn = server.get_db()
            cursor = conn.cursor()
            for uid in cls._created_users:
                for table in ("xp_history", "posts", "sessions"):
                    try:
                        cursor.execute("DELETE FROM %s WHERE user_id = ?" % table, (uid,))
                    except Exception:
                        pass
                try:
                    cursor.execute("DELETE FROM users WHERE id = ?", (uid,))
                except Exception:
                    pass
            conn.commit()
            conn.close()
        finally:
            cls._reset_pool()
            server.DATABASE_URL = cls._original_url
            if cls._original_env is None:
                os.environ.pop("ENVIRONMENT", None)
            else:
                os.environ["ENVIRONMENT"] = cls._original_env

    # -- driver / pool plumbing ------------------------------------------
    @classmethod
    def _reset_pool(cls):
        try:
            server._release_checked_out_pooled_connections()
        except Exception:
            pass
        pool = getattr(server, "_PG_POOL", None)
        server._PG_POOL = None
        server._PG_POOL_DSN = None
        if pool is not None:
            try:
                pool.close_all()
            except Exception:
                pass

    @contextlib.contextmanager
    def driver_mode(self, name):
        """Force one driver for the duration of the block.

        pg8000 mode hides psycopg2, which is exactly the runtime situation the
        fallback exists for: _create_raw_postgres_connection() and
        PostgresConnectionWrapper.cursor() both take their ImportError branch.
        """
        names = ("psycopg2", "psycopg2.extras")
        saved = {n: sys.modules.get(n, _MISSING) for n in names}
        try:
            if name == "pg8000":
                for n in names:
                    sys.modules[n] = None
            elif name == "psycopg2":
                for n in names:
                    sys.modules[n] = importlib.import_module(n)
            else:
                raise ValueError("unknown driver mode %r" % (name,))
            self._reset_pool()
            yield name
        finally:
            for n, module in saved.items():
                if module is _MISSING:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = module
            self._reset_pool()

    # -- helpers ---------------------------------------------------------
    def _driver_module(self):
        conn = server.get_db()
        try:
            return type(conn.raw_conn).__module__
        finally:
            conn.close()

    def _raw_row(self, sql, params=None):
        conn = server.get_db()
        try:
            raw_cursor = conn.raw_conn.cursor()
            raw_cursor.execute(sql, params) if params is not None else raw_cursor.execute(sql)
            row = raw_cursor.fetchone()
            try:
                raw_cursor.close()
            except Exception:
                pass
            return row
        finally:
            conn.close()

    def _sql(self, sql, params=(), fetch=False):
        conn = server.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall() if fetch else None
            conn.commit()
            return rows
        finally:
            conn.close()

    def _make_user(self, prefix="pgrow"):
        uid = "%s_%s" % (prefix, uuid.uuid4().hex[:10])
        token = "tok_%s" % uuid.uuid4().hex
        self._sql(
            "INSERT INTO users (id, email, handle, name, password_hash, salt)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (uid, uid + "@example.test", uid, "PG Row " + uid, "h", "s"),
        )
        self._sql(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at)"
            " VALUES (?, ?, ?, '2099-01-01T00:00:00', '2026-01-01T00:00:00')",
            ("sess_" + uuid.uuid4().hex[:10], token, uid),
        )
        type(self)._created_users.append(uid)
        return uid, token

    def _capture(self, token, caption):
        return _request(
            "/api/moments/capture",
            token,
            {"caption": caption, "mainImg": MEDIA_MAIN, "pipImg": MEDIA_PIP},
        )


class BDriverParity(PgDriverTestBase):
    """Real driver behaviour against disposable PostgreSQL."""

    def test_10_pg8000_is_really_active_and_returns_tuples(self):
        with self.driver_mode("pg8000"):
            self.assertTrue(
                self._driver_module().startswith("pg8000"),
                "expected the pg8000 driver, got %r" % self._driver_module(),
            )
            raw = self._raw_row("SELECT 1 AS one")
            # pg8000 1.31.6 hands back a list (older releases used tuples); either
            # way it is a bare sequence with no column names attached.
            self.assertIsInstance(raw, (list, tuple))
            self.assertNotIsInstance(raw, dict)

            conn = server.get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 AS one, 2 AS two")
                row = cursor.fetchone()
            finally:
                conn.close()
            self.assertIsInstance(row, PostgresRowMapping)
            self.assertEqual(dict(row), {"one": 1, "two": 2})
            self.assertEqual(row[1], 2)

    def test_11_same_row_values_under_both_drivers(self):
        uid, _token = self._make_user()
        sql = "SELECT id, email, handle FROM users WHERE id = ?"
        seen = {}
        for mode in ("psycopg2", "pg8000"):
            with self.driver_mode(mode):
                conn = server.get_db()
                try:
                    cursor = conn.cursor()
                    cursor.execute(sql, (uid,))
                    row = cursor.fetchone()
                finally:
                    conn.close()
                # psycopg2 rows are real DictRow objects (a list subclass) and
                # must survive untouched; only pg8000 tuples are normalised.
                if mode == "psycopg2":
                    import psycopg2.extras

                    self.assertIsInstance(
                        row,
                        psycopg2.extras.DictRow,
                        "psycopg2 rows must pass through as real DictRow objects",
                    )
                else:
                    self.assertIsInstance(
                        row,
                        PostgresRowMapping,
                        "pg8000 tuple rows must be normalised",
                    )
                self.assertEqual(row[0], uid)
                self.assertEqual(row["id"], uid)
                seen[mode] = dict(row)
        self.assertEqual(seen["pg8000"], seen["psycopg2"])
        self.assertEqual(seen["pg8000"]["handle"], uid)

    def test_12_authentication_succeeds_with_pg8000(self):
        uid, token = self._make_user()
        headers = {"Authorization": "Bearer " + token}
        users = {}
        for mode in ("psycopg2", "pg8000"):
            with self.driver_mode(mode):
                user = server.get_current_user(headers)
                self.assertIsNotNone(user, "get_current_user() returned None under %s" % mode)
                users[mode] = user
        self.assertEqual(users["pg8000"]["id"], uid)
        for key in ("id", "email", "handle", "name"):
            self.assertEqual(
                users["pg8000"].get(key), users["psycopg2"].get(key),
                "field %r differs between drivers" % key,
            )

    def test_13_capture_succeeds_through_pg8000(self):
        uid, token = self._make_user()
        with self.driver_mode("pg8000"):
            status, payload = self._capture(token, "pg8000 capture")
        self.assertEqual(status, 201, payload)
        self.assertTrue(payload.get("success"), payload)
        post = payload.get("post") or {}
        self.assertTrue(post.get("id"), payload)

        rows = self._sql(
            "SELECT id, user_id, main_img, pip_img FROM posts WHERE user_id = ?",
            (uid,),
            fetch=True,
        )
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["id"], post["id"])
        self.assertEqual(rows[0]["main_img"], MEDIA_MAIN)
        self.assertEqual(rows[0]["pip_img"], MEDIA_PIP)

    def test_14_capture_still_works_through_psycopg2(self):
        uid, token = self._make_user()
        with self.driver_mode("psycopg2"):
            status, payload = self._capture(token, "psycopg2 capture")
        self.assertEqual(status, 201, payload)
        self.assertTrue(payload.get("success"), payload)
        rows = self._sql("SELECT id FROM posts WHERE user_id = ?", (uid,), fetch=True)
        self.assertEqual(len(rows), 1, rows)

    def test_15_unauthorized_request_still_rejected_under_pg8000(self):
        with self.driver_mode("pg8000"):
            status, payload = _request(
                "/api/moments/capture",
                "tok_does_not_exist",
                {"caption": "nope", "mainImg": MEDIA_MAIN, "pipImg": MEDIA_PIP},
            )
        self.assertIn(status, (401, 403), payload)


class CLifecycle(PgDriverTestBase):
    """Pooled connection and cursor lifecycle for both drivers."""

    def test_16_success_path_returns_connection_to_pool(self):
        for mode in ("psycopg2", "pg8000"):
            with self.driver_mode(mode):
                conn = server.get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT 1 AS one")
                self.assertEqual(cursor.fetchone()["one"], 1)
                conn.commit()
                conn.close()
                self.assertTrue(getattr(conn, "_released", False), mode)
                self.assertEqual(server._checked_out_list(), [], mode)

    def test_17_exception_path_rolls_back_and_releases(self):
        for mode in ("psycopg2", "pg8000"):
            with self.driver_mode(mode):
                uid = "pgrow_rb_%s" % uuid.uuid4().hex[:10]
                conn = server.get_db()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO users (id, email, handle, name, password_hash, salt)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (uid, uid + "@example.test", uid, "Rollback", "h", "s"),
                    )
                    raise RuntimeError("simulated failure before commit")
                except RuntimeError:
                    conn.rollback()
                finally:
                    conn.close()
                self.assertTrue(getattr(conn, "_released", False), mode)
                self.assertEqual(server._checked_out_list(), [], mode)

                rows = self._sql("SELECT id FROM users WHERE id = ?", (uid,), fetch=True)
                self.assertEqual(rows, [], "%s persisted a rolled-back row" % mode)

    def test_18_cursor_after_release_raises_for_both_drivers(self):
        for mode in ("psycopg2", "pg8000"):
            with self.driver_mode(mode):
                conn = server.get_db()
                conn.close()
                with self.assertRaises(RuntimeError):
                    conn.cursor()


if __name__ == "__main__":
    unittest.main(verbosity=2)
