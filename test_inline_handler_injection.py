#!/usr/bin/env python3
"""
Focused tests for KINDID Batch-2 B2-SEC-15 (inline handler string injection).

Root cause being closed: the legacy pattern
    escapeHtml(value).replace(/'/g, "\\'")
was a silent no-op for apostrophes (escapeHtml had already converted ' to
&#039;), so the JS-level replace never fired — yet the browser entity-decodes
an attribute value BEFORE compiling the inline handler, re-materializing a
raw apostrophe and breaking out of the JavaScript string.

Groups:
  A. The broken pattern is completely gone from app.js (zero matches in the
     inline-JS-string context it exploited).
  B. jsAttr() exists and applies JS escaping BEFORE HTML escaping.
  C. Hostile payloads are safely encoded (node-executed behavioral check
     against the REAL app.js source).
  D. Entity-decoding attack is neutralized: a generated inline handler
     containing an attacker string cannot produce executable JavaScript
     after HTML-attribute entity decoding.
  E. All 10 confirmed interpolations now use jsAttr().
  F. Legitimate unicode/normal community and place names remain functional
     (byte-for-byte round-trip through the simulated browser pipeline).
  G. ID-only inline handlers and escapeHtml() itself remain unchanged.

Documented static-audit exclusion (not a vulnerability, deliberately left):
  app.js line ~3097 contains escapeHtml(c.name).replace(/"/g, '&quot;')
  feeding a radio input's value="..." HTML attribute — an HTML-context (not
  JS-string-context) sink where escapeHtml alone is already correct and the
  chained replace is an idempotent no-op. It is NOT the vulnerable
  replace(/'/g) pattern and is untouched per the review mandate.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_AVAILABLE = shutil.which("node") is not None

HOSTILE_PAYLOADS = [
    "');alert(1)//",
    "x')-alert(1)-('y",
    "\\",
    "'",
    '"',
    "<svg onload=alert(1)>",
]

LEGIT_NAMES = [
    "O'Brien's Cafe & Grill",
    'The <Bold> "Quote" Place',
    "Back\\slash Community",
    "Café ☕ Unicode Ünïcödé",
    "Ampersand & Sons 'N Daughters",
    "North City University",
]


def _app_js_source():
    with open(os.path.join(PROJECT_DIR, "app.js"), "r", encoding="utf-8") as f:
        return f.read()


# Node harness: extracts the REAL escapeHtml + jsAttr from app.js, builds an
# inline-handler attribute for each payload, simulates the browser pipeline
# (attribute value -> entity decode -> JS compile -> execute) and reports
# results as JSON.
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

function buildOldAttr(raw) {
  return "openCampusPage('" + escapeHtml(raw).replace(/'/g, "\\'") + "')";
}
function buildNewAttr(raw) {
  return "openCampusPage('" + jsAttr(raw) + "')";
}

function runHandler(attr) {
  const result = { executed: false, called: false, arg: undefined, error: null };
  try {
    const fn = new Function('openCampusPage', 'alert', entityDecode(attr) + ';');
    fn(
      function fakeOpenCampusPage(arg) { result.called = true; result.arg = arg; },
      function fakeAlert() { result.executed = true; }
    );
  } catch (e) {
    result.error = String(e && e.message || e);
  }
  return result;
}

const payloads = JSON.parse(process.argv[3]);
const legit = JSON.parse(process.argv[4]);
const out = { hostile: [], legit: [] };

for (const p of payloads) {
  const newR = runHandler(buildNewAttr(p));
  out.hostile.push({
    payload: p,
    executed: newR.executed,
    handlerError: newR.error !== null,
    error: newR.error
  });
}
for (const name of legit) {
  const r = runHandler(buildNewAttr(name));
  out.legit.push({
    name: name,
    roundTrip: r.called && !r.executed && !r.error && r.arg === name,
    arg: r.arg,
    handlerError: r.error !== null
  });
}
console.log(JSON.stringify(out));
"""


