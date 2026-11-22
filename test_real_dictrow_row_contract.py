#!/usr/bin/env python3
"""F4: real psycopg2 DictRow vs pg8000 tuple rows, against a disposable PostgreSQL.

The C-3 candidate claimed psycopg2 rows "are never converted", assuming
``psycopg2.extras.DictRow`` subclasses ``dict``. It does not -- it subclasses
``list`` -- so the old ``isinstance(row, dict)`` gate rewrote every psycopg2 row
into ``PostgresRowMapping`` and changed iteration, ``len()`` and slicing.
This suite uses the real ``psycopg2.extras.DictCursor`` and real
``psycopg2.extras.DictRow`` objects (no hand-written stand-in) to pin:

  * psycopg2 rows pass through untouched, with their original sequence
    behaviour (iteration yields values, slicing works, ``len`` counts values);
  * pg8000 tuple rows are normalised into PostgresRowMapping, which supports
    ``row[0]``, ``row["col"]``, ``dict(row)`` and NULLs;
  * both drivers expose the same mapping contract for the same SQL.

Requires KANDID_TEST_POSTGRES_URL pointing at a loopback database whose name
ends in ``_test``. The integration class skips without it and fails loudly when
a driver is missing (same convention as test_pg8000_row_shape.py).

Run:
  KANDID_TEST_POSTGRES_URL=postgresql://user@127.0.0.1:5432/kindid_pg8000_test \
      python3 test_real_dictrow_row_contract.py -v
"""

import os
import unittest
import urllib.parse

os.environ.pop("DATABASE_URL", None)

import server  # noqa: E402

PG_URL = os.environ.get("KANDID_TEST_POSTGRES_URL", "").strip()
PG_SKIP_REASON = "KANDID_TEST_POSTGRES_URL is not set; real PostgreSQL is required"

PLAIN_SQL = "SELECT 1 AS a, 'x' AS b, NULL::int AS c"
DUP_SQL = "SELECT 1 AS a, 'x' AS b, NULL::int AS c, 1 AS dup, 2 AS dup"
MULTI_SQL = "SELECT * FROM (VALUES (1, 'a'), (2, 'b'), (3, NULL)) AS t(id, label)"


