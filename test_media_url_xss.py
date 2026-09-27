#!/usr/bin/env python3
"""
Focused tests for KINDID Batch-2 B2-SEC-16 (stored XSS via post media URLs).

Chain being closed:
  /api/moments/capture -> save_base64_image() (passes http(s):///uploads/
  strings through verbatim) -> posts.main_img / posts.pip_img -> API response
  -> raw <img src> interpolation -> attribute breakout -> JS execution.

Groups:
  A. Server-side rejection through the REAL /api/moments/capture request
     path (mainImg/main_img and pipImg/pip_img variants), covering:
     attribute-breaking http/https payloads, arbitrary external hosts,
     javascript:, data:text/html, scheme-relative //, backslash tricks,
     control characters. Hostile requests get HTTP 400 and NOTHING is
     written to posts.main_img / posts.pip_img.
  B. Valid media behavior: generated /uploads/... media and the Cloudinary
     delivery host actually used by the product (res.cloudinary.com, the
     host upload_to_cloudinary()'s secure_url always returns) round-trip
     byte-for-byte. DiceBear is avatar-only and must be REJECTED for posts.
  C. Database write behavior: no hostile value is ever stored.
  D. Static sink checks: all confirmed sinks (410/412/766/779/1938/1940/8714)
     plus the missed sibling (community pulse p.main_img) use escapeHtml();
     no raw attacker-controlled media interpolation remains.
  E. Cache-bust: index.html references app.js?v=5.6.3 (the mandate's 5.6.2
     was already shipped in commit 9fad7f9, so the version moves forward).
  F. Regression: hostile payloads in OTHER fields (avatar_url) keep their
     B2-SEC-14 400 behavior; B2-SEC-15 jsAttr is intact.

Test harness rule: environment is configured BEFORE importing server.
"""

import os

os.environ["DATABASE_URL"] = ""
os.environ["ENVIRONMENT"] = "development"

import json
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler

TOKEN = "test_token_capturer"

CLOUDINARY_MEDIA = "https://res.cloudinary.com/kandid/image/upload/v123/main_capture.png"
DICEBEAR_URL = "https://api.dicebear.com/9x/avataaars.svg?seed=x"

# Hostile payloads targeting the media fields specifically.
HOSTILE_MEDIA_PAYLOADS = [
    'http://x" onerror="alert(1)',
    'https://x"><svg onload=alert(1)>',
    "https://evil.example.com/capture.png",          # arbitrary external host
    "https://res.cloudinary.com.evil.example/x.png", # spoofed subdomain suffix
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "//res.cloudinary.com/kandid/image/upload/x.png",  # scheme-relative
    "/uploads/../..\\windows.png",                     # backslash trick
    'https://res.cloudinary.com/a.png\' onclick=\'alert(1)',  # quote-breaking
    "https://res.cloudinary.com/a\x01.png",            # control character
]

SINKS = [
    # (old line number from the finding, exact escaped fragment, expected count)
    (410,  "'<img src=\"' + escapeHtml(mainImgSrc) + '\" class=\"w-full h-full object-cover main-stage-img\" alt=\"Global Moment\">' +", 1),
    (412,  "'<img src=\"' + escapeHtml(pipImgSrc) + '\" class=\"w-full h-full object-cover pip-sub-img\" alt=\"Selfie Photo\">' +", 3),
    (766,  "'<img class=\"w-full h-full object-cover main-stage-img\" src=\"' + escapeHtml(mainImgSrc) + '\" alt=\"Real moment\">' +", 1),
    (1938, "'<img src=\"' + escapeHtml(mainImgSrc) + '\" class=\"w-full h-full object-cover main-stage-img\" alt=\"Moment Photo\">' +", 1),
    (8714, "'<img src=\"' + escapeHtml(imgUrl) + '\" class=\"w-full h-full object-cover group-hover:scale-105 transition-transform\">' +", 1),
]


