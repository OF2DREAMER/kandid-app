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
        # B2-SEC-15 is explicitly out of scope: the openChatWithUser inline
        # onclick (one of the 43 handlers) must remain byte-for-byte intact.
        src = _read("app.js")
        marker = r"""onclick="openChatWithUser(\'' + f.id + '\', \'' + escapeHtml(name) + '\', \'' + escapeHtml(handle) + '\', \'' + escapeHtml(avatarSrc) + '\')">' +"""
        self.assertIn(marker, src, "inline onclick handlers must not be modified in this commit")


# ---------------------------------------------------------------------------
# Group D — cache-bust
# ---------------------------------------------------------------------------
class TestDCacheBust(unittest.TestCase):
    def test_30_index_references_app_js_5_6_1(self):
        src = _read("index.html")
        self.assertIn("app.js?v=5.6.1", src)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
