#!/usr/bin/env python3
"""
Focused tests for KINDID Batch-2 B2-SEC-14 (avatar URL attribute injection).

Groups:
  A. /api/user/update — server-side image-URL validation
     - javascript: payload -> 400, nothing written
     - attribute-breaking (quote) payload -> 400
     - data:text/html payload -> 400
     - arbitrary external host -> 400
     - valid /uploads/... accepted unchanged (byte-for-byte)
     - valid Cloudinary URL accepted unchanged
     - valid DiceBear URL accepted unchanged (legacy product support)
     - cover_url: same hostile/valid matrix
  B. /api/user/avatar (+ /api/user/photo alias, /api/user/cover)
     - same hostile/valid coverage where applicable
  C. Static sink verification (app.js)
     - every confirmed avatarSrc/avSrc <img src> sink uses escapeHtml()
     - no raw avatar URL interpolation remains in HTML attributes
     - escapeHtml() itself is unmodified
     - inline onclick handler text is untouched (B2-SEC-15 NOT implemented)
  D. Cache-bust
     - index.html references app.js?v=5.6.1
  E. chat_reactions.media_url latent hardening
     - javascript: rejected, attribute-breaking value rejected,
       arbitrary external host rejected
     - valid /uploads/... accepted unchanged, response contract unchanged
     - empty media_url stays allowed
  F. /api/register avatar_url residual hardening (B2-SEC-14 completion)
     - hostile payloads (javascript:, vbscript:, //host, http://, httpfoo,
       arbitrary hosts, suffix spoofs, quote/control payloads) -> 400,
       no user row written
     - accepted sources preserved: "", /uploads/, Cloudinary, DiceBear,
       googleusercontent.com (lh3..lh6/s2/arbitrary subdomains), data:image
  G. /api/onboarding/complete body-vs-session avatar precedence
     - Case A: hostile body -> verified session google_avatar wins
     - Case B: empty body -> session google_avatar wins
     - Case C: valid body -> byte-exact body value wins
     - Case D: session invalid/empty + hostile/empty body -> "" (no 500)
     - legacy DiceBear substring blanking replaced by the validator
  H. validator-level googleusercontent.com host rules
     - lh3..lh6/s2/arbitrary subdomains accepted; apex accepted
     - suffix spoofs (googleusercontent.com.attacker.com) rejected
     - httpfoo / uppercase-scheme / control-char / traversal rejected

Test harness rule: environment is configured BEFORE importing server so the
module-level configuration picks up a development SQLite setup.
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

TOKEN = "test_token_editor"

CLOUDINARY_URL = "https://res.cloudinary.com/kandid/image/upload/v123/avatar.png"
DICEBEAR_URL = "https://api.dicebear.com/9x/avataaars.svg?seed=kandid"
GOOGLE_AVATAR_URL = "https://lh3.googleusercontent.com/a/ACg8ocK_test=v3"
GOOGLE_AVATAR_SUB_URL = "https://s2.googleusercontent.com/a/sub_test.png"

# B2-SEC-14 residual: payloads that /api/register and
# /api/onboarding/complete must refuse to persist.
HOSTILE_REGISTER_PAYLOADS = [
    "javascript:alert(1)",
    "vbscript:alert(1)",
    "//evil.com/x.png",
    "HTTPS://evil.com/x.png",
    "http://evil.com/x.png",
    "httpfoo",
    "https://evil.example.com/x.png",
    "https://googleusercontent.com.attacker.com/x",
    "https://evil.googleusercontent.com.attacker.com/x",
    'http" onerror="alert(1)',
    "http' onmouseover='alert(1)",
    'http"><img src=x onerror=alert(1)>',
    "https://res.cloudinary.com/a.png\x01",
    "/uploads/../../etc/passwd",
]

HOSTILE_AVATAR_PAYLOADS = [
    "javascript:alert(document.cookie)",
    'https://res.cloudinary.com/x.png" onerror="alert(1)',
    '"><img src=x onerror=alert(1)>',
    "data:text/html,<script>alert(1)</script>",
    "https://evil.example.com/avatar.png",
    "http://res.cloudinary.com/kandid/image/upload/avatar.png",
    "https://res.cloudinary.com.evil.example/avatar.png",
]

HOSTILE_COVER_PAYLOADS = [
    "javascript:alert(document.cookie)",
    "data:text/html,<h1>cover</h1>",
    "https://cdn.totally-unrelated.example/cover.jpg",
]

HOSTILE_MEDIA_PAYLOADS = [
    "javascript:alert(document.cookie)",
    "/uploads/x.png\" onerror=\"alert(1)",
    "https://evil.example.com/reaction.png",
]


def _read(path):
    with open(os.path.join(PROJECT_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


class AvatarUrlBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec14_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_b2sec14.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_editor", "editor@example.test", "editor_handle", "Editor User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_partner", "partner@example.test", "partner_handle", "Partner User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_editor", TOKEN, "u_editor", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO messages (id, sender_id, receiver_id, content) VALUES (?, ?, ?, ?)",
            ("msg_b14", "u_partner", "u_editor", "hello from partner"),
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

    def _user_columns(self, user_id):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url, cover_url FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0], row[1]

    def _set_user_urls(self, avatar_url, cover_url):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET avatar_url = ?, cover_url = ? WHERE id = ?",
                       (avatar_url, cover_url, "u_editor"))
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Group A — /api/user/update
# ---------------------------------------------------------------------------
class TestAUserUpdate(AvatarUrlBase):
    def test_01_rejects_javascript_scheme(self):
        self._set_user_urls("/uploads/keep.png", "")
        status, body = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": "javascript:alert(1)"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success", True))
        self.assertEqual(self._user_columns("u_editor")[0], "/uploads/keep.png")

    def test_02_rejects_attribute_breaking_payload(self):
        status, _ = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": 'https://res.cloudinary.com/x.png" onerror="alert(1)'},
        )
        self.assertEqual(status, 400)

    def test_03_rejects_data_text_html(self):
        status, _ = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": "data:text/html,<script>alert(1)</script>"},
        )
        self.assertEqual(status, 400)

    def test_04_rejects_arbitrary_external_host(self):
        for payload in HOSTILE_AVATAR_PAYLOADS:
            status, _ = self._request(
                "/api/user/update", token=TOKEN, method="POST",
                body={"avatar_url": payload},
            )
            self.assertEqual(status, 400, "expected 400 for %r" % payload)

    def test_05_accepts_uploads_path_unchanged(self):
        status, body = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": "/uploads/avatar-me.png"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(body["user"]["avatar_url"], "/uploads/avatar-me.png")
        self.assertEqual(self._user_columns("u_editor")[0], "/uploads/avatar-me.png")

    def test_06_accepts_cloudinary_url_unchanged(self):
        status, body = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": CLOUDINARY_URL},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["avatar_url"], CLOUDINARY_URL)
        self.assertEqual(self._user_columns("u_editor")[0], CLOUDINARY_URL)

    def test_07_accepts_dicebear_url_unchanged(self):
        status, body = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"avatar_url": DICEBEAR_URL},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["user"]["avatar_url"], DICEBEAR_URL)
        self.assertEqual(self._user_columns("u_editor")[0], DICEBEAR_URL)

    def test_08_cover_url_hostile_rejected_and_valid_accepted(self):
        status, _ = self._request(
            "/api/user/update", token=TOKEN, method="POST",
            body={"cover_url": "javascript:alert(1)"},
        )
        self.assertEqual(status, 400)
        for cover in (CLOUDINARY_URL, "/uploads/cover-me.png"):
            status, body = self._request(
                "/api/user/update", token=TOKEN, method="POST",
                body={"cover_url": cover},
            )
            self.assertEqual(status, 200)
            self.assertEqual(body["user"]["cover_url"], cover)

    def test_09_hostile_cover_leaves_existing_cover_untouched(self):
        self._set_user_urls("", "/uploads/keep-cover.png")
        for payload in HOSTILE_COVER_PAYLOADS:
            status, _ = self._request(
                "/api/user/update", token=TOKEN, method="POST",
                body={"cover_url": payload},
            )
            self.assertEqual(status, 400, "expected 400 for %r" % payload)
        self.assertEqual(self._user_columns("u_editor")[1], "/uploads/keep-cover.png")


# ---------------------------------------------------------------------------
# Group B — /api/user/avatar (and /api/user/photo alias, /api/user/cover)
# ---------------------------------------------------------------------------
class TestBUserAvatar(AvatarUrlBase):
    def test_10_rejects_hostile_avatar_payloads(self):
        for payload in HOSTILE_AVATAR_PAYLOADS:
            status, _ = self._request(
                "/api/user/avatar", token=TOKEN, method="POST",
                body={"avatar_url": payload},
            )
            self.assertEqual(status, 400, "expected 400 for %r" % payload)

    def test_11_alias_photo_rejects_hostile_payloads(self):
        for payload in ("javascript:alert(1)", "https://evil.example.com/a.png"):
            status, _ = self._request(
                "/api/user/photo", token=TOKEN, method="POST",
                body={"photo": payload},
            )
            self.assertEqual(status, 400, "expected 400 for %r" % payload)

    def test_12_accepts_uploads_path_unchanged(self):
        status, body = self._request(
            "/api/user/avatar", token=TOKEN, method="POST",
            body={"avatar_url": "/uploads/new-me.png"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.get("avatar_url"), "/uploads/new-me.png")
        self.assertEqual(self._user_columns("u_editor")[0], "/uploads/new-me.png")

    def test_13_accepts_cloudinary_url_unchanged(self):
        status, body = self._request(
            "/api/user/avatar", token=TOKEN, method="POST",
            body={"avatar_url": CLOUDINARY_URL},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.get("avatar_url"), CLOUDINARY_URL)
        self.assertEqual(self._user_columns("u_editor")[0], CLOUDINARY_URL)

    def test_14_cover_route_rejects_arbitrary_https_host(self):
        status, _ = self._request(
            "/api/user/cover", token=TOKEN, method="POST",
            body={"cover_url": "https://cdn.totally-unrelated.example/cover.jpg"},
        )
        self.assertEqual(status, 400)

    def test_15_cover_route_accepts_cloudinary_unchanged(self):
        status, body = self._request(
            "/api/user/cover", token=TOKEN, method="POST",
            body={"cover_url": CLOUDINARY_URL},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body.get("cover_url"), CLOUDINARY_URL)
        self.assertEqual(self._user_columns("u_editor")[1], CLOUDINARY_URL)


# ---------------------------------------------------------------------------
# Group C — static sink verification (app.js)
# ---------------------------------------------------------------------------
class TestCStaticSinks(unittest.TestCase):
    def test_20_all_nine_avatar_img_sinks_escaped(self):
        src = _read("app.js")
        expectations = [
            # (expected escaped fragment, exact expected count)
            ("var avatarHtml = '<img src=\"' + escapeHtml(avatarSrc) + '\" class=\"w-full h-full object-cover\">';", 1),
            ("      ? '<img src=\"' + escapeHtml(avatarSrc) + '\" class=\"w-full h-full object-cover\">'", 1),
            ("        '<img src=\"' + escapeHtml(avatarSrc) + '\" alt=\"\" class=\"w-11 h-11 rounded-full object-cover flex-shrink-0 border border-neutral-800\">' +", 1),
            ("          '<img src=\"' + escapeHtml(avatarSrc) + '\" class=\"w-full h-full object-cover\">' +", 2),
            ("            '<img src=\"' + escapeHtml(avSrc) + '\" class=\"w-full h-full object-cover\">' +", 1),
            ("          '<img src=\"' + escapeHtml(avatarSrc) + '\" alt=\"' + escapeHtml(name) + '\" class=\"w-full h-full object-cover\">' +", 1),
            ("          '<img src=\"' + escapeHtml(avatarSrc) + '\" alt=\"\" class=\"w-full h-full object-cover\">' +", 1),
            ("(avatarSrc ? '<img src=\"' + escapeHtml(avatarSrc) + '\" class=\"w-full h-full object-cover\" onerror=\"this.style.display=\\047none\\047\">' : '') +", 1),
        ]
        for fragment, expected_count in expectations:
            self.assertEqual(
                src.count(fragment), expected_count,
                "expected %d occurrence(s) of escaped sink: %s" % (expected_count, fragment[:80]),
            )

    def test_21_no_raw_avatar_interpolation_remains_in_img_attributes(self):
        src = _read("app.js")
        self.assertNotIn('img src="' + "' + avatarSrc", src)
        self.assertNotIn('img src="' + "' + avSrc", src)
        self.assertNotIn('img src="' + "' + u.avatar_url", src)
        self.assertNotIn('img src="' + "' + m.avatar_url", src)
        self.assertNotIn('img src="' + "' + p.avatar_url", src)
        self.assertNotIn('img src="' + "' + f.avatar_url", src)

    def test_22_escapehtml_implementation_unmodified(self):
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
        self.assertIn(expected, src, "escapeHtml() must remain byte-for-byte unchanged")

    def test_23_inline_onclick_handlers_untouched(self):
        # Originally pinned during B2-SEC-14 to prevent unauthorized inline
        # handler edits. B2-SEC-15 completion (mandated) converted the three
        # attacker-controlled arguments of this handler to jsAttr(); the pin
        # now guards the AUTHORIZED state: f.id stays raw (server-generated)
        # and name/handle/avatarSrc use jsAttr.
        src = _read("app.js")
        marker = r"""onclick="openChatWithUser(\'' + f.id + '\', \'' + jsAttr(name) + '\', \'' + jsAttr(handle) + '\', \'' + jsAttr(avatarSrc) + '\')">' +"""
        self.assertIn(marker, src, "inline onclick handler must match the authorized post-B2-SEC-15-completion form")