def _read(path):
    with open(os.path.join(PROJECT_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


class MediaUrlBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec16_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_b2sec16.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_cap", "capturer@example.test", "capturer_handle", "Capturer User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_cap", TOKEN, "u_cap", future_iso, now_iso),
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        server.DB_FILE = cls._orig_db
        server.DATABASE_URL = cls._orig_url
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _request(self, path, token=None, method="GET", body=None):
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

        t = threading.Thread(target=run_handler)
        t.start()

        body_bytes = b""
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body_bytes = body.encode("utf-8")
            elif isinstance(body, bytes):
                body_bytes = body

        req = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
        if token:
            req += f"Authorization: Bearer {token}\r\n"
        if body_bytes:
            req += f"Content-Type: application/json\r\nContent-Length: {len(body_bytes)}\r\n"
        req += "\r\n"

        s2.settimeout(5.0)
        s2.sendall(req.encode("utf-8") + body_bytes)
        try:
            s2.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        chunks = []
        while True:
            try:
                chunk = s2.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        s2.close()
        t.join(timeout=5.0)

        raw = b"".join(chunks).decode("utf-8")
        headers_part, _, body_part = raw.partition("\r\n\r\n")
        status_line = headers_part.splitlines()[0]
        status_code = int(status_line.split()[1])
        try:
            parsed = json.loads(body_part)
        except Exception:
            parsed = body_part
        return status_code, parsed

    def _capture(self, media_body):
        """POST /api/moments/capture with the given media fields."""
        body = {"caption": "test moment"}
        body.update(media_body)
        return self._request("/api/moments/capture", token=TOKEN, method="POST", body=body)

    def _stored_posts(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT main_img, pip_img, caption FROM posts")
        rows = cursor.fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]


# ---------------------------------------------------------------------------
# Group A — server-side rejection through the real request path
# ---------------------------------------------------------------------------
class TestAServerSideRejection(MediaUrlBase):
    VARIANTS = [
        ("mainImg", "main_img"),
        ("pipImg", "pip_img"),
    ]

    def test_01_every_hostile_payload_rejected_on_every_variant(self):
        for key_a, _ in self.VARIANTS:
            for payload in HOSTILE_MEDIA_PAYLOADS:
                status, body = self._capture({key_a: payload})
                self.assertEqual(
                    status, 400,
                    "expected 400 for %s=%r, got %s (%r)" % (key_a, payload[:60], status, body),
                )
                self.assertFalse(body.get("success", True))

    def test_02_alias_names_rejected_too(self):
        for _, key_b in self.VARIANTS:
            for payload in ('http://x" onerror="alert(1)', "javascript:alert(1)"):
                status, _ = self._capture({key_b: payload})
                self.assertEqual(status, 400, "expected 400 for %s=%r" % (key_b, payload))

    def test_03_both_fields_hostile_rejected(self):
        status, _ = self._capture({
            "mainImg": "javascript:alert(1)",
            "pipImg": "https://evil.example.com/pip.png",
        })
        self.assertEqual(status, 400)

    def test_04_no_post_row_created_for_hostile_payloads(self):
        conn = server.get_db()
        conn.execute("DELETE FROM posts")
        conn.commit()
        conn.close()
        for payload in HOSTILE_MEDIA_PAYLOADS:
            self._capture({"mainImg": payload, "pipImg": payload})
        self.assertEqual(len(self._stored_posts()), 0, "no post row may be created for hostile media payloads")


# ---------------------------------------------------------------------------
# Group B — valid media behavior
# ---------------------------------------------------------------------------
class TestBValidMedia(MediaUrlBase):
    def test_10_generated_uploads_media_round_trips(self):
        status, body = self._capture({"mainImg": "/uploads/main_deadbeef.png"})
        self.assertEqual(status, 201)
        self.assertTrue(body.get("success"))
        self.assertEqual(body["post"]["main_img"], "/uploads/main_deadbeef.png")

    def test_11_cloudinary_media_round_trips_unchanged(self):
        status, body = self._capture({"mainImg": CLOUDINARY_MEDIA})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["main_img"], CLOUDINARY_MEDIA)

    def test_12_both_fields_valid_accepted(self):
        status, body = self._capture({
            "mainImg": "/uploads/main_1.png",
            "pipImg": CLOUDINARY_MEDIA,
        })
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["main_img"], "/uploads/main_1.png")
        self.assertEqual(body["post"]["pip_img"], CLOUDINARY_MEDIA)

    def test_13_empty_media_still_allowed(self):
        status, body = self._capture({"mainImg": "", "pipImg": ""})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["main_img"], "")
        self.assertEqual(body["post"]["pip_img"], "")

    def test_14_dicebear_is_avatar_only_and_rejected_for_posts(self):
        status, _ = self._capture({"mainImg": DICEBEAR_URL})
        self.assertEqual(status, 400, "DiceBear is not a valid post-media host")

    def test_15_base64_capture_flow_unaffected(self):
        # The legitimate base64 capture flow (data:image/...) must keep
        # working: without Cloudinary config the dev fallback persists the
        # decoded bytes under /uploads/ and returns that path.
        status, body = self._capture({"mainImg": "data:image/png;base64,iVBORw0KGgo="})
        self.assertEqual(status, 201)
        self.assertTrue(
            body["post"]["main_img"].startswith("/uploads/"),
            "base64 capture flow must still persist local media (got %r)" % body["post"]["main_img"],
        )

    def test_16_dangerous_raw_schemes_rejected_not_silently_emptied(self):
        # save_base64_image() would silently discard javascript:/data:text/html
        # into an empty-but-successful capture; the server must 400 instead.
        for payload in ("javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:alert(1)"):
            status, _ = self._capture({"mainImg": payload})
            self.assertEqual(status, 400, "raw scheme %r must be rejected" % payload)