def _run_node_harness(payloads, legit_names):
    tmpdir = tempfile.mkdtemp(prefix="kandid_b2sec15_")
    try:
        harness_path = os.path.join(tmpdir, "harness.js")
        with open(harness_path, "w", encoding="utf-8") as f:
            f.write(_NODE_HARNESS)
        proc = subprocess.run(
            ["node", harness_path,
             os.path.join(PROJECT_DIR, "app.js"),
             json.dumps(payloads), json.dumps(legit_names)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise AssertionError("node harness failed: %s" % proc.stderr[:500])
        return json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Group A — the broken pattern is completely gone
# ---------------------------------------------------------------------------
class TestABrokenPatternGone(unittest.TestCase):
    def test_01_no_legacy_noop_pattern_anywhere(self):
        src = _app_js_source()
        # The exact legacy construction (HTML-escape output fed into a
        # JS-level apostrophe backslash-replace) must not exist anywhere,
        # in any quote style.
        self.assertIsNone(
            re.search(r"escapeHtml\([^()]*\)\s*\.\s*replace\(\s*/'/g\s*,\s*(['\"])\\\\\\\1", src),
            "the no-op HTML-then-JS apostrophe replace pattern must be gone",
        )

    def test_02_no_escapehtml_result_feeds_apostrophe_js_replace(self):
        src = _app_js_source()
        matches = re.findall(r"escapeHtml\([^()]*\)\s*\.\s*replace\(\s*/'/g", src)
        self.assertEqual(
            matches, [],
            "no escapeHtml(...) result may be re-replaced for apostrophes (found %d)" % len(matches),
        )

    def test_03_only_expected_apostrophe_replaces_remain(self):
        src = _app_js_source()
        # Exactly two replace(/'/g may remain:
        #   1. inside escapeHtml() — the HTML entity substitution ('&#039;')
        #   2. inside jsAttr() — the JS-level backslash-escape
        # (A third historic match lived in a comment and was reworded away.)
        count = src.count("replace(/'/g")
        self.assertEqual(count, 2, "expected exactly 2 apostrophe replaces (escapeHtml + jsAttr), found %d" % count)
        self.assertIn(".replace(/'/g, '&#039;');", src)  # escapeHtml-internal (HTML context)
        jsa_start = src.find("function jsAttr(value) {")
        jsa_end = src.find("\n}", jsa_start)
        self.assertIn("replace(/'/g", src[jsa_start:jsa_end])  # jsAttr-internal (JS context)


# ---------------------------------------------------------------------------
# Group B — jsAttr() exists with correct ordering
# ---------------------------------------------------------------------------
class TestBJsAttrHelper(unittest.TestCase):
    def _jsattr_body(self):
        src = _app_js_source()
        start = src.find("function jsAttr(value) {")
        self.assertNotEqual(start, -1, "jsAttr() must exist in app.js")
        end = src.find("\n}", start)
        return src[start:end]

    def test_10_jsattr_exists_single_definition(self):
        src = _app_js_source()
        self.assertEqual(src.count("function jsAttr("), 1)

    def test_11_ordering_js_escape_chain_is_the_argument_of_escapehtml(self):
        # Structural proof of "JS escape -> HTML escape": the JS-string
        # escaping chain (backslash first) must be INSIDE the escapeHtml(...)
        # call, i.e. escapeHtml receives already-JS-escaped text.
        src = _app_js_source()
        self.assertIsNotNone(
            re.search(
                r"return\s+escapeHtml\(\s*String\(value\)\s*\.replace\(/\\\\/g",
                src,
                re.S,
            ),
            "jsAttr must pass JS-escaped text (backslash-escaped first) INTO escapeHtml",
        )

    def test_12_covers_js_string_terminators(self):
        body = self._jsattr_body()
        for marker in (".replace(/\\\\/g", ".replace(/'/g", '.replace(/"/g',
                       ".replace(/\\r/g", ".replace(/\\n/g",
                       ".replace(/\\u2028/g", ".replace(/\\u2029/g"):
            self.assertIn(marker, body, "jsAttr must handle %s" % marker)

    def test_13_escaphtml_implementation_untouched(self):
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
        self.assertIn(expected, src, "escapeHtml() must remain byte-for-byte unchanged")


# ---------------------------------------------------------------------------
# Groups C + D — behavioral proof via node (uses the REAL app.js source)
# ---------------------------------------------------------------------------
@unittest.skipUnless(NODE_AVAILABLE, "node is required for the behavioral harness")
class TestCHostilePayloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = _run_node_harness(HOSTILE_PAYLOADS, LEGIT_NAMES)

    def test_20_no_payload_executes_javascript(self):
        for r in self.results["hostile"]:
            self.assertFalse(
                r["executed"],
                "payload %r must never execute attacker JavaScript (old pattern executed alert(1) for break-out payloads)" % r["payload"],
            )

    def test_21_no_payload_breaks_the_handler(self):
        for r in self.results["hostile"]:
            self.assertFalse(
                r["handlerError"],
                "payload %r must not corrupt the inline handler" % r["payload"],
            )

    def test_22_entity_decoded_handler_cannot_produce_executable_js(self):
        # Group D: even after simulating the browser's entity decoding of the
        # attribute value, compiling and running the handler must neither
        # execute attacker code nor raise — the payload stays an inert string.
        for r in self.results["hostile"]:
            self.assertFalse(
                r["executed"] or r["handlerError"],
                "payload %r became active after entity decoding" % r["payload"],
            )


@unittest.skipUnless(NODE_AVAILABLE, "node is required for the behavioral harness")
class TestFLegitNamesRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = _run_node_harness(HOSTILE_PAYLOADS, LEGIT_NAMES)

    def test_30_legitimate_names_round_trip_byte_for_byte(self):
        for r in self.results["legit"]:
            self.assertTrue(
                r["roundTrip"],
                "legitimate name %r must survive the inline-handler pipeline unchanged" % r["name"],
            )

    def test_31_visible_label_values_not_altered_by_fix(self):
        # The fix changes only the handler-argument encoding; the *visible*
        # text of the affected elements keeps its existing escapeHtml().
        src = _app_js_source()
        self.assertIn("escapeHtml(locBanner)", src)  # 421 visible label
        self.assertIn("escapeHtml(c.name)", src)     # visible labels elsewhere


# ---------------------------------------------------------------------------
# Group E — all 10 confirmed interpolations use jsAttr()
# ---------------------------------------------------------------------------
class TestEAllTenSitesUseJsAttr(unittest.TestCase):
    EXPECTED_USAGES = [
        ("jsAttr(commTarget)", 3),      # 421 / 786 / 1950
        ("jsAttr(c.name)", 3),          # 881 / 1463 / 6131
        ("jsAttr(curCommName)", 1),     # 1182
        ("jsAttr(it.name)", 1),         # 5716
        ("jsAttr(s.name)", 1),          # 7449
        ("jsAttr(c.city || '')", 1),    # 6131 (second interpolation)
    ]

    def test_40_exact_usage_counts(self):
        src = _app_js_source()
        total = 0
        for fragment, expected in self.EXPECTED_USAGES:
            actual = src.count(fragment)
            total += actual
            self.assertEqual(actual, expected, "expected %d occurrence(s) of %s" % (expected, fragment))
        self.assertEqual(total, 10, "exactly 10 interpolations must be converted")

    def test_41_no_user_string_handler_still_uses_the_vulnerable_js_context_pattern(self):
        # The VULNERABLE pattern is: escapeHtml(X) followed by a JS-level
        # apostrophe replace feeding an inline handler string. Its absence is
        # already proven by Group A; here we additionally pin that the exact
        # expressions converted in this commit have not regressed.
        src = _app_js_source()
        for fragment, _ in self.EXPECTED_USAGES:
            expr = fragment[len("jsAttr("):-1]
            self.assertIsNone(
                re.search(r"escapeHtml\(" + re.escape(expr) + r"\)\s*\.\s*replace\(\s*/'/g", src),
                "%s must not fall back to the legacy pattern" % expr,
            )

    def test_42_documented_benign_html_context_pattern_unchanged(self):
        # Static-audit exclusion (see module docstring): the radio-input
        # value="..." at ~3097 chains .replace(/"/g, '&quot;') in an HTML
        # attribute context — not the JS-string-context finding. It must
        # remain exactly as-is.
        src = _app_js_source()
        self.assertIn(
            """escapeHtml(c.name).replace(/"/g, '&quot;')""",
            src,
            "the documented benign HTML-attribute value pattern at ~3097 must remain unchanged",
        )
        # ...and it must NOT use the vulnerable apostrophe replace.
        self.assertNotIn(
            """escapeHtml(c.name).replace(/'/g""",
            src,
            "the ~3097 pattern must not be the vulnerable apostrophe variant",
        )


# ---------------------------------------------------------------------------
# Group G — ID-only handlers and other guarantees stay untouched
# ---------------------------------------------------------------------------
class TestGIdOnlyHandlersUnchanged(unittest.TestCase):
    UNTOUCHED_MARKERS = [
        # moderation actions: server-generated ids/types (3 buttons each)
        ("handleModerationAction(\\'' + escapeHtml(r.id)", 3),
        ("escapeHtml(r.target_type)", 4),
        ("escapeHtml(r.target_id)", 3),
        ("escapeHtml(commId)", 3),
        # collective memories: server-generated id with static fallback
        ("openCollectiveMemoryPage(\\'' + (m.id || 'mem_1')", 1),
        # unblock: server-generated user id
        ("unblockUser(\\'' + escapeHtml(u.id)", 1),
        # selectCampus id argument remains the existing escapeHtml(c.id)
        ("selectCampus(\\'' + escapeHtml(c.id)", 1),
        # openCommunityMomentCapture id argument remains escapeHtml(curCommId)
        ("openCommunityMomentCapture(\\'' + escapeHtml(curCommId)", 1),
        # openChatWithUser inline handler (pre-existing escaping, not this finding)
        ("openChatWithUser(\\'' + f.id", 1),
    ]

    def test_50_id_only_handlers_remain_untouched(self):
        src = _app_js_source()
        for marker, expected in self.UNTOUCHED_MARKERS:
            actual = src.count(marker)
            self.assertEqual(
                actual, expected,
                "ID-only handler %r must remain unchanged (expected %d, found %d)" % (marker, expected, actual),
            )

    def test_51_no_handler_architecture_refactor(self):
        # B2-SEC-15 must NOT replace the inline-handler architecture.
        src = _app_js_source()
        self.assertGreater(
            src.count("onclick="), 30,
            "inline handlers must remain in place (architecture refactor is a future task)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
