#!/usr/bin/env python3
"""
Focused regression tests for B2-SEC-15 completion (inline-JS injection).

Completes the invariant: NO attacker-controlled value may appear inside an
inline JavaScript handler string using bare escapeHtml(). This suite uses
the ACTUAL handler template strings from app.js (with the real escapeHtml +
jsAttr extracted at test time) executed through a simulated browser pipeline
(attribute value -> HTML entity decode -> JS compile -> execute), plus real
server request-path tests for the new audio_url hardening.

Groups:
  A. audioUrl inline handler (playFeedAudio)
  B. friend name (openChatWithUser arg 2)
  C. friend handle (arg 3)
  D. friend avatarSrc (arg 4)
  E. moderation target_id (handleModerationAction, review/dismiss/hide)
  F. JSON.stringify(m) object-literal handler (openMomentDetail) —
     evidence-based verdict: escapeHtml(JSON.stringify(m)) is the CORRECT
     encoding for this sink (raw JS object-literal context, category E).
     jsAttr was tried per the mandate and behaviorally REJECTED: it escapes
     the structural double quotes of the object literal itself, producing
     'Invalid or unexpected token' (the mandate's own verification
     criterion — the runtime argument must reconstruct the same object
     semantics — fails). The original form is kept and proven safe.
  G. previously-fixed B2-SEC-15 conversions remain in place
  H. cache-bust (app.js?v=5.6.4, no stale versions)
  I. legitimate values round-trip byte-for-byte
  J. server-side audio_url hardening (defense-in-depth, real request path)

Test harness rule: environment is configured BEFORE importing server.
"""

import os

os.environ["DATABASE_URL"] = ""
os.environ["ENVIRONMENT"] = "development"

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server
from server import KandidHandler

NODE_AVAILABLE = shutil.which("node") is not None

TOKEN = "test_token_b15c"

HOSTILE_JS_PAYLOADS = [
    "');alert(1)//",
    "x')-alert(1)-('y",
    "' onmouseover='alert(1)",
    "\\');alert(1)//",
    "');\nalert(1)//",
]

LEGIT = {
    "name": "O'Brien's Cafe & Grill",
    "handle": "o'brien_handle",
    "avatar": "https://res.cloudinary.com/kandid/image/upload/av.png",
    "audio": "https://res.cloudinary.com/kandid/video/upload/aud_x.webm",
    "audio_uploads": "/uploads/ambient_deadbeef.webm",
    "target_id": "post_abc123def456",
}


def _read(path):
    with open(os.path.join(PROJECT_DIR, path), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Node harness: extracts the REAL escapeHtml + jsAttr from app.js and builds
# the ACTUAL handler template strings used by the fixed lines, then runs the
# simulated browser pipeline (entity decode -> compile -> execute).
# ---------------------------------------------------------------------------
_NODE_HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const escSrc = src.match(/function escapeHtml\(str\) \{[\s\S]*?\n\}/);
const jsaSrc = src.match(/function jsAttr\(value\) \{[\s\S]*?\n\}/);
if (!escSrc || !jsaSrc) { console.log(JSON.stringify({fatal: 'functions not found'})); process.exit(0); }
eval(escSrc[0]);
eval(jsaSrc[0]);

function entityDecode(s) {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&amp;/g, '&');
}

// Extract the value of the first onclick="..." (or generic on*=) attribute.
function firstHandler(html) {
  const m = html.match(/on(?:click|change|input|load|error|dblclick|mousedown|mouseup|keydown|keyup)="([^"]*)"/);
  return m ? m[1] : null;
}

function runHandler(attr, fakeName) {
  const result = { executed: false, called: false, args: [], error: null };
  try {
    // Browsers always provide `event` inside inline handlers; mirror that.
    const fn = new Function(fakeName, 'event', 'alert', entityDecode(attr) + ';');
    fn(function () { result.called = true; result.args = Array.prototype.slice.call(arguments); },
       { stopPropagation: function () {} },
       function () { result.executed = true; });
  } catch (e) {
    result.error = String(e && e.message || e);
  }
  return result;
}

