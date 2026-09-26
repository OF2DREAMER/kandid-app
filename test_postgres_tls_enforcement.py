#!/usr/bin/env python3
"""
Unit test suite for PostgreSQL TLS enforcement (D4-08).
Validates that all remote PostgreSQL connections fail closed to TLS,
local exemptions work as intended, percent-encoding and parameters are preserved,
and server.py get_db() / migrate_sqlite_to_postgres.py control flows fail closed.
"""

import os
import sys
import unittest
import urllib.parse
import ssl
from unittest.mock import patch, MagicMock

import server
import migrate_sqlite_to_postgres as mig


class TestEnsureSecureSslmodeRemoteUrl(unittest.TestCase):
    """Test URL normalization for remote endpoints."""

    def test_remote_absent_sslmode_adds_require(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb"
        out = server._ensure_secure_sslmode(dsn)
        p = urllib.parse.urlsplit(out)
        qs = urllib.parse.parse_qs(p.query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])
        self.assertEqual(p.hostname, "ep-cool-lake-123456.us-east-2.aws.neon.tech")

    def test_remote_disable_overridden_to_require(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=disable"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_remote_allow_overridden_to_require(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=allow"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_remote_prefer_overridden_to_require(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=prefer"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_remote_require_preserved(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_remote_verify_ca_preserved(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=verify-ca"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["verify-ca"])

    def test_remote_verify_full_preserved(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=verify-full"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["verify-full"])

    def test_duplicate_sslmode_verify_full_and_disable(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=verify-full&sslmode=disable"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["verify-full"])

    def test_duplicate_sslmode_disable_and_prefer(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=disable&sslmode=prefer"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_duplicate_sslmode_verify_ca_and_require(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=verify-ca&sslmode=require"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["verify-ca"])

    def test_invalid_sslmode_raises_value_error(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=super-secure"
        with self.assertRaises(ValueError):
            server._ensure_secure_sslmode(dsn)

    def test_non_postgres_scheme_raises_value_error(self):
        for bad_dsn in [
            "mysql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb",
            "http://ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb",
            "sqlite:///data/kandid.db",
        ]:
            with self.subTest(dsn=bad_dsn):
                with self.assertRaises(ValueError):
                    server._ensure_secure_sslmode(bad_dsn)

    def test_empty_or_whitespace_dsn_raises_value_error(self):
        for empty_val in ["", "   ", None]:
            with self.subTest(val=empty_val):
                with self.assertRaises(ValueError):
                    server._ensure_secure_sslmode(empty_val)

    def test_channel_binding_and_extra_query_params_preserved(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require&application_name=kandid_api&connect_timeout=10"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])
        self.assertEqual(qs.get("channel_binding"), ["require"])
        self.assertEqual(qs.get("application_name"), ["kandid_api"])
        self.assertEqual(qs.get("connect_timeout"), ["10"])

    def test_percent_encoded_credentials_preserved_in_url(self):
        dsn = "postgresql://user%40example.com:p%40ss%2Fword%231@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
        out = server._ensure_secure_sslmode(dsn)
        p = urllib.parse.urlsplit(out)
        self.assertIn("user%40example.com:p%40ss%2Fword%231@", p.netloc)
        self.assertEqual(p.hostname, "ep-cool-lake-123456.us-east-2.aws.neon.tech")

    def test_neon_pooler_host_recognized_and_enforced(self):
        dsn = "postgresql://user:pass@ep-cool-lake-123456-pooler.us-east-2.aws.neon.tech:5432/neondb"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])
        self.assertIn("-pooler.", out)

    def test_postgres_scheme_alias_supported(self):
        dsn = "postgres://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])

    def test_uri_query_host_remote_enforces_require(self):
        dsn = "postgresql:///neondb?host=ep-cool.neon.tech"
        out = server._ensure_secure_sslmode(dsn)
        self.assertTrue(out.startswith("postgresql:///"), f"Expected triple-slash prefix in {out}")
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])
        self.assertEqual(qs.get("host"), ["ep-cool.neon.tech"])

    def test_uri_query_host_localhost_remote_hostaddr_enforces_require(self):
        dsn = "postgresql:///neondb?host=localhost&hostaddr=203.0.113.10"
        out = server._ensure_secure_sslmode(dsn)
        self.assertTrue(out.startswith("postgresql:///"), f"Expected triple-slash prefix in {out}")
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["require"])


