#!/usr/bin/env python3
"""
Focused regression test for Day-3 Task 3: hidden-tab network polling.

Three network timers in app.js must bail out while the document is hidden:

  1. 3s  heartbeat / notification poller   (DOMContentLoaded, ~line 5417)
  2. 2.5s chat sync poller                 (chatSyncGlobalInterval)
  3. 45s  auth ping                        (chatHeartbeatInterval)

The DOM-only timers (10s updateAllMomentTimestamps, 1s statusClock,
1s dailyAlertInterval) must stay untouched.

Two layers of proof, deliberately not a fake browser:

  A. STATIC  - the guard is the first statement of each network callback and
               appears before any network call in that callback; intervals are
               unchanged; only 3 `document.hidden` guards exist and no
               `visibilitychange` listener was added.

  B. INSTRUMENTED - the *real* callback bodies extracted from app.js are
               executed by Node with stubbed timers/network functions, so we
               observe actual call behaviour for document.hidden true/false.

Runs read-only: app.js is parsed, never modified. No server and no database
are used, so data/kandid.db is never touched.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_JS = os.path.join(PROJECT_DIR, "app.js")

# Baseline commit that this task is implemented on (guards must be the only
# difference inside these three callbacks).
BASELINE_COMMIT = "5f7db8e"

# (name, anchor that starts the callback, terminator, expected interval)
NETWORK_TIMERS = [
    (
        "heartbeat_3s",
        "// 5b. Real-time Heartbeat, Notification, & Presence Poller\n  setInterval(function() {\n",
        "\n  }, 3000);",
        3000,
    ),
    (
        "chat_sync_2_5s",
        "window.chatSyncGlobalInterval = setInterval(function() {\n",
        "\n}, 2500);",
        2500,
    ),
    (
        "auth_ping_45s",
        "window.chatHeartbeatInterval = setInterval(function() {\n",
        "\n}, 45000);",
        45000,
    ),
]

# Callables that produce (or trigger) network traffic.
NETWORK_CALL_RE = re.compile(
    r"\b(apiRequest|loadChatMessages|loadChatConversations|loadNotifications|checkChatUnreadBadge|fetch)\s*\("
)

GUARD = "if (document.hidden) return;"

# DOM-only timers that must NOT be gated.
DOM_ONLY_TIMERS = [
    ("updateAllMomentTimestamps_10s", 1819),
    ("statusClock_1s", 5402),
    ("dailyAlert_1s", 9669),
]


def read_app():
    with open(APP_JS, "r", encoding="utf-8") as fh:
        return fh.read()


def extract_callback_body(src, anchor, terminator):
    """Return the raw text of a setInterval callback body (between the opening
    `function() {` and the terminating `}, <ms>);`)."""
    start = src.find(anchor)
    if start == -1:
        raise AssertionError("anchor not found: %r" % anchor[:60])
    if src.count(anchor) != 1:
        raise AssertionError("anchor not unique: %r" % anchor[:60])
    body_start = start + len(anchor)
    end = src.find(terminator, body_start)
    if end == -1:
        raise AssertionError("terminator not found for %r" % anchor[:60])
    return src[body_start:end]


def strip_guard_comments(body):
    """Remove the guard statement and its D3-3 comment line."""
    lines = [
        ln
        for ln in body.split("\n")
        if "D3-3: skip network polling" not in ln and GUARD not in ln
    ]
    return "\n".join(lines)


def network_calls_in(body):
    return NETWORK_CALL_RE.findall(body)


class HiddenTabStaticTests(unittest.TestCase):
    """Layer A: the guard exists, is first, and precedes every network call."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_app()

    def test_01_guard_is_first_statement_in_each_network_callback(self):
        for name, anchor, terminator, _ms in NETWORK_TIMERS:
            body = extract_callback_body(self.src, anchor, terminator)
            stmts = [
                ln.strip()
                for ln in body.split("\n")
                if ln.strip() and not ln.strip().startswith("//")
            ]
            self.assertTrue(stmts, "%s: empty callback" % name)
            self.assertEqual(
                stmts[0],
                GUARD,
                "%s: first statement must be `%s`, got %r" % (name, GUARD, stmts[0]),
            )

    def test_02_guard_precedes_every_network_call(self):
        for name, anchor, terminator, _ms in NETWORK_TIMERS:
            body = extract_callback_body(self.src, anchor, terminator)
            guard_at = body.find(GUARD)
            self.assertNotEqual(guard_at, -1, "%s: guard missing" % name)
            first_call = NETWORK_CALL_RE.search(body)
            self.assertIsNotNone(
                first_call, "%s: expected at least one network call" % name
            )
            self.assertLess(
                guard_at,
                first_call.start(),
                "%s: guard must run before the first network call" % name,
            )
            self.assertGreaterEqual(
                len(network_calls_in(body)), 1, "%s: no network calls found" % name
            )

    def test_03_intervals_unchanged(self):
        for name, anchor, terminator, expected_ms in NETWORK_TIMERS:
            idx = self.src.find(anchor)
            self.assertNotEqual(idx, -1)
            self.assertIn(
                terminator,
                self.src[idx:],
                "%s: interval must stay %d ms" % (name, expected_ms),
            )
        # No interval was cleared/re-registered as part of this task: the three
        # interval registrations still exist exactly once each.
        self.assertEqual(
            self.src.count("window.chatSyncGlobalInterval = setInterval("), 1
        )
        self.assertEqual(
            self.src.count("window.chatHeartbeatInterval = setInterval("), 1
        )

    def test_04_only_three_hidden_guards_and_no_visibility_listener(self):
        self.assertEqual(
            self.src.count("if (document.hidden) return;"),
            3,
            "exactly the three network callbacks may be gated",
        )
        self.assertEqual(
            self.src.count("document.hidden"),
            3,
            "no other document.hidden usage may be introduced",
        )
        self.assertEqual(
            self.src.count("visibilitychange"),
            0,
            "D3-3 must not add a visibilitychange listener",
        )

    def test_05_dom_only_timers_untouched(self):
        lines = self.src.split("\n")
        for name, line_no in DOM_ONLY_TIMERS:
            window = "\n".join(lines[line_no - 2: line_no + 12])
            self.assertNotIn(
                "document.hidden",
                window,
                "%s (%s) is DOM-only and must not be gated" % (name, line_no),
            )
        # The long-standing registrations themselves are still present.
        self.assertIn("setInterval(updateAllMomentTimestamps, 10000)", self.src)
        self.assertEqual(
            self.src.count("dailyAlertInterval = setInterval(function() {"), 1
        )

    def test_06_foreground_callbacks_identical_to_baseline(self):
        """Removing the guard lines must reproduce the committed baseline exactly."""
        try:
            baseline = subprocess.run(
                ["git", "show", "%s:app.js" % BASELINE_COMMIT],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            self.skipTest("git/baseline unavailable: %s" % exc)
        if baseline.returncode != 0:
            self.skipTest("baseline commit %s not available" % BASELINE_COMMIT)

        for name, anchor, terminator, _ms in NETWORK_TIMERS:
            cur_body = extract_callback_body(self.src, anchor, terminator)
            base_body = extract_callback_body(baseline.stdout, anchor, terminator)
            self.assertEqual(
                strip_guard_comments(cur_body),
                base_body,
                "%s: foreground behaviour must be unchanged vs %s"
                % (name, BASELINE_COMMIT),
            )


NODE_HARNESS = r"""
'use strict';
const calls = [];
const state = {
  token: 'test-token',
  currentUser: { id: 'u_test', handle: '@test' },
  activeScreen: '__SCREEN__',
  activeChatUser: 'u_other',
  lastAlertedNotifId: null
};
const document = {
  hidden: __HIDDEN__,
  getElementById: function () { return null; }
};
function apiRequest(path) {
  calls.push('apiRequest:' + path);
  if (path === '/api/chat/unread-count') return Promise.resolve({ success: true, count: 0 });
  return Promise.resolve({ success: true, unreadCount: 0, pendingRequestsCount: 0 });
}
function loadChatMessages(user, silent) { calls.push('loadChatMessages:' + user); }
function loadChatConversations(silent) { calls.push('loadChatConversations'); }
function loadNotifications() { calls.push('loadNotifications'); }
function checkChatUnreadBadge() { calls.push('checkChatUnreadBadge'); }
function showLiveNotificationBanner(n) { calls.push('showLiveNotificationBanner'); }

async function runCallback() {
  __BODY__
}

runCallback().then(function () {
  return new Promise(function (r) { setTimeout(r, 5); });
}).then(function () {
  process.stdout.write(JSON.stringify(calls));
}).catch(function (err) {
  process.stdout.write(JSON.stringify({ error: String(err) }));
});
"""


class HiddenTabInstrumentedTests(unittest.TestCase):
    """Layer B: execute the real callback bodies under Node with stubs."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_app()
        cls.tmpdir = tempfile.mkdtemp(prefix="kandid_d3_3_")
        try:
            subprocess.run(["node", "--version"], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            shutil.rmtree(cls.tmpdir, ignore_errors=True)
            raise unittest.SkipTest("node unavailable: %s" % exc)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmpdir", ""), ignore_errors=True)

    def _run(self, body, hidden, screen="chat-conversation"):
        script = (
            NODE_HARNESS.replace("__HIDDEN__", "true" if hidden else "false")
            .replace("__SCREEN__", screen)
            .replace("__BODY__", body)
        )
        path = os.path.join(self.tmpdir, "cb.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(script)
        proc = subprocess.run(
            ["node", path], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(
            proc.returncode,
            0,
            "node harness failed: %s %s" % (proc.stdout, proc.stderr),
        )
        out = proc.stdout.strip()
        parsed = json.loads(out)
        self.assertNotIsInstance(parsed, dict, "callback threw: %s" % parsed)
        return parsed

    def test_07_hidden_tab_makes_no_heartbeat_network_request(self):
        name, anchor, terminator, _ms = NETWORK_TIMERS[0]
        body = extract_callback_body(self.src, anchor, terminator)
        hidden_calls = self._run(body, hidden=True)
        self.assertEqual(
            hidden_calls, [], "hidden tab must not poll /api/heartbeat or anything else"
        )
        visible_calls = self._run(body, hidden=False)
        self.assertIn(
            "apiRequest:/api/heartbeat",
            visible_calls,
            "visible tab must keep its existing heartbeat behaviour",
        )

    def test_08_hidden_tab_makes_no_chat_sync_network_request(self):
        name, anchor, terminator, _ms = NETWORK_TIMERS[1]
        body = extract_callback_body(self.src, anchor, terminator)
        hidden_calls = self._run(body, hidden=True)
        self.assertEqual(
            hidden_calls, [], "hidden tab must not run the chat sync poller"
        )
        visible_calls = self._run(body, hidden=False)
        self.assertEqual(
            visible_calls,
            ["checkChatUnreadBadge", "loadChatMessages:u_other"],
            "visible chat sync behaviour must be unchanged",
        )

    def test_09_hidden_tab_makes_no_auth_ping_request(self):
        name, anchor, terminator, _ms = NETWORK_TIMERS[2]
        body = extract_callback_body(self.src, anchor, terminator)
        hidden_calls = self._run(body, hidden=True)
        self.assertEqual(hidden_calls, [], "hidden tab must not ping /api/auth/ping")
        visible_calls = self._run(body, hidden=False)
        self.assertEqual(
            visible_calls, ["apiRequest:/api/auth/ping"], "visible ping unchanged"
        )

    def test_10_visible_heartbeat_notification_refresh_unchanged(self):
        """When the notifications screen is open the visible heartbeat still
        refreshes notifications (and does nothing extra while hidden)."""
        name, anchor, terminator, _ms = NETWORK_TIMERS[0]
        body = extract_callback_body(self.src, anchor, terminator)
        visible_calls = self._run(body, hidden=False, screen="notifications")
        self.assertIn(
            "apiRequest:/api/heartbeat",
            visible_calls,
            "visible heartbeat must still ping",
        )
        self.assertIn(
            "loadNotifications",
            visible_calls,
            "visible heartbeat must still refresh notifications on that screen",
        )
        hidden_calls = self._run(body, hidden=True, screen="notifications")
        self.assertEqual(hidden_calls, [], "hidden tab must do neither")


if __name__ == "__main__":
    unittest.main(verbosity=2)
