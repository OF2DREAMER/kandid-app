#!/usr/bin/env python3
"""
Focused tests for KINDID Batch-2 B2-SEC-01 (stored reaction XSS remediation).

Groups:
  A. /api/react — server-side allowlist validation
     - <script> payload rejected (HTTP 400, nothing written to DB)
     - <img onerror> payload rejected
     - arbitrary HTML/JS-like payloads rejected
     - over-length payload rejected
     - every legitimate shipped reaction emoji accepted byte-for-byte
  B. /api/chat/reactions — identical validation applied
     - same rejection/acceptance matrix
  C. Static sink verification (app.js)
     - moment feed reaction pills use escapeHtml
     - moment detail reaction pills use escapeHtml
     - chat reaction pill uses escapeHtml
     - escapeHtml() itself is unmodified
  D. Regression / output checks
     - legitimate reaction values round-trip byte-for-byte (API + DB)
     - attacker-controlled HTML never reaches the database
     - reaction rendering templates no longer concatenate raw emoji

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

TOKEN = "test_token_reactor"

# The exact reaction values shipped by the app (moment popover + modal,
# chat reaction sheet, selfie Realmoji) — must be preserved byte-for-byte.
LEGIT_REACTIONS = ["🔥", "⚡", "😮", "❤️", "👏", "☕", "😂", "💯", "🤳"]

ATTACK_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '"><svg/onload=alert(1)>',
    "javascript:alert(document.cookie)",
    "<iframe src=javascript:alert(1)></iframe>",
]

OVERLENGTH_PAYLOAD = "🔥" * 17  # 17 chars > MAX_EMOJI_LEN (16)


class ReactionXssBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec01_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_b2sec01.db")
        server.init_db()

        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()

        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_reactor", "reactor@example.test", "reactor_handle", "Reactor User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_author", "author@example.test", "author_handle", "Author User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_reactor", TOKEN, "u_reactor", future_iso, now_iso),
        )
        cursor.execute(
            "INSERT INTO posts (id, user_id, author_name, author_handle, main_img, pip_img) VALUES (?, ?, ?, ?, ?, ?)",
            ("post_xss", "u_author", "Author User", "author_handle", "a.jpg", "b.jpg"),
        )
        cursor.execute(
            "INSERT INTO messages (id, sender_id, receiver_id, content) VALUES (?, ?, ?, ?)",
            ("msg_xss", "u_author", "u_reactor", "hello from author"),
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

    def _stored_emojis(self, table, where_clause="", params=()):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT emoji FROM %s %s" % (table, where_clause), params)
        rows = [r[0] for r in cursor.fetchall()]
        conn.close()
        return rows


# ---------------------------------------------------------------------------
# Group A — /api/react
# ---------------------------------------------------------------------------
class TestAReactRejectsPayloads(ReactionXssBase):
    def _reject(self, emoji):
        status, body = self._request(
            "/api/react", token=TOKEN, method="POST",
            body={"postId": "post_xss", "emoji": emoji},
        )
        self.assertEqual(status, 400, "expected 400 for payload %r, got %s (%r)" % (emoji, status, body))
        self.assertFalse(body.get("success", True) if isinstance(body, dict) else True)

    def test_01_rejects_script_payload(self):
        self._reject("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", self._stored_emojis("reactions"))

    def test_02_rejects_img_onerror_payload(self):
        self._reject("<img src=x onerror=alert(1)>")
        self.assertNotIn("<img src=x onerror=alert(1)>", self._stored_emojis("reactions"))

    def test_03_rejects_arbitrary_html_js_payloads(self):
        for payload in ATTACK_PAYLOADS:
            self._reject(payload)
        for payload in ATTACK_PAYLOADS:
            self.assertNotIn(payload, self._stored_emojis("reactions"))

    def test_04_rejects_over_length_payload(self):
        self._reject(OVERLENGTH_PAYLOAD)
        self.assertNotIn(OVERLENGTH_PAYLOAD, self._stored_emojis("reactions"))

    def test_05_rejects_non_string_reaction(self):
        status, _ = self._request(
            "/api/react", token=TOKEN, method="POST",
            body={"postId": "post_xss", "emoji": None},
        )
        self.assertEqual(status, 400)


# ---------------------------------------------------------------------------
# Group B — /api/chat/reactions
# ---------------------------------------------------------------------------
class TestBChatReactionsRejectsPayloads(ReactionXssBase):
    def _reject(self, emoji):
        status, body = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_xss", "emoji": emoji},
        )
        self.assertEqual(status, 400, "expected 400 for payload %r, got %s (%r)" % (emoji, status, body))
        self.assertFalse(body.get("success", True) if isinstance(body, dict) else True)

    def test_10_rejects_script_payload(self):
        self._reject("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", self._stored_emojis("chat_reactions"))

    def test_11_rejects_img_onerror_payload(self):
        self._reject("<img src=x onerror=alert(1)>")
        self.assertNotIn("<img src=x onerror=alert(1)>", self._stored_emojis("chat_reactions"))

    def test_12_rejects_arbitrary_html_js_payloads(self):
        for payload in ATTACK_PAYLOADS:
            self._reject(payload)
        for payload in ATTACK_PAYLOADS:
            self.assertNotIn(payload, self._stored_emojis("chat_reactions"))

    def test_13_rejects_over_length_payload(self):
        self._reject(OVERLENGTH_PAYLOAD)
        self.assertNotIn(OVERLENGTH_PAYLOAD, self._stored_emojis("chat_reactions"))

    def test_14_accepts_legitimate_chat_emoji(self):
        status, body = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_xss", "emoji": "❤️"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertIn(body.get("action"), ("added", "updated"))
        stored = self._stored_emojis("chat_reactions", "WHERE message_id = ?", ("msg_xss",))
        self.assertIn("❤️", stored)  # byte-for-byte

    def test_15_updates_to_another_legitimate_emoji(self):
        status, body = self._request(
            "/api/chat/reactions", token=TOKEN, method="POST",
            body={"message_id": "msg_xss", "emoji": "😂"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        stored = self._stored_emojis("chat_reactions", "WHERE message_id = ?", ("msg_xss",))
        self.assertIn("😂", stored)  # byte-for-byte


# ---------------------------------------------------------------------------
# Group C — static sink verification in app.js
# ---------------------------------------------------------------------------
def _app_js_source():
    with open(os.path.join(PROJECT_DIR, "app.js"), "r", encoding="utf-8") as f:
        return f.read()


class TestCStaticSinks(unittest.TestCase):
    def test_20_moment_feed_sink_uses_escapehtml(self):
        src = _app_js_source()
        self.assertIn(
            "data-emoji=\"' + escapeHtml(emoji) + '\">'",
            src,
            "moment feed reaction pill must escape the emoji attribute value",
        )
        self.assertNotIn(
            "data-emoji=\"' + emoji + '\">'",
            src,
            "raw emoji concatenation must be gone from the data-emoji attribute",
        )

    def test_21_moment_detail_sink_uses_escapehtml(self):
        src = _app_js_source()
        # Both identical pill construction sites (feed ~399, detail ~1890)
        # must escape the emoji label span.
        self.assertEqual(
            src.count("'<span>' + escapeHtml(emoji) + '</span>'"),
            2,
            "both moment reaction pill label sinks must use escapeHtml",
        )
        self.assertNotIn(
            "'<span>' + emoji + '</span>'",
            src,
            "raw emoji concatenation must be gone from the pill label spans",
        )

    def test_22_chat_reaction_sink_uses_escapehtml(self):
        src = _app_js_source()
        self.assertIn(
            "pillBtn.innerHTML = escapeHtml(em) + ",
            src,
            "chat reaction pill must escape the emoji interpolated into innerHTML",
        )
        self.assertNotIn(
            "pillBtn.innerHTML = em + ",
            src,
            "raw emoji concatenation must be gone from the chat reaction pill",
        )

    def test_23_escapehtml_implementation_unmodified(self):
        src = _app_js_source()
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
        self.assertIn(
            expected, src,
            "escapeHtml() must remain byte-for-byte unchanged",
        )


# ---------------------------------------------------------------------------
# Group D — regression / output checks
# ---------------------------------------------------------------------------
class TestDRegression(ReactionXssBase):
    def test_30_legitimate_values_byte_for_byte_via_api(self):
        for emoji in LEGIT_REACTIONS:
            status, body = self._request(
                "/api/react", token=TOKEN, method="POST",
                body={"postId": "post_xss", "emoji": emoji},
            )
            self.assertEqual(status, 200, "legitimate reaction %r must be accepted" % emoji)
            self.assertTrue(body.get("success"))
            self.assertEqual(
                body.get("realmojis", {}).get(emoji), 1,
                "tallies must round-trip the reaction byte-for-byte",
            )

    def test_31_legitimate_values_byte_for_byte_in_db(self):
        stored = self._stored_emojis("reactions", "WHERE post_id = ?", ("post_xss",))
        for emoji in LEGIT_REACTIONS:
            self.assertIn(
                emoji, stored,
                "stored reaction must equal the submitted value byte-for-byte",
            )

    def test_32_default_fire_emoji_still_accepted(self):
        status, body = self._request(
            "/api/react", token=TOKEN, method="POST", body={"postId": "post_xss"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertIn("🔥", body.get("realmojis", {}))

    def test_33_attacker_html_never_stored_anywhere(self):
        for payload in ATTACK_PAYLOADS + [OVERLENGTH_PAYLOAD]:
            self._request(
                "/api/react", token=TOKEN, method="POST",
                body={"postId": "post_xss", "emoji": payload},
            )
            self._request(
                "/api/chat/reactions", token=TOKEN, method="POST",
                body={"message_id": "msg_xss", "emoji": payload},
            )
        for payload in ATTACK_PAYLOADS + [OVERLENGTH_PAYLOAD]:
            self.assertNotIn(payload, self._stored_emojis("reactions"))
            self.assertNotIn(payload, self._stored_emojis("chat_reactions"))

    def test_34_rendering_templates_never_concatenate_raw_reaction_values(self):
        src = _app_js_source()
        # Reaction markup must only ever embed escaped emoji values.
        self.assertNotIn("data-emoji=\"' + emoji + '\">'", src)
        self.assertNotIn("'<span>' + emoji + '</span>'", src)
        self.assertNotIn("pillBtn.innerHTML = em + ", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