class TestEnsureSecureSslmodeLocal(unittest.TestCase):
    """Test local endpoint exemption and handling."""

    def test_localhost_unmodified_when_no_sslmode(self):
        dsn = "postgresql://user:pass@localhost:5432/kandid_dev"
        out = server._ensure_secure_sslmode(dsn)
        self.assertEqual(out, dsn)

    def test_localhost_preserves_explicit_sslmode(self):
        dsn = "postgresql://user:pass@localhost:5432/kandid_dev?sslmode=disable"
        out = server._ensure_secure_sslmode(dsn)
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertEqual(qs.get("sslmode"), ["disable"])

    def test_127_0_0_1_unmodified_when_no_sslmode(self):
        dsn = "postgresql://user:pass@127.0.0.1:5432/kandid_dev"
        out = server._ensure_secure_sslmode(dsn)
        self.assertEqual(out, dsn)

    def test_127_loopback_range_recognized_as_local(self):
        for ip in ["127.0.0.2", "127.1.2.3"]:
            with self.subTest(ip=ip):
                dsn = f"postgresql://user:pass@{ip}:5432/kandid_dev"
                out = server._ensure_secure_sslmode(dsn)
                self.assertEqual(out, dsn)

    def test_ipv6_loopback_recognized_as_local(self):
        dsn = "postgresql://user:pass@[::1]:5432/kandid_dev"
        out = server._ensure_secure_sslmode(dsn)
        self.assertEqual(out, dsn)

    def test_unix_socket_recognized_as_local(self):
        self.assertTrue(server._is_local_host("/var/run/postgresql"))
        self.assertTrue(server._is_local_host("./socket"))
        self.assertTrue(server._is_local_host(None))
        self.assertTrue(server._is_local_host(""))

    def test_uri_query_host_unix_socket_preserved(self):
        dsn = "postgresql:///neondb?host=/tmp/postgresql"
        out = server._ensure_secure_sslmode(dsn)
        self.assertTrue(out.startswith("postgresql:///"), f"Expected triple-slash prefix in {out}")
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertNotIn("sslmode", qs)

    def test_uri_query_host_localhost_preserved(self):
        dsn = "postgresql:///neondb?host=localhost"
        out = server._ensure_secure_sslmode(dsn)
        self.assertTrue(out.startswith("postgresql:///"), f"Expected triple-slash prefix in {out}")
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(out).query, keep_blank_values=True)
        self.assertNotIn("sslmode", qs)


