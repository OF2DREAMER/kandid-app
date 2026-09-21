#!/usr/bin/env python3
"""
Focused regression test for Day-3 Task 5: CORS origin suffix-matching fix.

BEFORE the fix the production CORS check in `KandidHandler.end_headers()` was:

    if origin in allowed_origins or (origin and any(
        origin.endswith(d) for d in [".kindid.in", "kindid.in", ".onrender.com"])):
        Access-Control-Allow-Origin: <origin>
        Access-Control-Allow-Credentials: true

The suffix arms made the allowlist decorative: `origin.endswith("kindid.in")`
accepts ANY domain that merely *ends* with that string, so an attacker who
registers `evilkindid.in` (or `evil-kindid.in`) gets a credentialed, same-trust
CORS response. `.onrender.com` is equally unsafe because every Render tenant can
serve a host under that suffix.

The fix replaces the condition with exact matching against the trusted origins
that were already listed:

    if origin in allowed_origins:

No wildcard, no new origins, no CORS redesign - one line.

Two layers of proof:
  A. STATIC      - the suffix arms are gone from the CORS path, the trusted
                   origins are still listed, and the rest of server.py is
                   byte-identical to baseline 26f9210 apart from that one line.
  B. BEHAVIOURAL - the REAL server (KandidHandler, ENVIRONMENT=production) is
                   started in-process and probed over HTTP with attacker and
                   legitimate Origin headers, so the actual response headers are
                   inspected.

Runs read-only: the database is redirected to a throwaway copy, so
data/kandid.db is never touched. The probes used (/health, OPTIONS /api/feed)
do not query the database at all.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402

SERVER_PY = os.path.join(PROJECT_DIR, "server.py")

# Commit this task is implemented on: used for the blast-radius comparison and
# to show the pre-fix predicate really did accept the attacker origins.
BASELINE_COMMIT = "26f9210"

CORS_MARKER = "# CORS Origin Control"
CORS_END = 'self.send_header("Access-Control-Allow-Headers"'

FIXED_CONDITION = "            if origin in allowed_origins:"
OLD_CONDITION = (
    '            if origin in allowed_origins or (origin and '
    'any(origin.endswith(d) for d in [".kindid.in", "kindid.in", ".onrender.com"])):'
)
UNSAFE_SUFFIXES = (".kindid.in", "kindid.in", ".onrender.com")

# The trusted origins the code already listed (must stay allowed).
TRUSTED_LITERALS = (
    "https://kindid.in",
    "https://www.kindid.in",
    "https://kandid-app-1.onrender.com",
    "https://kandid.app",
    "https://kandid.in",
    "https://www.kandid.in",
)

# Domains that the old suffix arms accepted but that must now be rejected.
ATTACKER_ORIGINS = (
    "https://evilkindid.in",          # endswith("kindid.in")
    "https://evil-kindid.in",         # endswith("kindid.in")
    "https://kindid.in.attacker.com",  # unrelated + attacker-controlled
    "https://attacker.example",       # completely unrelated
    "https://notkindid.in",           # endswith("kindid.in")
    "http://kindid.in",               # scheme mismatch must not be trusted
)

# Origins the OLD suffix arms also accepted - now deliberately tightened, since
# they are not in the trusted list.
PREVIOUSLY_SUFFIX_MATCHED = (
    "https://staging.kindid.in",      # was allowed by ".kindid.in"
    "https://anything.onrender.com",  # any Render tenant could claim this
)


def read_server_source():
    with open(SERVER_PY, "r", encoding="utf-8") as fh:
        return fh.read()


def baseline_source():
    """Committed pre-fix server.py, or None when git/baseline is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "show", "%s:server.py" % BASELINE_COMMIT],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def cors_block(src):
    """The exact text of the CORS origin-control section of end_headers()."""
    start = src.find(CORS_MARKER)
    if start == -1:
        raise AssertionError("CORS marker %r not found" % CORS_MARKER)
    end = src.find(CORS_END, start)
    if end == -1:
        raise AssertionError("CORS block end marker not found")
    return src[start:end]