# ---------------------------------------------------------------------------
# Group D — cache-bust
# ---------------------------------------------------------------------------
class TestDCacheBust(unittest.TestCase):
    def test_30_index_references_app_js_5_6_1(self):
        # Version pin maintained across mandated cache-bust bumps (5.6.1 ->
        # 5.6.2 micro commit -> 5.6.3 B2-SEC-16 -> 5.6.4 B2-SEC-15 completion
        # -> 5.6.5 final cluster_id blocker). The invariant under test is:
        # index.html references the CURRENT app.js cache-bust version and no
        # older stale version.
        src = _read("index.html")
        self.assertIn("app.js?v=5.6.5", src)
        self.assertNotIn("app.js?v=5.6.4", src)
        self.assertNotIn("app.js?v=5.6.3", src)
        self.assertNotIn("app.js?v=5.6.2", src)
        self.assertNotIn("app.js?v=5.6.1", src)
        self.assertNotIn("app.js?v=5.6.0", src)


# ---------------------------------------------------------------------------
# Group E — chat_reactions.media_url latent hardening
# ---------------------------------------------------------------------------
class TestEChatReactionMediaUrl(AvatarUrlBase):
    def test_40_rejects_javascript_media_url(self):
        status, _ = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_b14", "emoji": "❤️", "media_url": "javascript:alert(1)"},
        )
        self.assertEqual(status, 400)

    def test_41_rejects_attribute_breaking_media_url(self):
        status, _ = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_b14", "emoji": "❤️", "media_url": '/uploads/x.png" onerror="alert(1)'},
        )
        self.assertEqual(status, 400)

    def test_42_rejects_arbitrary_external_media_host(self):
        for payload in HOSTILE_MEDIA_PAYLOADS:
            status, _ = self._request(
                "/api/chat/reactions", token=TOKEN, method="POST",
                body={"message_id": "msg_b14", "emoji": "❤️", "media_url": payload},
            )
            self.assertEqual(status, 400, "expected 400 for %r" % payload)

    def test_43_accepts_uploads_media_url_unchanged_and_contract_intact(self):
        status, body = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_b14", "emoji": "❤️", "media_url": "/uploads/reaction.png"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        # Response contract unchanged
        for key in ("success", "action", "message_id", "reactions"):
            self.assertIn(key, body)
        self.assertEqual(body["message_id"], "msg_b14")
        mine = [r for r in body["reactions"] if r.get("user_id") == "u_editor"]
        self.assertTrue(mine)
        self.assertEqual(mine[0].get("media_url"), "/uploads/reaction.png")

    def test_44_empty_media_url_still_allowed(self):
        status, body = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_b14", "emoji": "👏", "media_url": ""},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))