class TestEnsureSecureSslmodeConninfo(unittest.TestCase):
    """Test conninfo key-value string normalization."""

    def test_service_only_fails_closed(self):
        dsn = "service=kandid_neon"
        with self.assertRaises(ValueError) as ctx:
            server._ensure_secure_sslmode(dsn)
        self.assertIn("service-only", str(ctx.exception).lower())

    def test_malformed_unbalanced_quotes_fails_closed(self):
        dsn = "host='ep-cool.neon.tech dbname=test"
        with self.assertRaises(ValueError):
            server._ensure_secure_sslmode(dsn)

    def test_malformed_token_missing_equals_fails_closed(self):
        dsn = "host=ep-cool.neon.tech invalid_token dbname=test"
        with self.assertRaises(ValueError):
            server._ensure_secure_sslmode(dsn)

    def test_explicit_remote_host_with_service_enforces_tls(self):
        dsn = "host=ep-cool-lake-123456.us-east-2.aws.neon.tech service=kandid_neon"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)
        self.assertIn("service=kandid_neon", out)

    def test_explicit_remote_host_disable_overridden_to_require(self):
        dsn = "host=ep-cool.neon.tech dbname=neondb sslmode=disable"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)
        self.assertNotIn("sslmode=disable", out)

    def test_explicit_remote_host_verify_full_preserved(self):
        dsn = "host=ep-cool.neon.tech dbname=neondb sslmode=verify-full"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=verify-full", out)

    def test_explicit_local_host_conninfo_preserved(self):
        dsn = "host=localhost dbname=kandid_dev"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("host=localhost", out)
        self.assertIn("dbname=kandid_dev", out)
        self.assertNotIn("sslmode=require", out)

    def test_explicit_local_127_conninfo_preserved(self):
        dsn = "host=127.0.0.1 dbname=kandid_dev"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("host=127.0.0.1", out)
        self.assertNotIn("sslmode=require", out)

    def test_conninfo_with_spaces_in_values_quoted_properly(self):
        dsn = "host=ep-cool.neon.tech dbname='my kandid db'"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)
        self.assertIn("dbname='my kandid db'", out)

    def test_conninfo_host_localhost_remote_hostaddr_enforces_tls(self):
        dsn = "host=localhost hostaddr=203.0.113.10 dbname=kandid"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)

    def test_conninfo_host_localhost_local_hostaddr_preserved(self):
        dsn = "host=localhost hostaddr=127.0.0.1 dbname=kandid"
        out = server._ensure_secure_sslmode(dsn)
        self.assertNotIn("sslmode=require", out)

    def test_conninfo_host_remote_remote_hostaddr_enforces_tls(self):
        dsn = "host=ep-cool.neon.tech hostaddr=203.0.113.10 dbname=kandid"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)

    def test_conninfo_remote_hostaddr_without_host_enforces_tls(self):
        dsn = "hostaddr=203.0.113.10 dbname=kandid"
        out = server._ensure_secure_sslmode(dsn)
        self.assertIn("sslmode=require", out)