class RealDictRowContract(unittest.TestCase):
    """Both drivers against a real cluster, through the server's own wrappers."""

    @classmethod
    def setUpClass(cls):
        if not PG_URL:
            raise unittest.SkipTest(PG_SKIP_REASON)
        parsed = urllib.parse.urlsplit(PG_URL)
        host = (parsed.hostname or "").strip().lower()
        dbname = (parsed.path or "").lstrip("/")
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise AssertionError(
                "refusing to run: KANDID_TEST_POSTGRES_URL must point at a "
                "loopback/disposable host (got %r)" % host
            )
        if not dbname.endswith("_test"):
            raise AssertionError(
                "refusing to run: database name must end with '_test' (got %r)" % dbname
            )
        try:
            import psycopg2
            import psycopg2.extras  # noqa: F401
        except ImportError as exc:
            raise AssertionError(
                "psycopg2 is required for the DictRow regression: %s" % exc
            )
        try:
            import pg8000.dbapi  # noqa: F401
        except ImportError as exc:
            raise AssertionError("pg8000 is required for the tuple-row checks: %s" % exc)
        import pg8000
        import psycopg2

        print(
            "\n[PG] host=%s db=%s psycopg2=%s pg8000=%s"
            % (host, dbname, psycopg2.__version__, pg8000.__version__)
        )

    # -- helpers ---------------------------------------------------------
    def _psycopg2_conn(self):
        import psycopg2

        return psycopg2.connect(PG_URL)

    def _pg8000_conn(self):
        import pg8000.dbapi

        return pg8000.dbapi.connect(**server._get_pg8000_connect_kwargs(PG_URL))

    def _cursor(self, driver):
        raw = self._psycopg2_conn() if driver == "psycopg2" else self._pg8000_conn()
        return raw, server.PostgresConnectionWrapper(raw).cursor()

    def _fetch_one(self, driver, sql):
        raw, cursor = self._cursor(driver)
        try:
            cursor.execute(sql)
            return cursor.fetchone()
        finally:
            raw.close()

    def _fetch_all(self, driver, sql):
        raw, cursor = self._cursor(driver)
        try:
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            raw.close()

    def _iterate(self, driver, sql):
        raw, cursor = self._cursor(driver)
        try:
            cursor.execute(sql)
            return list(cursor)
        finally:
            raw.close()

    # -- psycopg2: genuine DictRow must survive untouched ----------------
    def test_01_psycopg2_row_is_a_real_dictrow_passthrough(self):
        import psycopg2.extras

        row = self._fetch_one("psycopg2", PLAIN_SQL)
        self.assertIsInstance(row, psycopg2.extras.DictRow)
        self.assertNotIsInstance(row, server.PostgresRowMapping)
        self.assertNotIsInstance(row, dict)
        self.assertIsInstance(row, list)

    def test_02_psycopg2_mapping_and_positional_access(self):
        row = self._fetch_one("psycopg2", PLAIN_SQL)
        self.assertEqual(row[0], 1)
        self.assertEqual(row["a"], 1)
        self.assertEqual(row[1], "x")
        self.assertEqual(row["b"], "x")
        self.assertIsNone(row[2])
        self.assertIsNone(row["c"])
        self.assertEqual(dict(row), {"a": 1, "b": "x", "c": None})

    def test_03_psycopg2_sequence_behaviour_is_preserved(self):
        row = self._fetch_one("psycopg2", PLAIN_SQL)
        self.assertEqual(list(iter(row)), [1, "x", None])
        self.assertEqual(len(row), 3)
        self.assertEqual(row[0:2], [1, "x"])
        self.assertEqual(list(row), [1, "x", None])
        self.assertEqual(row, [1, "x", None])

    def test_04_psycopg2_duplicate_columns(self):
        row = self._fetch_one("psycopg2", DUP_SQL)
        self.assertEqual(row["dup"], 2)
        self.assertEqual(dict(row)["dup"], 2)
        self.assertEqual(row[3], 1)
        self.assertEqual(row[4], 2)
        self.assertEqual(len(row), 5)
        self.assertEqual(row[0:2], [1, "x"])

    def test_05_psycopg2_fetchone_fetchall_iteration(self):
        one = self._fetch_all("psycopg2", MULTI_SQL)
        self.assertEqual([dict(r) for r in one], [
            {"id": 1, "label": "a"},
            {"id": 2, "label": "b"},
            {"id": 3, "label": None},
        ])
        iterated = self._iterate("psycopg2", MULTI_SQL)
        self.assertEqual([dict(r) for r in iterated], [dict(r) for r in one])
        self.assertEqual([r[0] for r in iterated], [1, 2, 3])
        self.assertEqual([list(r) for r in iterated], [[1, "a"], [2, "b"], [3, None]])
        self.assertIsNone(self._fetch_one("psycopg2", MULTI_SQL + " WHERE id = 99"))

    # -- pg8000: tuple rows become the compatibility mapping -------------
    def test_06_pg8000_tuple_rows_become_the_compat_mapping(self):
        row = self._fetch_one("pg8000", PLAIN_SQL)
        self.assertIsInstance(row, server.PostgresRowMapping)
        self.assertIsInstance(row, dict)
        self.assertEqual(row[0], 1)
        self.assertEqual(row["a"], 1)
        self.assertEqual(row[1], "x")
        self.assertEqual(row["b"], "x")
        self.assertIsNone(row[2])
        self.assertIsNone(row["c"])
        self.assertEqual(dict(row), {"a": 1, "b": "x", "c": None})

    def test_07_pg8000_fetchone_fetchall_iteration_agree(self):
        fetched = self._fetch_all("pg8000", MULTI_SQL)
        iterated = self._iterate("pg8000", MULTI_SQL)
        expected = [
            {"id": 1, "label": "a"},
            {"id": 2, "label": "b"},
            {"id": 3, "label": None},
        ]
        self.assertEqual([dict(r) for r in fetched], expected)
        self.assertEqual([dict(r) for r in iterated], expected)
        self.assertEqual([r[0] for r in fetched], [1, 2, 3])
        self.assertEqual([r["label"] for r in iterated], ["a", "b", None])
        self.assertIsNone(self._fetch_one("pg8000", MULTI_SQL + " WHERE id = 99"))

    def test_08_pg8000_duplicate_columns_match_dictcursor_mapping(self):
        row = self._fetch_one("pg8000", DUP_SQL)
        self.assertEqual(row["dup"], 2)
        self.assertEqual(dict(row)["dup"], 2)
        self.assertEqual(row[3], 1)
        self.assertEqual(row[4], 2)
        # Mapping stays DictCursor-compatible; positional width is the one
        # documented difference (a mapping cannot hold both duplicate columns).
        self.assertEqual(len(row), 4)

    def test_09_pg8000_empty_result_set(self):
        empty_sql = MULTI_SQL + " WHERE id = 99"
        raw, cursor = self._cursor("pg8000")
        try:
            cursor.execute(empty_sql)
            self.assertIsNone(cursor.fetchone())
            self.assertEqual(cursor.fetchall(), [])
        finally:
            raw.close()

    # -- cross-driver contract -------------------------------------------
    def test_10_both_drivers_expose_the_same_mapping_contract(self):
        for sql in (PLAIN_SQL, DUP_SQL):
            self.assertEqual(
                dict(self._fetch_one("psycopg2", sql)),
                dict(self._fetch_one("pg8000", sql)),
                "mapping mismatch for %r" % sql,
            )
            self.assertEqual(
                [dict(r) for r in self._fetch_all("psycopg2", MULTI_SQL)],
                [dict(r) for r in self._fetch_all("pg8000", MULTI_SQL)],
            )
            self.assertEqual(
                [r[0] for r in self._fetch_all("psycopg2", sql)],
                [r[0] for r in self._fetch_all("pg8000", sql)],
            )

    # -- R2 against a genuine DictRow -------------------------------------
    def test_11_real_dictrow_with_mismatched_description_is_rejected(self):
        """A real DictRow is never reinterpreted when its description is wrong.

        The first-column probe runs on the actual psycopg2 row object, not on a
        stand-in: its keys are ``a``/``b``/``c``, so describing it as
        ``zzz``/``b``/``c`` must raise rather than quietly turn the row's keys
        into positional values.
        """
        import psycopg2.extras

        row = self._fetch_one("psycopg2", PLAIN_SQL)
        self.assertIsInstance(row, psycopg2.extras.DictRow)

        class _DescribedCursor(object):
            description = [("zzz",), ("b",), ("c",)]

            def __init__(self, value):
                self._rows = [value]

            def fetchone(self):
                return self._rows.pop(0)

        cursor = server.PostgresCursorWrapper(_DescribedCursor(row))
        with self.assertRaises(server.PostgresRowShapeError) as ctx:
            cursor.fetchone()
        self.assertIn("zzz", str(ctx.exception))
        self.assertIn("DictRow", str(ctx.exception))
        # The genuine row is untouched: keys, values and identity intact.
        self.assertEqual(list(row.keys()), ["a", "b", "c"])
        self.assertEqual(list(row), [1, "x", None])


if __name__ == "__main__":
    unittest.main(verbosity=2)