# ---------------------------------------------------------------------------
# Group F — /api/register avatar_url residual hardening
# ---------------------------------------------------------------------------
class TestFRegisterAvatar(AvatarUrlBase):
    def _stored_avatar(self, handle):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url FROM users WHERE handle = ?", (handle,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def _register(self, handle, avatar):
        return self._request(
            "/api/register", method="POST",
            body={"name": "Reg User", "handle": handle, "avatar_url": avatar},
        )

    def test_01_hostile_payloads_rejected_400_no_row(self):
        for i, payload in enumerate(HOSTILE_REGISTER_PAYLOADS):
            handle = "reg_hostile_%02d" % i
            status, body = self._request(
                "/api/register", method="POST",
                body={"name": "Reg User", "handle": handle, "avatar_url": payload},
            )
            self.assertEqual(status, 400, "expected 400 for avatar %r" % payload[:60])
            self.assertFalse(body.get("success", True))
            self.assertIsNone(self._stored_avatar(handle), "no user row may be written for %r" % payload[:60])

    def test_02_avatar_alias_field_also_validated(self):
        status, _ = self._request(
            "/api/register", method="POST",
            body={"name": "Reg User", "handle": "reg_alias_hostile", "avatar": "javascript:alert(1)"},
        )
        self.assertEqual(status, 400)
        self.assertIsNone(self._stored_avatar("reg_alias_hostile"))

    def test_03_empty_avatar_creates_user_with_empty_avatar(self):
        status, body = self._register("reg_avatar_user", "")
        self.assertEqual(status, 201)
        self.assertTrue(body.get("success"))
        self.assertEqual(body["user"]["avatar_url"], "")
        self.assertEqual(self._stored_avatar("reg_avatar_user"), "")

    def test_04_uploads_path_preserved(self):
        status, body = self._register("reg_uploads_ok", "/uploads/example.jpg")
        self.assertEqual(status, 201)
        self.assertEqual(body["user"]["avatar_url"], "/uploads/example.jpg")
        self.assertEqual(self._stored_avatar("reg_uploads_ok"), "/uploads/example.jpg")

    def test_05_cloudinary_preserved(self):
        status, body = self._register("reg_cloud_ok", CLOUDINARY_URL)
        self.assertEqual(status, 201)
        self.assertEqual(self._stored_avatar("reg_cloud_ok"), CLOUDINARY_URL)

    def test_06_dicebear_preserved(self):
        status, body = self._register("reg_dice_ok", DICEBEAR_URL)
        self.assertEqual(status, 201)
        self.assertEqual(self._stored_avatar("reg_dice_ok"), DICEBEAR_URL)

    def test_07_googleusercontent_preserved(self):
        for i, url in enumerate((GOOGLE_AVATAR_URL, GOOGLE_AVATAR_SUB_URL)):
            handle = "reg_google_%d" % i
            status, body = self._register(handle, url)
            self.assertEqual(status, 201, "legitimate Google avatar %r must be accepted" % url)
            self.assertEqual(self._stored_avatar(handle), url)

    def test_08_data_image_capture_flow_preserved(self):
        data_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        status, body = self._register("reg_dataimage_ok", data_image)
        self.assertEqual(status, 201)
        stored = self._stored_avatar("reg_dataimage_ok")
        self.assertTrue(
            stored.startswith("/uploads/") or stored.startswith("https://res.cloudinary.com/"),
            "data:image capture must resolve to /uploads/ (dev) or Cloudinary (got %r)" % stored,
        )