// ---- Actual app.js handler templates (mirroring the fixed lines) ----
function buildAudioAttr(audioUrl) {
  return '<button class="x" onclick="event.stopPropagation(); playFeedAudio(\'' + jsAttr(audioUrl) + '\')">PLAY</button>';
}
function buildFriendAttr(id, name, handle, avatarSrc) {
  return '<button class="x" onclick="openChatWithUser(\'' + id + '\', \'' + jsAttr(name) + '\', \'' + jsAttr(handle) + '\', \'' + jsAttr(avatarSrc) + '\')">MSG</button>';
}
function buildModerationAttr(rid, action, ttype, tid, commId) {
  return '<button class="x" onclick="handleModerationAction(\'' + rid + '\', \'' + action + '\', \'' + jsAttr(ttype) + '\', \'' + jsAttr(tid) + '\', \'' + commId + '\')">Review</button>';
}
function buildJsonAttr(m) {
  // Category E (safe-by-construction JSON object literal): the argument is
  // NOT inside a quoted JS string — it is raw JS object-literal source.
  // JSON.stringify provides the JS-string escaping of member values and
  // escapeHtml the HTML-attribute context. (jsAttr was TRIED here and
  // behaviorally rejected: it escapes the structural double quotes of the
  // object literal itself, producing 'Invalid or unexpected token'.)
  return '<div class="x" onclick="openMomentDetail(' + escapeHtml(JSON.stringify(m)) + ')"></div>';
}
// Actual cluster badge template (post-fix form) — mirrors app.js 776/1946.
function buildClusterAttr(m) {
  return '<button class="x" onclick="event.stopPropagation(); openMomentClusterModal(\'' + jsAttr(m.cluster_id || '') + '\', \'' + m.id + '\')">CLUSTER</button>';
}

const cases = JSON.parse(process.argv[3]);
const out = { results: [] };