class CorsStaticSourceTests(unittest.TestCase):
    """Layer A: shape of the fix and its blast radius, checked on the real file."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_server_source()
        cls.baseline = baseline_source()

    def test_01_cors_condition_uses_exact_origin_matching(self):
        block = cors_block(self.src)
        self.assertIn(
            FIXED_CONDITION.strip(),
            block,
            "the CORS check must be plain `if origin in allowed_origins:`",
        )
        self.assertIn('self.send_header("Access-Control-Allow-Origin", origin)', block)
        self.assertIn('self.send_header("Access-Control-Allow-Credentials", "true")', block)

    def test_02_no_suffix_matching_left_in_the_cors_path(self):
        block = cors_block(self.src)
        self.assertNotIn("endswith", block, "suffix matching must be gone from CORS")
        self.assertNotIn("any(", block, "the any(...endswith...) matcher must be gone")
        for suffix in UNSAFE_SUFFIXES:
            self.assertNotIn(
                '"%s"' % suffix,
                block,
                "unsafe suffix %r must no longer appear in the CORS path" % suffix,
            )
        # No wildcard was introduced in the trusted branch.
        self.assertNotIn('"Access-Control-Allow-Origin", "*"', block)

    def test_03_trusted_origins_are_still_listed(self):
        block = cors_block(self.src)
        for origin in TRUSTED_LITERALS:
            self.assertIn(
                '"%s"' % origin,
                block,
                "trusted origin %r must remain allowed" % origin,
            )
        # APP_URL stays the first allowlist entry.
        self.assertIn("allowed_origins = [", block)
        self.assertRegex(block, r"allowed_origins = \[\s*\n\s*APP_URL,")

    def test_04_only_the_cors_condition_line_changed_vs_baseline(self):
        if self.baseline is None:
            self.skipTest("baseline commit %s not available" % BASELINE_COMMIT)
        # Restoring the old condition must reproduce the baseline byte-for-byte,
        # proving this edit touched nothing else anywhere in server.py.
        self.assertEqual(
            self.src.count(FIXED_CONDITION),
            1,
            "the fixed condition must occur exactly once",
        )
        self.assertEqual(
            self.baseline.count(OLD_CONDITION),
            1,
            "baseline must contain exactly one instance of the vulnerable condition",
        )
        self.assertEqual(
            self.src.replace(FIXED_CONDITION, OLD_CONDITION),
            self.baseline,
            "server.py must differ from baseline %s by that single line only" % BASELINE_COMMIT,
        )

    def test_05_baseline_predicate_really_accepted_the_attackers(self):
        """Teeth: the pre-fix suffix arms must be shown to accept the attacker
        domains, otherwise the behavioural rejections prove nothing."""
        if self.baseline is None:
            self.skipTest("baseline commit %s not available" % BASELINE_COMMIT)
        line = [ln for ln in self.baseline.splitlines() if "allowed_origins or" in ln]
        self.assertEqual(len(line), 1, "expected the vulnerable line in the baseline")
        line = line[0]
        self.assertIn("origin.endswith", line)
        match = re.search(r"for d in \[(.*?)\]", line)
        self.assertIsNotNone(match, "expected the suffix list in the baseline line")
        suffixes = [s.strip().strip('"') for s in match.group(1).split(",")]
        self.assertEqual(suffixes, list(UNSAFE_SUFFIXES))

        def old_predicate(origin, allowed_origins):
            return origin in allowed_origins or (
                origin and any(origin.endswith(d) for d in suffixes)
            )

        for attacker in ("https://evilkindid.in", "https://evil-kindid.in",
                         "https://anything.onrender.com"):
            self.assertTrue(
                old_predicate(attacker, list(TRUSTED_LITERALS)),
                "baseline predicate unexpectedly rejected %r - scenario is wrong" % attacker,
            )
        for attacker in ("https://attacker.example", "https://kindid.in.attacker.com"):
            self.assertFalse(
                old_predicate(attacker, list(TRUSTED_LITERALS)),
                "%r was not a suffix bypass; keep it in the rejection cases" % attacker,
            )


class CorsBehavioralTests(unittest.TestCase):
    """Layer B: probe the real handler in production mode over HTTP."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_cors_")
        cls._orig_db_file = server.DB_FILE
        cls._orig_database_url = server.DATABASE_URL
        cls._orig_environment = server.ENVIRONMENT

        # Keep the real database out of the loop entirely.
        db_copy = os.path.join(cls._tmpdir, "kandid.db")
        if os.path.exists(server.DB_FILE):
            shutil.copy(server.DB_FILE, db_copy)
        server.DATABASE_URL = ""
        server.DB_FILE = db_copy

        # The strict CORS branch is the production one.
        server.ENVIRONMENT = "production"

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KandidHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        cls.app_url = (server.APP_URL or "").strip()
        cls.trusted = [o for o in (cls.app_url,) + TRUSTED_LITERALS if o]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            server.DB_FILE = cls._orig_db_file
            server.DATABASE_URL = cls._orig_database_url
            server.ENVIRONMENT = cls._orig_environment
            shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, origin=None, method="GET"):
        headers = {}
        if origin is not None:
            headers["Origin"] = origin
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return (
                    resp.status,
                    dict((k.lower(), v) for k, v in resp.headers.items()),
                    resp.read(),
                )
        except urllib.error.HTTPError as exc:
            return (
                exc.code,
                dict((k.lower(), v) for k, v in exc.headers.items()),
                exc.read(),
            )

    # ---------------- 1: legitimate origins stay allowed ----------------

    def test_06_trusted_origins_are_allowed_and_echoed(self):
        for origin in self.trusted:
            status, headers, _ = self._request("/health", origin=origin)
            self.assertEqual(status, 200, "origin=%s" % origin)
            self.assertEqual(
                headers.get("access-control-allow-origin"),
                origin,
                "trusted origin %r must be echoed back" % origin,
            )
            self.assertEqual(
                headers.get("access-control-allow-credentials"),
                "true",
                "trusted origin %r must keep credentialed CORS" % origin,
            )

    def test_07_production_branch_is_actually_exercised(self):
        status, _, body = self._request("/health", origin="https://kindid.in")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(
            payload.get("environment"),
            "production",
            "the strict production CORS branch must be the one under test",
        )

    # ---------------- 2-5: attacker origins are rejected ----------------

    def test_08_evilkindid_in_rejected(self):
        self._assert_rejected("https://evilkindid.in")

    def test_09_evil_hyphen_kindid_in_rejected(self):
        self._assert_rejected("https://evil-kindid.in")

    def test_10_kindid_in_attacker_com_rejected(self):
        self._assert_rejected("https://kindid.in.attacker.com")

    def test_11_unrelated_attacker_origins_rejected(self):
        for origin in ("https://attacker.example", "https://notkindid.in",
                       "http://kindid.in"):
            self._assert_rejected(origin)

    def test_12_previously_suffix_matched_origins_now_rejected(self):
        """The suffix arms used to trust any *.kindid.in / *.onrender.com host;
        only explicitly listed origins may be trusted now."""
        for origin in PREVIOUSLY_SUFFIX_MATCHED:
            self._assert_rejected(origin)

    def _assert_rejected(self, origin):
        status, headers, _ = self._request("/health", origin=origin)
        self.assertEqual(status, 200, "origin=%s status=%s" % (origin, status))
        acao = headers.get("access-control-allow-origin")
        self.assertNotEqual(
            acao,
            origin,
            "untrusted origin %r must never be reflected back" % origin,
        )
        self.assertNotEqual(
            headers.get("access-control-allow-credentials"),
            "true",
            "untrusted origin %r must never get credentialed CORS" % origin,
        )
        return acao

    # ---------------- 6: no wildcard acceptance ----------------

    def test_13_no_wildcard_acceptance(self):
        for origin in ATTACKER_ORIGINS + PREVIOUSLY_SUFFIX_MATCHED:
            _, headers, _ = self._request("/health", origin=origin)
            acao = headers.get("access-control-allow-origin")
            creds = headers.get("access-control-allow-credentials")
            self.assertFalse(
                acao == "*" and creds == "true",
                "wildcard + credentials must never be emitted (origin=%r)" % origin,
            )
            self.assertFalse(
                acao == origin,
                "untrusted origin %r must not be echoed" % origin,
            )
        # An untrusted origin falls back to the known APP_URL (or to a bare
        # wildcard without credentials) - never to the caller's origin.
        if self.app_url:
            _, headers, _ = self._request("/health", origin="https://evilkindid.in")
            self.assertEqual(headers.get("access-control-allow-origin"), self.app_url)

    # ---------------- 7: the rest of the CORS behaviour is unchanged ----------------

    def test_14_preflight_and_cors_headers_unchanged(self):
        status, headers, _ = self._request(
            "/api/feed", origin="https://kindid.in", method="OPTIONS"
        )
        self.assertEqual(status, 200, "preflight must still succeed")
        self.assertEqual(
            headers.get("access-control-allow-origin"), "https://kindid.in"
        )
        self.assertEqual(headers.get("access-control-allow-credentials"), "true")
        self.assertEqual(
            headers.get("access-control-allow-headers"),
            "Content-Type, Authorization, X-User-Id",
        )
        self.assertEqual(
            headers.get("access-control-allow-methods"),
            "GET, POST, PUT, DELETE, OPTIONS",
        )

    def test_15_security_headers_unchanged(self):
        _, headers, _ = self._request("/health", origin="https://kindid.in")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(
            headers.get("referrer-policy"), "strict-origin-when-cross-origin"
        )
        self.assertEqual(headers.get("x-xss-protection"), "1; mode=block")
        self.assertIn("no-store", headers.get("cache-control", ""))

    def test_16_missing_origin_header_is_harmless(self):
        status, headers, _ = self._request("/health")
        self.assertEqual(status, 200)
        # No Origin header means not a CORS request; nothing may be echoed.
        self.assertNotEqual(headers.get("access-control-allow-origin"), "")
        self.assertIsNone(headers.get("access-control-allow-credentials"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