# ---------------------------------------------------------------------------
# Group G — /api/onboarding/complete body-vs-session avatar precedence
# ---------------------------------------------------------------------------
class TestGOnboardingAvatarPrecedence(AvatarUrlBase):
    def _seed_session(self, session_id, google_avatar):
        conn = server.get_db()
        cursor = conn.cursor()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()
        cursor.execute(
            """INSERT INTO onboarding_sessions
                   (id, provider, provider_subject, email, google_name, google_avatar,
                    step, chosen_handle, chosen_campus_id, chosen_campus_name, chosen_city, expires_at)
               VALUES (?, 'google', ?, ?, 'Google User', ?, 2, ?, '', '', '', ?)""",
            (session_id, "sub_" + session_id, session_id.replace("onb_", "u") + "@example.test",
             google_avatar, session_id.replace("onb_", "hdl_"), future_iso),
        )
        conn.commit()
        conn.close()

    def _complete(self, session_id, avatar):
        return self._request(
            "/api/onboarding/complete", method="POST",
            body={"session_id": session_id, "handle": session_id.replace("onb_", "hdl_"), "avatar_url": avatar},
        )

    def _stored_avatar(self, email):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT avatar_url FROM users WHERE LOWER(email) = ?", (email.lower(),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def _email_for(self, session_id):
        return session_id.replace("onb_", "u") + "@example.test"

    def _user_exists(self, email):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE LOWER(email) = ?", (email.lower(),))
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def test_case_a_hostile_body_never_persisted_session_fallback(self):
        for i, payload in enumerate(HOSTILE_REGISTER_PAYLOADS):
            sid = "onb_case_a_r%02d" % i
            self._seed_session(sid, GOOGLE_AVATAR_URL)
            status, _ = self._complete(sid, payload)
            self.assertEqual(status, 200, "hostile avatar must not break onboarding (%r)" % payload[:50])
            stored = self._stored_avatar(sid.replace("onb_", "u") + "@example.test")
            self.assertNotEqual(stored, payload)
            self.assertEqual(stored, GOOGLE_AVATAR_URL, "verified session google_avatar must win over hostile body")

    def test_case_a2_single_hostile_body_falls_back_to_session(self):
        self._seed_session("onb_case_a2", GOOGLE_AVATAR_URL)
        status, _ = self._complete("onb_case_a2", "javascript:alert(1)")
        self.assertEqual(status, 200)
        self.assertEqual(
            self._stored_avatar(self._email_for("onb_case_a2")),
            GOOGLE_AVATAR_URL,
            "hostile body.avatar_url must fall back to the verified session google_avatar",
        )

    def test_case_b_empty_body_keeps_session_google_avatar(self):
        self._seed_session("onb_case_b", GOOGLE_AVATAR_URL)
        status, body = self._complete("onb_case_b", "")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(body["user"]["avatar_url"], GOOGLE_AVATAR_URL)
        self.assertEqual(self._stored_avatar(self._email_for("onb_case_b")), GOOGLE_AVATAR_URL)

    def test_case_c_valid_body_wins_byte_exact(self):
        for i, valid in enumerate((DICEBEAR_URL, CLOUDINARY_URL, "/uploads/onboard_capture.jpg",
                                   GOOGLE_AVATAR_SUB_URL)):
            sid = "onb_case_c%d" % i
            self._seed_session(sid, GOOGLE_AVATAR_URL)
            status, body = self._complete(sid, valid)
            self.assertEqual(status, 200)
            self.assertEqual(body["user"]["avatar_url"], valid)
            self.assertEqual(
                self._stored_avatar(sid.replace("onb_", "u") + "@example.test"), valid,
                "valid body.avatar_url must win byte-exact over the session value",
            )

    def test_case_d_no_google_avatar_hostile_body_degrades_to_empty(self):
        self._seed_session("onb_case_d", "")
        status, body = self._complete("onb_case_d", "javascript:alert(1)")
        self.assertEqual(status, 200, "onboarding must not 500 when avatar validation degrades")
        self.assertTrue(body.get("success"))
        self.assertEqual(self._stored_avatar(self._email_for("onb_case_d")), "")

    def test_case_d2_no_google_avatar_empty_body_degrades_to_empty(self):
        self._seed_session("onb_case_d2", "")
        status, _ = self._complete("onb_case_d2", "")
        self.assertEqual(status, 200)
        self.assertEqual(self._stored_avatar(self._email_for("onb_case_d2")), "")

    def test_dicebear_substring_blanking_replaced_by_validator(self):
        # Legacy behavior blanked ANY DiceBear URL; the validator now accepts
        # it as a legitimate avatar source (parity with /api/user/update).
        self._seed_session("onb_dice_valid", "")
        status, _ = self._complete("onb_dice_valid", DICEBEAR_URL)
        self.assertEqual(status, 200)
        self.assertEqual(self._stored_avatar(self._email_for("onb_dice_valid")), DICEBEAR_URL)