class TestPg8000ConnectKwargs(unittest.TestCase):
    """Test keyword argument preparation for pg8000 driver."""

    def test_remote_url_creates_ssl_context(self):
        dsn = "postgresql://user:p%40ss%2Fword@ep-cool.neon.tech:5432/neondb?sslmode=require"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertIsNotNone(kwargs["ssl_context"])
        self.assertEqual(kwargs["user"], "user")
        self.assertEqual(kwargs["password"], "p@ss/word")
        self.assertEqual(kwargs["host"], "ep-cool.neon.tech")
        self.assertEqual(kwargs["port"], 5432)
        self.assertEqual(kwargs["database"], "neondb")

    def test_local_url_has_no_ssl_context(self):
        dsn = "postgresql://user:pass@localhost:5432/kandid_dev"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertIsNone(kwargs["ssl_context"])

    def test_verify_full_configures_hostname_verification(self):
        dsn = "postgresql://user:pass@ep-cool.neon.tech:5432/neondb?sslmode=verify-full"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        ctx = kwargs["ssl_context"]
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_conninfo_parsed_correctly(self):
        dsn = "host=ep-cool.neon.tech user=app password=secret dbname=prod sslmode=require"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["host"], "ep-cool.neon.tech")
        self.assertEqual(kwargs["user"], "app")
        self.assertEqual(kwargs["password"], "secret")
        self.assertEqual(kwargs["database"], "prod")
        self.assertIsNotNone(kwargs["ssl_context"])

    def test_application_name_mapped_from_url(self):
        dsn = "postgresql://user:p%40ss%2Fword@ep-cool.neon.tech/neondb?sslmode=require&application_name=kindid"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["application_name"], "kindid")
        self.assertEqual(kwargs["password"], "p@ss/word")

    def test_application_name_mapped_from_conninfo(self):
        dsn = "host=ep-cool.neon.tech dbname=neondb user=app application_name=kandid_backend"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["application_name"], "kandid_backend")

    def test_unix_socket_mapped_to_unix_sock_and_host_none_conninfo(self):
        dsn = "host=/tmp/postgresql dbname=kandid_dev user=app"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["unix_sock"], "/tmp/postgresql")
        self.assertIsNone(kwargs["host"])
        self.assertIsNone(kwargs["port"])
        self.assertIsNone(kwargs["ssl_context"])

    def test_unix_socket_custom_dir_mapped_correctly(self):
        dsn = "host=/var/run/postgresql/.s.PGSQL.5432 dbname=kandid_dev"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["unix_sock"], "/var/run/postgresql/.s.PGSQL.5432")
        self.assertIsNone(kwargs["host"])
        self.assertIsNone(kwargs["port"])
        self.assertIsNone(kwargs["ssl_context"])

    def test_unix_socket_url_mapped_to_unix_sock(self):
        dsn = "postgresql://user:pass@/kandid_dev?host=/tmp/postgresql"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["unix_sock"], "/tmp/postgresql")
        self.assertIsNone(kwargs["host"])
        self.assertIsNone(kwargs["port"])
        self.assertIsNone(kwargs["ssl_context"])

    def test_channel_binding_explicitly_excluded_from_pg8000_while_ssl_enforced(self):
        dsn = "postgresql://user:pass@ep-cool.neon.tech/neondb?sslmode=require&channel_binding=require"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        # pg8000.dbapi.connect does not take channel_binding kwarg
        self.assertNotIn("channel_binding", kwargs)
        # TLS security is enforced via ssl_context
        self.assertIsNotNone(kwargs["ssl_context"])
        # But psycopg2/normalized DSN retains channel_binding
        norm_dsn = server._ensure_secure_sslmode(dsn)
        self.assertIn("channel_binding=require", norm_dsn)

    def test_uri_query_host_remote_creates_ssl_context(self):
        dsn = "postgresql:///neondb?host=ep-cool.neon.tech"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["host"], "ep-cool.neon.tech")
        self.assertIsNone(kwargs["unix_sock"])
        self.assertIsNotNone(kwargs["ssl_context"])

    def test_uri_query_host_unix_socket_maps_unix_sock(self):
        dsn = "postgresql:///neondb?host=/tmp/postgresql"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["unix_sock"], "/tmp/postgresql")
        self.assertIsNone(kwargs["host"])
        self.assertIsNone(kwargs["ssl_context"])

    def test_conninfo_remote_hostaddr_maps_host_and_creates_ssl_context(self):
        dsn = "host=localhost hostaddr=203.0.113.10 dbname=kandid user=app"
        kwargs = server._get_pg8000_connect_kwargs(dsn)
        self.assertEqual(kwargs["host"], "203.0.113.10")
        self.assertIsNotNone(kwargs["ssl_context"])


