#!/usr/bin/env python3
"""
Regression test suite for B2-SEC-03 (CORS Hardening) and B2-SEC-12 (HSTS).

Covers:
1. CORS:
   - Authorized canonical origins receive matching Access-Control-Allow-Origin & Credentials.
   - Unauthorized origins (e.g. evil.com) receive NO Access-Control-Allow-Origin.
   - Suffix-spoof origins (e.g. evilkindid.in, evil-kindid.in) receive NO ACAO.
   - Empty APP_URL="" does not produce wildcard ACAO: *.
   - Missing Origin header does not receive ACAO or credentials.
   - Vary: Origin is present on responses.
   - Authorized OPTIONS/preflight returns 200 with complete CORS headers.
   - Unauthorized OPTIONS/preflight fails closed (NO ACAO / NO credentials).

2. HSTS:
   - Production environment emits Strict-Transport-Security: max-age=31536000.
   - Development/test environment does NOT emit Strict-Transport-Security.
   - Header does not include includeSubDomains or preload.

Runs in-process against an isolated ephemeral database; data/kandid.db is never touched.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server

_ORIGINAL_DB_FILE = server.DB_FILE
_ORIGINAL_DATABASE_URL = server.DATABASE_URL
_ORIGINAL_ENVIRONMENT = server.ENVIRONMENT
_ORIGINAL_APP_URL = server.APP_URL


def _restore_server_globals():
    server.DB_FILE = _ORIGINAL_DB_FILE
    server.DATABASE_URL = _ORIGINAL_DATABASE_URL
    server.ENVIRONMENT = _ORIGINAL_ENVIRONMENT
    server.APP_URL = _ORIGINAL_APP_URL


class TestB2Sec03CorsAndHsts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2b_test_")
        cls.addClassCleanup(shutil.rmtree, cls._tmpdir, ignore_errors=True)
        cls.addClassCleanup(_restore_server_globals)

        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "test.db")
        server.init_db()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            _restore_server_globals()

    def _request(self, path="/health", origin=None, method="GET", extra_headers=None):
        headers = {}
        if origin is not None:
            headers["Origin"] = origin
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, hdrs, resp.read()
        except urllib.error.HTTPError as e:
            hdrs = {k.lower(): v for k, v in e.headers.items()}
            return e.code, hdrs, e.read()

    # =========================================================================
    # SCOPE 1: B2-SEC-03 CORS HARDENING
    # =========================================================================

    def test_01_authorized_canonical_origins_receive_matching_acao(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = "https://kindid.in"

        trusted_origins = [
            "https://kindid.in",
            "https://www.kindid.in",
            "https://kandid-app-1.onrender.com",
            "https://kandid.app",
            "https://kandid.in",
            "https://www.kandid.in",
        ]
        for origin in trusted_origins:
            status, headers, _ = self._request("/health", origin=origin)
            self.assertEqual(status, 200, f"Failed on origin: {origin}")
            self.assertEqual(
                headers.get("access-control-allow-origin"),
                origin,
                f"Expected matching ACAO for {origin}",
            )
            self.assertEqual(
                headers.get("access-control-allow-credentials"),
                "true",
                f"Expected credentials for {origin}",
            )
            self.assertEqual(headers.get("vary"), "Origin")

    def test_02_unauthorized_origins_receive_no_acao(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = "https://kindid.in"

        unauthorized_origins = [
            "https://evil.com",
            "https://attacker.org",
            "http://kindid.in",  # Insecure HTTP scheme
            "https://notkindid.in",
            "null",
        ]
        for origin in unauthorized_origins:
            status, headers, _ = self._request("/health", origin=origin)
            self.assertEqual(status, 200)
            self.assertIsNone(
                headers.get("access-control-allow-origin"),
                f"Unauthorized origin {origin} must NOT receive ACAO header",
            )
            self.assertIsNone(
                headers.get("access-control-allow-credentials"),
                f"Unauthorized origin {origin} must NOT receive ACAC header",
            )
            self.assertEqual(headers.get("vary"), "Origin")

    def test_03_suffix_spoof_origins_receive_no_acao(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = "https://kindid.in"

        spoof_origins = [
            "https://evilkindid.in",
            "https://evil-kindid.in",
            "https://kindid.in.attacker.com",
            "https://evilonrender.com",
            "https://kandid-app-1.onrender.com.evil.com",
        ]
        for origin in spoof_origins:
            status, headers, _ = self._request("/health", origin=origin)
            self.assertEqual(status, 200)
            self.assertIsNone(
                headers.get("access-control-allow-origin"),
                f"Suffix-spoof origin {origin} must NOT receive ACAO header",
            )
            self.assertIsNone(headers.get("access-control-allow-credentials"))
            self.assertEqual(headers.get("vary"), "Origin")

    def test_04_empty_app_url_does_not_produce_wildcard_acao(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = ""

        # Probe with unauthorized origin
        status, headers, _ = self._request("/health", origin="https://evil.com")
        self.assertEqual(status, 200)
        self.assertIsNone(
            headers.get("access-control-allow-origin"),
            "Empty APP_URL must never fall back to wildcard '*' for unauthorized origin",
        )
        self.assertNotEqual(headers.get("access-control-allow-origin"), "*")

        # Canonical origins must still work even when APP_URL is empty
        status, headers, _ = self._request("/health", origin="https://kindid.in")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "https://kindid.in")

    def test_05_missing_origin_does_not_enter_trusted_origin_handling(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = ""

        # Request with NO Origin header
        status, headers, _ = self._request("/health", origin=None)
        self.assertEqual(status, 200)
        self.assertIsNone(
            headers.get("access-control-allow-origin"),
            "Missing Origin header must NOT receive ACAO header",
        )
        self.assertIsNone(headers.get("access-control-allow-credentials"))
        self.assertEqual(headers.get("vary"), "Origin")

    def test_06_vary_origin_is_present(self):
        server.ENVIRONMENT = "production"
        for origin in ["https://kindid.in", "https://evil.com", None]:
            _, headers, _ = self._request("/health", origin=origin)
            self.assertEqual(
                headers.get("vary"),
                "Origin",
                "Vary: Origin must be present for cache consistency",
            )

    def test_07_authorized_preflight_options_functional(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = "https://kindid.in"

        status, headers, _ = self._request(
            "/api/feed",
            origin="https://kindid.in",
            method="OPTIONS",
            extra_headers={"Access-Control-Request-Method": "POST"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "https://kindid.in")
        self.assertEqual(headers.get("access-control-allow-credentials"), "true")
        self.assertEqual(
            headers.get("access-control-allow-headers"),
            "Content-Type, Authorization, X-User-Id",
        )
        self.assertEqual(
            headers.get("access-control-allow-methods"),
            "GET, POST, PUT, DELETE, OPTIONS",
        )
        self.assertEqual(headers.get("vary"), "Origin")

    def test_08_unauthorized_preflight_options_fails_closed(self):
        server.ENVIRONMENT = "production"
        server.APP_URL = "https://kindid.in"

        status, headers, _ = self._request(
            "/api/feed",
            origin="https://evil.com",
            method="OPTIONS",
            extra_headers={"Access-Control-Request-Method": "POST"},
        )
        self.assertEqual(status, 200)
        self.assertIsNone(
            headers.get("access-control-allow-origin"),
            "Unauthorized preflight must NOT receive Access-Control-Allow-Origin",
        )
        self.assertIsNone(headers.get("access-control-allow-credentials"))
        self.assertIsNone(headers.get("access-control-allow-headers"))
        self.assertIsNone(headers.get("access-control-allow-methods"))
        self.assertEqual(headers.get("vary"), "Origin")

    # =========================================================================
    # SCOPE 2: B2-SEC-12 STRICT-TRANSPORT-SECURITY (HSTS)
    # =========================================================================

    def test_09_production_emits_hsts(self):
        server.ENVIRONMENT = "production"
        status, headers, _ = self._request("/health", origin="https://kindid.in")
        self.assertEqual(status, 200)
        hsts = headers.get("strict-transport-security")
        self.assertIsNotNone(hsts, "Production must emit Strict-Transport-Security")
        self.assertEqual(hsts, "max-age=31536000")
        self.assertNotIn("includesubdomains", hsts.lower())
        self.assertNotIn("preload", hsts.lower())

    def test_10_development_does_not_emit_hsts(self):
        server.ENVIRONMENT = "development"
        status, headers, _ = self._request("/health", origin="https://kindid.in")
        self.assertEqual(status, 200)
        self.assertIsNone(
            headers.get("strict-transport-security"),
            "Development environment must NOT emit Strict-Transport-Security",
        )

    def test_11_core_security_headers_remain_active(self):
        server.ENVIRONMENT = "production"
        status, headers, _ = self._request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(
            headers.get("referrer-policy"), "strict-origin-when-cross-origin"
        )
        self.assertEqual(headers.get("x-xss-protection"), "1; mode=block")
        self.assertEqual(
            headers.get("permissions-policy"),
            "camera=(self), microphone=(self), geolocation=(self)",
        )
        self.assertEqual(headers.get("strict-transport-security"), "max-age=31536000")


if __name__ == "__main__":
    unittest.main(verbosity=2)
