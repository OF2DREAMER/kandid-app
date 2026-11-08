#!/usr/bin/env python3
"""P0-3 regression tests for SESSION_SECRET environment policy.

Each test runs the real server.py in an isolated temporary directory. No
external services, production databases, or repository data files are used.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_SOURCE = Path(__file__).resolve().with_name("server.py")
STRONG_SECRET = "9f8e7d6c5b4a3928170e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"
WEAK_SECRET = "kandid_super_secure_session_secret_2026"
DEV_FALLBACK = "kandid_dev_only_session_key_do_not_use_in_prod"

_ENV_KEYS_TO_CLEAR = (
    "RENDER",
    "RENDER_SERVICE_ID",
    "ENVIRONMENT",
    "SESSION_SECRET",
    "DATABASE_URL",
    "CLOUDINARY_URL",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
    "BREVO_API_KEY",
    "RESEND_API_KEY",
    "PYTHONPATH",
)


class EnvironmentSecretMatrixTests(unittest.TestCase):
    maxDiff = None

    def _env(self, **values):
        env = os.environ.copy()
        for key in _ENV_KEYS_TO_CLEAR:
            env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(values)
        return env

    def _copy_server(self, directory):
        destination = os.path.join(directory, "server.py")
        shutil.copy2(SERVER_SOURCE, destination)
        return destination

    def _free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _run_import(self, env, body):
        """Import the copied server.py and run assertions inside its process."""
        with tempfile.TemporaryDirectory(prefix="kandid_p03_import_") as tmpdir:
            self._copy_server(tmpdir)
            script = "import server\n" + body
            return subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )

    def _run_invalid_startup(self, **values):
        """Run __main__ and require rejection before DB creation or binding."""
        with tempfile.TemporaryDirectory(prefix="kandid_p03_startup_") as tmpdir:
            self._copy_server(tmpdir)
            port = self._free_port()
            env = self._env(PORT=str(port), **values)
            process = subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=tmpdir,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                output, _ = process.communicate(timeout=5)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
                timed_out = True

            db_files = []
            for root, _dirs, files in os.walk(tmpdir):
                for filename in files:
                    if filename.endswith(".db"):
                        db_files.append(os.path.join(root, filename))

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
                check.settimeout(0.2)
                listener_was_opened = check.connect_ex(("127.0.0.1", port)) == 0

            if timed_out:
                self.fail(
                    "server did not fail before binding; it was still running.\n"
                    + (output or "")
                )

            self.assertNotEqual(process.returncode, 0, output)
            self.assertIn("CRITICAL", output or "")
            self.assertIn("SESSION_SECRET", output or "")
            self.assertEqual(db_files, [], f"database created before validation: {db_files}")
            self.assertFalse(listener_was_opened, f"port {port} was bound before validation")
            return output

    def _assert_strong_module_accepted(self, environment, render_key=None):
        env = self._env(
            ENVIRONMENT=environment,
            SESSION_SECRET=STRONG_SECRET,
            PORT=str(self._free_port()),
        )
        if render_key:
            env[render_key] = "true"
        result = self._run_import(
            env,
            "assert server.is_session_secret_required()\n"
            "assert server.SESSION_SECRET == %r\n"
            "server.validate_environment()\n" % STRONG_SECRET,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _assert_required_reset_hash_fails_closed(self, **values):
        env = self._env(DATABASE_URL="", **values)
        result = self._run_import(
            env,
            "assert server.is_session_secret_required()\n"
            "token = 'prt_test_token_1234567890'\n"
            "try:\n"
            "    server.hash_reset_token(token)\n"
            "except RuntimeError as exc:\n"
            "    assert 'SESSION_SECRET' in str(exc), str(exc)\n"
            "else:\n"
            "    raise AssertionError('reset-token fallback was used')\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_render_development_reset_token_hashing_fails_closed_without_startup(self):
        self._assert_required_reset_hash_fails_closed(
            RENDER="true",
            ENVIRONMENT="development",
        )

    def test_render_staging_reset_token_hashing_fails_closed_without_startup(self):
        self._assert_required_reset_hash_fails_closed(
            RENDER_SERVICE_ID="srv-test",
            ENVIRONMENT="staging",
        )

    def test_non_render_staging_reset_token_hashing_fails_closed_without_startup(self):
        self._assert_required_reset_hash_fails_closed(
            ENVIRONMENT="staging",
        )

    def test_empty_render_does_not_hide_render_service_id_for_reset_tokens(self):
        self._assert_required_reset_hash_fails_closed(
            RENDER="",
            RENDER_SERVICE_ID="srv-test",
            ENVIRONMENT="development",
        )

    def test_render_development_reset_token_hashing_rejects_weak_secret_without_startup(self):
        self._assert_required_reset_hash_fails_closed(
            RENDER="true",
            ENVIRONMENT="development",
            SESSION_SECRET=WEAK_SECRET,
        )

    def test_render_development_reset_token_hashing_accepts_strong_secret_without_startup(self):
        env = self._env(
            RENDER="true",
            ENVIRONMENT="development",
            SESSION_SECRET=STRONG_SECRET,
            DATABASE_URL="",
        )
        result = self._run_import(
            env,
            f"assert server.is_session_secret_required()\n"
            f"assert server.SESSION_SECRET == {STRONG_SECRET!r}\n"
            "token = 'prt_test_token_1234567890'\n"
            "verifier = server.hash_reset_token(token)\n"
            "assert verifier.startswith('v1$hmac_sha256$')\n"
            "assert server.verify_reset_token_hash(token, verifier) is True\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_required_secret_rejects_legacy_plaintext_reset_verifiers(self):
        configurations = (
            ("render-development", {"RENDER": "true", "ENVIRONMENT": "development"}),
            ("render-staging", {"RENDER_SERVICE_ID": "srv-test", "ENVIRONMENT": "staging"}),
            ("non-render-staging", {"ENVIRONMENT": "staging"}),
        )
        for label, values in configurations:
            with self.subTest(configuration=label):
                env = self._env(DATABASE_URL="", **values)
                result = self._run_import(
                    env,
                    "assert server.is_session_secret_required()\n"
                    "token = 'prt_legacy_token_1234567890'\n"
                    "assert server.verify_reset_token_hash(token, token) is False\n",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_required_secret_hmac_verification_does_not_use_dev_fallback(self):
        env = self._env(
            RENDER="true",
            ENVIRONMENT="development",
            DATABASE_URL="",
        )
        result = self._run_import(
            env,
            "assert server.is_session_secret_required()\n"
            "token = 'prt_hmac_token_1234567890'\n"
            "stored = 'v1$hmac_sha256$' + '0' * 64\n"
            "try:\n"
            "    server.verify_reset_token_hash(token, stored)\n"
            "except RuntimeError as exc:\n"
            "    assert 'SESSION_SECRET' in str(exc), str(exc)\n"
            "else:\n"
            "    raise AssertionError('HMAC verification used the development fallback')\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_development_reset_token_fallback_is_preserved(self):
        env = self._env(
            ENVIRONMENT="development",
            DATABASE_URL="",
        )
        result = self._run_import(
            env,
            "import hashlib, hmac\n"
            "assert not server.is_session_secret_required()\n"
            "token = 'prt_local_token_1234567890'\n"
            "expected = 'v1$hmac_sha256$' + hmac.new(\n"
            "    server.DEV_SESSION_SECRET_FALLBACK.encode('utf-8'),\n"
            "    token.encode('utf-8'), hashlib.sha256\n"
            ").hexdigest()\n"
            "actual = server.hash_reset_token(token)\n"
            "assert actual == expected\n"
            "assert server.verify_reset_token_hash(token, actual) is True\n"
            "assert server.verify_reset_token_hash(token, token) is True\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_render_development_missing_secret_fails_startup(self):
        self._run_invalid_startup(
            RENDER="true",
            ENVIRONMENT="development",
            DATABASE_URL="",
        )

    def test_render_development_rejects_weak_secret(self):
        self._run_invalid_startup(
            RENDER="true",
            ENVIRONMENT="development",
            SESSION_SECRET=WEAK_SECRET,
            DATABASE_URL="",
        )

    def test_render_staging_missing_secret_fails_startup(self):
        self._run_invalid_startup(
            RENDER_SERVICE_ID="srv-test",
            ENVIRONMENT="staging",
            DATABASE_URL="",
        )

    def test_render_overrides_all_local_environment_names(self):
        for environment in ("development", "dev", "test", "local"):
            with self.subTest(environment=environment):
                self._run_invalid_startup(
                    RENDER="true",
                    ENVIRONMENT=environment,
                    DATABASE_URL="",
                )

    def test_non_render_staging_missing_secret_fails_startup(self):
        self._run_invalid_startup(
            ENVIRONMENT="staging",
            DATABASE_URL="",
        )

    def test_unknown_non_render_environment_fails_closed(self):
        self._run_invalid_startup(
            ENVIRONMENT="qa",
            DATABASE_URL="",
        )

    def test_required_environments_reject_missing_and_weak_secrets(self):
        for environment in ("staging", "production", "prod"):
            for secret in ("", "short", WEAK_SECRET):
                with self.subTest(environment=environment, secret=secret):
                    self._run_invalid_startup(
                        ENVIRONMENT=environment,
                        SESSION_SECRET=secret,
                        DATABASE_URL="",
                    )

    def test_staging_and_production_accept_strong_explicit_secret(self):
        for environment in ("staging", "production", "prod"):
            with self.subTest(environment=environment):
                self._assert_strong_module_accepted(environment)

    def test_render_development_accepts_strong_explicit_secret(self):
        self._assert_strong_module_accepted("development", render_key="RENDER")

    def test_permitted_local_development_uses_the_real_fallback(self):
        for environment in ("development", "dev", "test", "testing", "local"):
            with self.subTest(environment=environment):
                env = self._env(
                    ENVIRONMENT=environment,
                    PORT=str(self._free_port()),
                )
                result = self._run_import(
                    env,
                    "assert not server.is_session_secret_required()\n"
                    "assert server.SESSION_SECRET == %r\n"
                    "server.validate_environment()\n" % DEV_FALLBACK,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_render_change_after_import_fails_closed(self):
        env = self._env(
            ENVIRONMENT="development",
            DATABASE_URL="",
        )
        result = self._run_import(
            env,
            "import os\n"
            "assert not server.is_session_secret_required()\n"
            "os.environ['RENDER'] = 'true'\n"
            "assert server.is_session_secret_required()\n"
            "try:\n"
            "    server.hash_reset_token('prt_runtime_token_1234567890')\n"
            "except RuntimeError as exc:\n"
            "    assert 'SESSION_SECRET' in str(exc), str(exc)\n"
            "else:\n"
            "    raise AssertionError('runtime Render change used the development fallback')\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reset_password_route_rejects_plaintext_token_in_required_secret_env(self):
        env = self._env(
            RENDER="true",
            ENVIRONMENT="development",
            SESSION_SECRET=STRONG_SECRET,
            DATABASE_URL="",
        )
        result = self._run_import(
            env,
            "import io, json, os, sqlite3\n"
            "db_path = os.path.join(os.getcwd(), 'route_test.db')\n"
            "server.DB_FILE = db_path\n"
            "server.DATABASE_URL = ''\n"
            "conn = sqlite3.connect(db_path)\n"
            "conn.execute('CREATE TABLE password_resets (id TEXT PRIMARY KEY, email TEXT NOT NULL, token TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')\n"
            "expires = (server.datetime.now() + server.timedelta(minutes=10)).isoformat()\n"
            "token = 'prt_legacy_route_token_1234567890'\n"
            "conn.execute('INSERT INTO password_resets (id, email, token, expires_at) VALUES (?, ?, ?, ?)', ('pr_plain_route', 'alice@example.com', token, expires))\n"
            "conn.commit(); conn.close()\n"
            "class DummyHandler(server.KandidHandler):\n"
            "    def __init__(self):\n"
            "        body = json.dumps({'reset_token': token, 'new_password': 'BrandNewPassword123!'}).encode('utf-8')\n"
            "        self.path = '/api/auth/reset-password'\n"
            "        self.headers = {'Content-Length': str(len(body)), 'Content-Type': 'application/json'}\n"
            "        self.rfile = io.BytesIO(body)\n"
            "        self.sent_response = {}\n"
            "        self.client_address = ('127.0.0.1', 12345)\n"
            "    def send_json(self, status_code, response_dict):\n"
            "        self.sent_response = {'status': status_code, 'body': response_dict}\n"
            "        return response_dict\n"
            "handler = DummyHandler()\n"
            "handler.do_POST()\n"
            "assert handler.sent_response['status'] == 400, handler.sent_response\n"
            "assert handler.sent_response['body']['error_code'] == 'INVALID_RESET_TOKEN', handler.sent_response\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_startup_logs_hide_secret_and_database_credentials(self):
        fake_dsn = "postgresql://audit_user:not-a-real-password@db.example.invalid/kindid"
        env = self._env(
            ENVIRONMENT="production",
            SESSION_SECRET=STRONG_SECRET,
            DATABASE_URL=fake_dsn,
            PORT=str(self._free_port()),
        )
        result = self._run_import(env, "server.validate_environment()\n")
        rendered = (result.stdout or "") + (result.stderr or "")
        self.assertEqual(result.returncode, 0, rendered)

        self.assertNotIn(STRONG_SECRET, rendered)
        self.assertNotIn(STRONG_SECRET[:20], rendered)
        self.assertNotIn(fake_dsn, rendered)
        self.assertNotIn("audit_user", rendered)
        self.assertNotIn("not-a-real-password", rendered)
        self.assertNotIn("postgresql://", rendered)
        self.assertIn("PostgreSQL configured.", rendered)


if __name__ == "__main__":
    unittest.main()