# ---------------------------------------------------------------------------
# Group C — database write behavior
# ---------------------------------------------------------------------------
class TestCDatabaseWriteBlocking(MediaUrlBase):
    def test_20_no_unsafe_value_ever_stored(self):
        for payload in HOSTILE_MEDIA_PAYLOADS:
            self._capture({"mainImg": payload})
            self._capture({"pipImg": payload})
        for main_img, pip_img in self._stored_posts():
            for stored in (main_img, pip_img):
                for payload in HOSTILE_MEDIA_PAYLOADS:
                    self.assertNotEqual(stored, payload)
                    self.assertNotIn("onerror", (stored or ""))
                    self.assertNotIn("<svg", (stored or ""))
                    self.assertNotIn("javascript:", (stored or ""))
                if stored:
                    # Every stored value must satisfy the server validator.
                    server.validate_post_media_url(stored)

    def test_21_valid_rows_present_after_mixed_traffic(self):
        # Seed one legitimate capture, then hammer with hostile payloads;
        # the valid row must survive and no hostile row may appear.
        status, body = self._capture({"mainImg": "/uploads/main_valid_check.png"})
        self.assertEqual(status, 201)
        valid_post_id = body["post"]["id"]
        for payload in HOSTILE_MEDIA_PAYLOADS:
            self._capture({"mainImg": payload})
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT main_img, pip_img FROM posts")
        rows = cursor.fetchall()
        conn.close()
        self.assertTrue(rows, "legitimate captures must have been stored")
        for main_img, pip_img in rows:
            for stored in (main_img, pip_img):
                for payload in HOSTILE_MEDIA_PAYLOADS:
                    self.assertNotEqual(stored, payload)
                # Every stored value must satisfy the server validator.
                server.validate_post_media_url(stored or "")
        # The seeded valid row must still hold its exact value.
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT main_img FROM posts WHERE id = ?", (valid_post_id,))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "/uploads/main_valid_check.png")