class TestServerGetDbControlFlow(unittest.TestCase):
    """Test critical control flow paths in server.py get_db()."""

    def setUp(self):
        self.orig_db_url = server.DATABASE_URL
        self.orig_env = server.ENVIRONMENT

    def tearDown(self):
        server.DATABASE_URL = self.orig_db_url
        server.ENVIRONMENT = self.orig_env

    def test_normalization_failure_in_development_raises_without_sqlite_fallback(self):
        server.ENVIRONMENT = "development"
        server.DATABASE_URL = "service=ambiguous_neon_service"
        with self.assertRaises(ValueError):
            server.get_db()

    def test_normalization_failure_in_production_raises_without_driver_call(self):
        server.ENVIRONMENT = "production"
        server.DATABASE_URL = "mysql://user:pass@ep-cool.neon.tech/neondb"
        with self.assertRaises(ValueError):
            server.get_db()

    def test_driver_failure_in_development_falls_back_to_sqlite(self):
        server.ENVIRONMENT = "development"
        server.DATABASE_URL = "postgresql://invalid_user:invalid_pass@ep-fake-123456.neon.tech/db"

        with patch("server._ensure_secure_sslmode", wraps=server._ensure_secure_sslmode) as mock_norm:
            # Force psycopg2 to fail to trigger driver error path
            with patch.dict("sys.modules", {"psycopg2": None}):
                with patch("pg8000.dbapi.connect", side_effect=Exception("Connection refused")):
                    conn = server.get_db()
                    # Normalizer was called
                    mock_norm.assert_called_once()
                    # Fell back to SQLite connection
                    import sqlite3
                    self.assertIsInstance(conn, sqlite3.Connection)
                    conn.close()

    def test_driver_failure_in_production_raises_runtime_error(self):
        server.ENVIRONMENT = "production"
        server.DATABASE_URL = "postgresql://user:pass@ep-fake.neon.tech/db"

        with patch.dict("sys.modules", {"psycopg2": None}):
            with patch("pg8000.dbapi.connect", side_effect=Exception("Connection refused")):
                with self.assertRaises(RuntimeError) as ctx:
                    server.get_db()
                self.assertIn("CRITICAL: Failed to connect to production PostgreSQL database", str(ctx.exception))

    def test_empty_database_url_returns_sqlite(self):
        server.DATABASE_URL = ""
        conn = server.get_db()
        import sqlite3
        self.assertIsInstance(conn, sqlite3.Connection)
        conn.close()


class TestMigrateScriptControlFlow(unittest.TestCase):
    """Test control flow in migrate_sqlite_to_postgres.py."""

    def test_migration_normalization_failure_fails_closed(self):
        with self.assertRaises(ValueError):
            mig.migrate_database(target_pg_url="service=only")

    def test_migration_normalizes_remote_url(self):
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.fetchone.return_value = (0,)
        with patch("psycopg2.connect", return_value=mock_conn) as mock_connect:
            mig.migrate_database(
                sqlite_path=mig.DEFAULT_SQLITE_PATH,
                target_pg_url="postgresql://user:pass@ep-cool.neon.tech/db?sslmode=disable",
                dry_run=False,
            )
            # psycopg2.connect should receive normalized URL with sslmode=require
            self.assertTrue(mock_connect.called)
            called_url = mock_connect.call_args[0][0]
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(called_url).query)
            self.assertEqual(qs.get("sslmode"), ["require"])


class TestNormalizedRoundTrip(unittest.TestCase):
    """Round-trip verification of accepted normalized remote DSNs."""

    def test_round_trip_preserves_host_single_sslmode_and_credentials(self):
        cases = [
            "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb",
            "postgresql://user:pass@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
            "postgresql://user:p%40ss%2Fword@ep-cool-lake-123456.us-east-2.aws.neon.tech/neondb?sslmode=require",
        ]

        for dsn in cases:
            with self.subTest(dsn=dsn):
                out = server._ensure_secure_sslmode(dsn)
                p = urllib.parse.urlsplit(out)
                orig_p = urllib.parse.urlsplit(dsn)
                qs = urllib.parse.parse_qs(p.query, keep_blank_values=True)

                self.assertEqual(p.hostname, orig_p.hostname)
                self.assertEqual(qs.get("sslmode"), ["require"])
                # Exactly one sslmode
                raw_qs_items = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
                sslmode_count = sum(1 for k, v in raw_qs_items if k == "sslmode")
                self.assertEqual(sslmode_count, 1)

                if "channel_binding" in orig_p.query:
                    self.assertEqual(qs.get("channel_binding"), ["require"])

                self.assertEqual(p.username, orig_p.username)
                self.assertEqual(p.password, orig_p.password)


if __name__ == "__main__":
    unittest.main()