# ---------------------------------------------------------------------------
# Group H — validator-level googleusercontent.com host rules
# ---------------------------------------------------------------------------
class TestHGoogleHostRules(unittest.TestCase):
    def test_01_google_subdomains_accepted(self):
        for host in ("lh3", "lh4", "lh5", "lh6", "s2"):
            url = "https://%s.googleusercontent.com/a/photo" % host
            self.assertEqual(server.validate_media_url(url, "avatar_url"), url)

    def test_02_arbitrary_subdomain_and_apex_accepted(self):
        for url in ("https://sub.googleusercontent.com/a/x.png",
                    "https://googleusercontent.com/a/apex.png"):
            self.assertEqual(server.validate_media_url(url, "avatar_url"), url)

    def test_03_suffix_spoofs_rejected(self):
        for url in ("https://googleusercontent.com.attacker.com/x",
                    "https://evil.googleusercontent.com.attacker.com/x"):
            with self.assertRaises(ValueError):
                server.validate_media_url(url, "avatar_url")

    def test_04_google_avatar_requires_https_allowlisted_host(self):
        # urlsplit() lowercases the scheme, so "HTTPS://..." is only accepted
        # when the HOST itself is allowlisted (HTTPS://evil.com is rejected
        # via hostname mismatch; HTTPS://lh3.googleusercontent.com is a
        # legitimate Google image URL and stays accepted).
        for url in ("http://lh3.googleusercontent.com/a/x.png",
                    "//lh3.googleusercontent.com/a/x.png",
                    "HTTPS://evil.com/x.png"):
            with self.assertRaises(ValueError):
                server.validate_media_url(url, "avatar_url")
        self.assertEqual(
            server.validate_media_url("HTTPS://lh3.googleusercontent.com/a/x.png", "avatar_url"),
            "HTTPS://lh3.googleusercontent.com/a/x.png",
        )

    def test_05_httpfoo_control_chars_and_traversal_rejected(self):
        for url in ("httpfoo",
                    "https://res.cloudinary.com/a.png\x01",
                    "/uploads/../../etc/passwd",
                    "/uploads/ok.png/../../../etc"):
            with self.assertRaises(ValueError):
                server.validate_media_url(url, "avatar_url")

    def test_06_uploads_traversal_rejected_but_valid_paths_kept(self):
        with self.assertRaises(ValueError):
            server.validate_media_url("/uploads/../../etc/passwd", "avatar_url")
        self.assertEqual(
            server.validate_media_url("/uploads/example.jpg", "avatar_url"),
            "/uploads/example.jpg",
        )

    def test_07_sinks_and_cache_state_untouched(self):
        # B2-SEC-15/16 sink regressions + cache state must remain unchanged.
        app_src = _read("app.js")
        self.assertIn("jsAttr(avatarSrc)", app_src)
        self.assertIn("function escapeHtml(str)", app_src)
        self.assertIn("app.js?v=5.6.5", _read("index.html"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