# ---------------------------------------------------------------------------
# Group D — static sink checks
# ---------------------------------------------------------------------------
class TestDStaticSinks(unittest.TestCase):
    def test_30_all_confirmed_sinks_escaped(self):
        src = _read("app.js")
        for old_line, fragment, expected_count in SINKS:
            self.assertEqual(
                src.count(fragment), expected_count,
                "sink from finding line %d must use escapeHtml (fragment: %s)" % (old_line, fragment[:70]),
            )

    def test_31_missed_sibling_sink_escaped(self):
        src = _read("app.js")
        self.assertIn(
            "'<img src=\"' + escapeHtml(p.main_img || '') + '\" class=\"w-full h-full object-cover\">' +",
            src,
            "the community pulse sibling sink (p.main_img) must be escaped",
        )

    def test_32_no_raw_post_media_interpolation_remains(self):
        src = _read("app.js")
        import re
        self.assertIsNone(
            re.search(r"img src=\"' \+ (mainImgSrc|pipImgSrc)\b", src),
            "no raw mainImgSrc/pipImgSrc interpolation may remain",
        )
        # The chat moment picker imgUrl sink must be escaped.
        self.assertNotIn('img src="' + "' + imgUrl + '" + '" class="w-full h-full object-cover group-hover:scale-105 transition-transform">', src)

    def test_33_safe_by_construction_sinks_documented(self):
        # imgUrl/locStr interpolations at ~4073/~5120 are pre-escaped at
        # assignment (var imgUrl = escapeHtml(...)); pin that invariant.
        src = _read("app.js")
        self.assertIn("var imgUrl = escapeHtml(m.main_img || m.mediaUrl || m.media_url || m.mainImg || '');", src)
        self.assertIn("var imgSrc = escapeHtml(m.mediaUrl || m.mainImg || m.main_img || '');", src)

    def test_34_escapehtml_implementation_untouched(self):
        src = _read("app.js")
        expected = (
            "function escapeHtml(str) {\n"
            "  if (!str) return '';\n"
            "  return String(str)\n"
            "    .replace(/&/g, '&amp;')\n"
            "    .replace(/</g, '&lt;')\n"
            "    .replace(/>/g, '&gt;')\n"
            "    .replace(/\"/g, '&quot;')\n"
            "    .replace(/'/g, '&#039;');\n"
            "}"
        )
        self.assertIn(expected, src)

    def test_35_no_inline_handler_changes(self):
        # jsAttr usage pin, maintained across mandated B2-SEC-15 work:
        # 10 (initial conversions) + 6 (completion: audioUrl, friend
        # name/handle/avatarSrc, r.target_id x3) + 2 (final cluster_id
        # blocker) usages + 1 definition = 20.
        src = _read("app.js")
        self.assertEqual(src.count("jsAttr("), 20)


# ---------------------------------------------------------------------------
# Group E — cache-bust
# ---------------------------------------------------------------------------
class TestECacheBust(unittest.TestCase):
    def test_40_index_references_app_js_5_6_3(self):
        # Version pin maintained across mandated cache-bust bumps (now 5.6.5
        # from the final cluster_id blocker). Invariant: current version
        # present, all older ones absent.
        src = _read("index.html")
        self.assertIn("app.js?v=5.6.5", src)
        self.assertNotIn("app.js?v=5.6.4", src)
        self.assertNotIn("app.js?v=5.6.3", src)
        self.assertNotIn("app.js?v=5.6.2", src)
        self.assertNotIn("app.js?v=5.6.1", src)


# ---------------------------------------------------------------------------
# Group F — regression boundaries
# ---------------------------------------------------------------------------
class TestFRegressionBoundaries(MediaUrlBase):
    def test_50_avatar_validation_still_enforced_on_user_update(self):
        status, _ = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": "javascript:alert(1)"},
        )
        self.assertEqual(status, 400, "B2-SEC-14 avatar validation must remain active")

    def test_51_reaction_allowlist_still_enforced(self):
        status, _ = self._request(
            "/api/react", token=TOKEN, method="POST",
            body={"postId": "whatever", "emoji": "<script>alert(1)</script>"},
        )
        self.assertEqual(status, 400, "B2-SEC-01 reaction allowlist must remain active")

    def test_52_capture_requires_auth(self):
        status, _ = self._request(
            "/api/moments/capture", token=None, method="POST",
            body={"caption": "anon", "mainImg": "javascript:alert(1)"},
        )
        self.assertEqual(status, 401, "unauthenticated capture must still be rejected")

    def test_53_server_validator_unit_matrix(self):
        cases = [
            ("", True),
            ("/uploads/main_x.png", True),
            (CLOUDINARY_MEDIA, True),
            ("https://res.cloudinary.com.evil.example/x.png", False),
            ("http://res.cloudinary.com/x.png", False),
            ("javascript:alert(1)", False),
            ("data:text/html,<x>", False),
            ("//res.cloudinary.com/x.png", False),
            ('https://res.cloudinary.com/x.png" onerror="a()', False),
            ("https://res.cloudinary.com/x.png\x07", False),
        ]
        for value, expected in cases:
            self.assertEqual(
                server._b16_post_media_url_is_safe(value), expected,
                "validator matrix failed for %r" % value,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