for (const c of cases) {
  let html, fake;
  if (c.kind === 'audio') {
    html = buildAudioAttr(c.value);
    fake = 'playFeedAudio';
  } else if (c.kind === 'friend') {
    html = buildFriendAttr('f_deadbeef01', c.value, c.value2 || 'plain_handle', c.value3 || '');
    fake = 'openChatWithUser';
  } else if (c.kind === 'friend_handle') {
    html = buildFriendAttr('f_deadbeef01', 'Plain Name', c.value, 'https://res.cloudinary.com/kandid/image/upload/av.png');
    fake = 'openChatWithUser';
  } else if (c.kind === 'friend_avatar') {
    html = buildFriendAttr('f_deadbeef01', 'Plain Name', 'plain_handle', c.value);
    fake = 'openChatWithUser';
  } else if (c.kind === 'moderation') {
    html = buildModerationAttr('rep_abc123', c.action || 'review', 'moment', c.value, 'comm_123abc');
    fake = 'handleModerationAction';
  } else if (c.kind === 'json') {
    html = buildJsonAttr({ id: 'post_x', caption: c.value, main_img: '/uploads/a.png' });
    fake = 'openMomentDetail';
  } else if (c.kind === 'cluster') {
    html = buildClusterAttr({ cluster_id: c.value, id: 'post_deadbeef' });
    fake = 'openMomentClusterModal';
  } else if (c.kind === 'cluster_legit') {
    html = buildClusterAttr({ cluster_id: c.value, id: 'post_deadbeef' });
    fake = 'openMomentClusterModal';
  }
  const r = runHandler(firstHandler(html), fake);
  out.results.push({
    kind: c.kind, payload: c.value,
    executed: r.executed, handlerError: r.error !== null, error: r.error,
    called: r.called, args: r.args
  });
}
console.log(JSON.stringify(out));
"""


def _run_node(cases):
    tmpdir = tempfile.mkdtemp(prefix="kandid_b15c_")
    try:
        harness_path = os.path.join(tmpdir, "harness.js")
        with open(harness_path, "w", encoding="utf-8") as f:
            f.write(_NODE_HARNESS)
        proc = subprocess.run(
            ["node", harness_path, os.path.join(PROJECT_DIR, "app.js"), json.dumps(cases)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise AssertionError("node harness failed: %s" % proc.stderr[:500])
        return json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class ServerBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="kandid_b15c_srv_")
        cls._orig_db = server.DB_FILE
        cls._orig_url = server.DATABASE_URL
        server.DATABASE_URL = ""
        server.DB_FILE = os.path.join(cls._tmpdir, "kandid_b15c.db")
        server.init_db()
        conn = server.get_db()
        cursor = conn.cursor()
        now_iso = datetime.now().isoformat()
        future_iso = (datetime.now() + timedelta(days=1)).isoformat()
        cursor.execute(
            "INSERT INTO users (id, email, handle, name, password_hash, salt) VALUES (?, ?, ?, ?, ?, ?)",
            ("u_b15c", "b15c@example.test", "b15c_handle", "B15C User", "test_hash", "test_salt"),
        )
        cursor.execute(
            "INSERT INTO sessions (id, token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            ("sess_b15c", TOKEN, "u_b15c", future_iso, now_iso),
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
        status_code = int(headers_part.splitlines()[0].split()[1])
        try:
            parsed = json.loads(body_part)
        except Exception:
            parsed = body_part
        return status_code, parsed


# ---------------------------------------------------------------------------
# Groups A–F + I — behavioral proofs through the real handler templates
# ---------------------------------------------------------------------------
@unittest.skipUnless(NODE_AVAILABLE, "node is required for the behavioral harness")
class TestBehavioralHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = []
        for p in HOSTILE_JS_PAYLOADS:
            cases.append({"kind": "audio", "value": p})
            cases.append({"kind": "friend", "value": p})
            cases.append({"kind": "friend_handle", "value": p})
            cases.append({"kind": "friend_avatar", "value": p})
            cases.append({"kind": "moderation", "value": p})
            cases.append({"kind": "json", "value": p})
            cases.append({"kind": "cluster", "value": p})
        cls.results = _run_node(cases)["results"]
        cls.by_kind = {}
        for r in cls.results:
            cls.by_kind.setdefault(r["kind"], []).append(r)

    def _assert_inert(self, kind):
        for r in self.by_kind[kind]:
            self.assertFalse(r["executed"], "%s payload %r executed attacker JS" % (kind, r["payload"]))
            self.assertFalse(r["handlerError"], "%s payload %r corrupted the handler (%r)" % (kind, r["payload"], r["error"]))

    def test_01_audio_handler_inert(self):
        self._assert_inert("audio")

    def test_02_friend_name_handler_inert(self):
        self._assert_inert("friend")

    def test_03_friend_handle_handler_inert(self):
        self._assert_inert("friend_handle")

    def test_04_friend_avatar_handler_inert(self):
        self._assert_inert("friend_avatar")

    def test_05_moderation_target_id_handler_inert(self):
        self._assert_inert("moderation")

    def test_06_json_object_literal_handler_inert(self):
        self._assert_inert("json")

    def test_06b_cluster_id_handler_inert(self):
        # The final raw sink: (m.cluster_id || '') is now jsAttr-wrapped.
        self._assert_inert("cluster")

    def test_06c_cluster_id_poc_payload_specifically(self):
        # Arena's exact PoC shape, run through the REAL app.js jsAttr + the
        # ACTUAL badge template.
        r = _run_node([{"kind": "cluster", "value": "');globalThis.__OWNED_CLUSTER=true;//"}])["results"][0]
        self.assertFalse(r["executed"], "cluster_id PoC payload executed attacker JS")
        self.assertFalse(r["handlerError"])

    def test_06d_normal_cluster_ids_still_work(self):
        for cid in ("cls_ab12cd34ef56", "", "cls-X_9"):
            r = _run_node([{"kind": "cluster_legit", "value": cid}])["results"][0]
            self.assertTrue(r["called"], "cluster id %r must still reach openMomentClusterModal" % cid)
            self.assertFalse(r["executed"])
            self.assertFalse(r["handlerError"])
            self.assertEqual(r["args"][0], cid)
            self.assertEqual(r["args"][1], "post_deadbeef")  # m.id untouched

    def test_07_friend_handler_preserves_server_id_and_safe_values(self):
        # f.id must remain passed through raw; name/handle/avatar round-trip.
        cases = [{"kind": "friend", "value": LEGIT["name"],
                  "value2": LEGIT["handle"], "value3": LEGIT["avatar"]}]
        r = _run_node(cases)["results"][0]
        self.assertTrue(r["called"])
        self.assertEqual(r["args"][0], "f_deadbeef01")
        self.assertEqual(r["args"][1], LEGIT["name"])
        self.assertEqual(r["args"][2], LEGIT["handle"])
        self.assertEqual(r["args"][3], LEGIT["avatar"])

    def test_08_audio_handler_legit_values_round_trip(self):
        for audio in (LEGIT["audio"], LEGIT["audio_uploads"]):
            r = _run_node([{"kind": "audio", "value": audio}])["results"][0]
            self.assertTrue(r["called"])
            self.assertEqual(r["args"][0], audio)

    def test_09_moderation_legit_target_id_round_trip(self):
        r = _run_node([{"kind": "moderation", "value": LEGIT["target_id"]}])["results"][0]
        self.assertTrue(r["called"])
        self.assertEqual(r["args"][3], LEGIT["target_id"])
        self.assertEqual(r["args"][0], "rep_abc123")
        self.assertEqual(r["args"][2], "moment")
        self.assertEqual(r["args"][4], "comm_123abc")

    def test_10_json_object_literal_preserves_semantics(self):
        # Category E proof: with escapeHtml(JSON.stringify(m)) the decoded
        # argument reconstructs the ORIGINAL object (JSON.stringify already
        # JS-escapes member strings; escapeHtml only handles the attribute
        # context; no quoting conflict exists in the raw object-literal).
        tricky = [
            "Real caption with 'quote' and \"double\" quotes",
            "Back\\slash and </script> inside caption",
            "Unicode café ☕ — ünïcödé",
            "Line\nbreak\ttab",
            "');alert(1)// (inert as caption text)",
            '</script><img src=x onerror=alert(1)>',
        ]
        cases = [{"kind": "json", "value": t} for t in tricky]
        results = _run_node(cases)["results"]
        for expected, r in zip(tricky, results):
            self.assertTrue(r["called"], "json case %r must still call openMomentDetail" % expected)
            self.assertFalse(r["executed"], "json case %r executed attacker JS" % expected)
            self.assertFalse(r["handlerError"], "json case %r corrupted the handler" % expected)
            self.assertIsInstance(r["args"][0], dict)
            self.assertEqual(r["args"][0]["caption"], expected)
            self.assertEqual(r["args"][0]["main_img"], "/uploads/a.png")
            self.assertEqual(r["args"][0]["id"], "post_x")


# ---------------------------------------------------------------------------
# Group G — static pins: conversions in place + classified remainder
# ---------------------------------------------------------------------------
class TestStaticConversions(unittest.TestCase):
    def test_20_new_conversions_present(self):
        src = _read("app.js")
        self.assertEqual(src.count("jsAttr(audioUrl)"), 1)
        self.assertEqual(src.count("jsAttr(r.target_id)"), 3)
        # JSON object-literal sink: escapeHtml(JSON.stringify(m)) is the
        # CORRECT encoding (category E) — see buildJsonAttr comment and
        # test_10_json_object_literal_preserves_semantics.
        self.assertEqual(src.count("escapeHtml(JSON.stringify(m))"), 1)
        self.assertNotIn("jsAttr(JSON.stringify(m))", src)
        # friend handler: locate the openChatWithUser onclick line and verify
        # the three conversions (f.id intentionally stays raw).
        line = next(l for l in src.splitlines() if "openChatWithUser(" in l and "f.id" in l and "onclick" in l)
        self.assertIn("jsAttr(name)", line)
        self.assertIn("jsAttr(handle)", line)
        self.assertIn("jsAttr(avatarSrc)", line)
        self.assertNotIn("escapeHtml(name)", line)
        self.assertNotIn("escapeHtml(handle)", line)
        self.assertNotIn("escapeHtml(avatarSrc)", line)
        self.assertIn("+ f.id +", line)

    def test_21_full_expression_sweep_no_raw_attacker_interpolation(self):
        # WHOLE-EXPRESSION sweep (replaces the escapeHtml-only scan, which
        # missed raw interpolations like (m.cluster_id || '')). For every
        # inline on*= handler attribute, tokenize the interpolation joints
        # (" + ") and require each interpolated expression to be jsAttr(...)
        # or an explicitly allowlisted safe value.
        import re
        src = _read("app.js")
        ON_ATTR = re.compile(r"\bon[a-z]+=\"([^\"]*)\"")
        # Category B/D allowlist — server-generated identifiers whose charset
        # is guaranteed server-side, plus deterministic UI values.
        RAW_SAFE_IDS = {
            "m.id", "f.id", "u.id", "r.id", "c.id", "curCommId", "commId",
            "(m.id || 'mem_1')", "circle", "k",
            # circle: only ever assigned UI literals (foryou/nearby/community/
            # campus) via selectSubTab/static buttons; k: server timestamp
            # substring (YYYY-MM keys) used by the memories month filter.
        }
        # escapeHtml()-wrapped SERVER IDs (safe charset; escapeHtml on top is
        # harmless defense-in-depth, not JS-string encoding of user data).
        ESCAPED_ID_INNER = {"r.id", "commId", "u.id", "curCommId", "c.id"}
        # escapeHtml()-wrapped expressions that are NOT used as JS-string
        # encoding: HTML-attribute/text contexts sharing the handler line,
        # the server-validated enum, and the category-E object literal.
        ESCAPED_SAFE_INNER = {
            "c.name",          # radio input value="..." (~3097)
            "avatarSrc",       # <img src> on the onerror line (~9423)
            "locBanner",       # visible span text (~445)
            "m.media_url",     # img src + data-media-url attribute
            "JSON.stringify(m)",  # category E: raw object-literal context
            "r.target_type",   # server-validated enum at report creation
        }
        problems = []
        raw_count = 0
        checked = 0
        for lineno, line in enumerate(src.splitlines(), 1):
            if "' +" not in line:
                continue
            for attr in ON_ATTR.findall(line):
                # Interpolation joints are always written " + EXPR + " in this
                # codebase; split and inspect odd indices (the expressions).
                parts = attr.split(" + ")
                for idx in range(1, len(parts), 2):
                    expr = parts[idx].strip()
                    checked += 1
                    if expr.startswith("jsAttr("):
                        continue
                    if expr in RAW_SAFE_IDS:
                        continue
                    if expr.startswith("escapeHtml(") and expr.endswith(")"):
                        inner = expr[len("escapeHtml("):-1]
                        if inner in ESCAPED_SAFE_INNER or inner in ESCAPED_ID_INNER:
                            continue
                    problems.append((lineno, expr))
                    raw_count += 1
        self.assertEqual(
            problems, [],
            "attacker-controllable or unclassified interpolation inside inline JS: %r" % problems,
        )
        self.assertEqual(raw_count, 0)
        # Sanity: the sweep must actually have inspected the known sinks.
        self.assertGreaterEqual(checked, 25)

    def test_21b_cluster_id_specifically_jsattr_wrapped(self):
        src = _read("app.js")
        self.assertEqual(src.count("jsAttr(m.cluster_id || '')"), 2)
        self.assertNotIn("+ (m.cluster_id || '') +", src)

    def test_21c_escapehtml_in_handlers_classified_safe_only(self):
        # Complementary invariant to test_21: the only escapeHtml calls on
        # handler lines are the classified-safe set (IDs/enum/dataset/
        # HTML-context/object-literal).
        src = _read("app.js")
        import re
        handler_lines = [l for l in src.splitlines() if re.search(r"on(click|change|input|load|error|dblclick|mousedown|mouseup|keydown|keyup)=", l) and "' +" in l]
        found = []
        for l in handler_lines:
            found.extend(re.findall(r"escapeHtml\(([^)]+)\)", l))
        allowed = {
            "r.target_type", "r.id", "commId", "u.id", "curCommId", "c.id",
            "m.media_url", "c.name", "avatarSrc", "locBanner",
            "JSON.stringify(m",  # category E: raw object-literal context
        }
        unexpected = [f for f in found if f not in allowed]
        self.assertEqual(unexpected, [], "unclassified escapeHtml inside handler lines: %r" % unexpected)
        for must in ("jsAttr(r.target_id)", "jsAttr(audioUrl)", "jsAttr(m.cluster_id || '')"):
            self.assertIn(must, src)
        self.assertEqual(src.count("jsAttr(r.target_id)"), 3)

    def test_22_escapehtml_and_jsattr_implementations_untouched(self):
        src = _read("app.js")
        self.assertIn(
            "function escapeHtml(str) {\n  if (!str) return '';\n  return String(str)\n    .replace(/&/g, '&amp;')\n    .replace(/</g, '&lt;')\n    .replace(/>/g, '&gt;')\n    .replace(/\"/g, '&quot;')\n    .replace(/'/g, '&#039;');\n}",
            src,
        )
        self.assertEqual(src.count("function jsAttr("), 1)


# ---------------------------------------------------------------------------
# Group H — cache-bust
# ---------------------------------------------------------------------------
class TestCacheBust(unittest.TestCase):
    def test_30_index_references_app_js_5_6_5_only(self):
        src = _read("index.html")
        self.assertIn("app.js?v=5.6.5", src)
        for stale in ("5.6.4", "5.6.3", "5.6.2", "5.6.1", "5.6.0"):
            self.assertNotIn("app.js?v=" + stale, src)


# ---------------------------------------------------------------------------
# Group J — server-side audio_url hardening (real request path)
# ---------------------------------------------------------------------------
class TestServerAudioHardening(ServerBase):
    def _capture(self, body):
        body.setdefault("caption", "b15c audio test")
        return self._request("/api/moments/capture", token=TOKEN, method="POST", body=body)

    def test_40_hostile_raw_audio_schemes_rejected(self):
        for payload in ("javascript:alert(1)", "vbscript:alert(1)", "data:text/html,<script>x</script>", "//res.cloudinary.com/x.webm"):
            status, _ = self._capture({"audioData": payload})
            self.assertEqual(status, 400, "raw audio %r must be rejected" % payload)

    def test_41_hostile_resolved_audio_urls_rejected(self):
        for payload in ('http://x" onerror="alert(1)', "https://evil.example.com/a.webm", "javascript:alert(1)"):
            status, _ = self._capture({"audioData": payload, "audio_data": None})
            self.assertEqual(status, 400, "resolved audio %r must be rejected" % payload)

    def test_42_legitimate_uploads_audio_round_trips(self):
        status, body = self._capture({"audioData": "/uploads/ambient_preset.webm"})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["audio_url"], "/uploads/ambient_preset.webm")

    def test_43_legitimate_cloudinary_audio_round_trips(self):
        status, body = self._capture({"audioData": LEGIT["audio"]})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["audio_url"], LEGIT["audio"])

    def test_44_legitimate_base64_audio_capture_still_works(self):
        # data:audio must keep flowing through save_base64_audio's dev
        # fallback into local /uploads storage.
        status, body = self._capture({"audioData": "data:audio/webm;base64,SkFORElE"})
        self.assertEqual(status, 201)
        self.assertTrue(
            (body["post"]["audio_url"] or "").startswith("/uploads/"),
            "base64 audio capture must persist locally (got %r)" % body["post"]["audio_url"],
        )

    def test_45_no_post_row_for_hostile_audio(self):
        conn = server.get_db()
        conn.execute("DELETE FROM posts")
        conn.commit()
        conn.close()
        for payload in ("javascript:alert(1)", "https://evil.example.com/a.webm", "//res.cloudinary.com/x.webm"):
            self._capture({"audioData": payload})
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM posts")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0, "hostile audio must prevent the post row")

    def test_46_existing_image_validation_untouched(self):
        # B2-SEC-16 image behavior must remain exactly as shipped.
        status, _ = self._capture({"mainImg": "javascript:alert(1)"})
        self.assertEqual(status, 400)
        status, body = self._capture({"mainImg": "/uploads/main_ok.png"})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["main_img"], "/uploads/main_ok.png")

    # ---- cluster_id server-side hardening (final B2-SEC-15 blocker) ----

    def _seed_cluster(self, cluster_id="cls_ab12cd34ef56"):
        # Seed a real originating post first (FK target), then the cluster.
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO posts (id, user_id, author_name, author_handle, main_img, pip_img) VALUES (?, ?, ?, ?, ?, ?)",
            ("post_seedcluster", "u_b15c", "Seed Author", "seed_handle", "a.png", "b.png"),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO moment_clusters (id, originator_moment_id, originator_user_id, status) VALUES (?, ?, ?, 'active')",
            (cluster_id, "post_seedcluster", "u_b15c"),
        )
        conn.commit()
        conn.close()

    def _post_rows(self):
        conn = server.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT cluster_id FROM posts")
        rows = [r[0] for r in cursor.fetchall()]
        conn.close()
        return rows

    def test_47_hostile_cluster_id_format_rejected_400(self):
        for payload in (
            "');globalThis.__OWNED_CLUSTER=true;//",
            "abc'def",
            'abc"def',
            "a<b>c",
            "back\\\\slash",
            "sp ace",
            "semi;colon",
        ):
            status, _ = self._capture({"cluster_id": payload})
            self.assertEqual(status, 400, "hostile cluster_id %r must be rejected" % payload)

    def test_48_hostile_cluster_id_never_persisted(self):
        conn = server.get_db()
        conn.execute("DELETE FROM posts")
        conn.commit()
        conn.close()
        for payload in ("');globalThis.__OWNED_CLUSTER=true;//", "x'y", 'a"b', "a<b"):
            self._capture({"cluster_id": payload})
        for stored in self._post_rows():
            self.assertNotIn("__OWNED_CLUSTER", stored or "")
            self.assertNotIn("'", stored or "")
            self.assertNotIn('"', stored or "")

    def test_49_unknown_but_wellformed_cluster_id_degrades_to_empty(self):
        status, body = self._capture({"cluster_id": "cls_doesnotexist99"})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["cluster_id"], "", "unknown cluster id must not be persisted")

    def test_50_real_active_cluster_id_round_trips(self):
        self._seed_cluster("cls_real12345678")
        status, body = self._capture({"cluster_id": "cls_real12345678"})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["cluster_id"], "cls_real12345678")

    def test_51_empty_and_missing_cluster_id_still_allowed(self):
        status, body = self._capture({"cluster_id": ""})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["cluster_id"], "")
        status, body = self._capture({})
        self.assertEqual(status, 201)
        self.assertEqual(body["post"]["cluster_id"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
