#!/usr/bin/env python3
"""
Focused regression test for Day-3 Task 4: service-worker API cache isolation.

BEFORE the fix sw.js cached *every* same-origin, status-200, type-'basic' GET
response into Cache Storage and replayed it by URL whenever the network failed.
That included authenticated/private `/api/*` responses, so user A's private
payload could be served to user B out of the shared cache.

The fix inserts one early return in the fetch listener:

    const url = new URL(event.request.url);
    if (url.origin === self.location.origin &&
        (url.pathname === '/api' || url.pathname.startsWith('/api/') ||
         url.pathname === '/health')) {
      return;
    }

Returning without calling event.respondWith() means the browser performs its
normal network fetch: the service worker never sees the response, never calls
cache.put(), never calls caches.match(), and therefore can never replay private
API data. Static asset caching is untouched.

Two layers of proof, deliberately not a fake browser:

  A. STATIC      - the guard lives inside the fetch listener, after the method
                   check, before event.respondWith(), same-origin scoped, and
                   the rest of sw.js is byte-identical to the committed
                   baseline (install/activate/CACHE_NAME/respondWith body).

  B. BEHAVIOURAL - the *real* sw.js is loaded into a Node `vm` sandbox with
                   instrumented caches/fetch, and synthetic FetchEvents are
                   dispatched at the registered fetch listener. We observe
                   whether the SW intercepted the request (respondWith called)
                   or left it to the browser, and which cache methods it hit.

Teeth: the harness is also run against the committed baseline sw.js, where the
same cases must show the leak (API response cached; cached private data
consulted while offline). Without the fix the behavioural tests fail.

Runs read-only: sw.js is parsed, never modified. No server and no database are
used, so data/kandid.db is never touched.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SW_JS = os.path.join(PROJECT_DIR, "sw.js")

# Commit the D3-4 work is built on: `git show <commit>:sw.js` is the pre-fix
# service worker used both to prove nothing else changed and to prove that the
# behavioural cases really do catch the leak.
BASELINE_COMMIT = "572e29f"

FETCH_LISTENER = "self.addEventListener('fetch', event => {"
INSTALL_LISTENER = "self.addEventListener('install', event => {"
ACTIVATE_LISTENER = "self.addEventListener('activate', event => {"
CACHE_NAME_LINE = "const CACHE_NAME = 'kandid-v5.0.5';"
METHOD_GUARD = "if (event.request.method !== 'GET') return;"
ORIGIN_GUARD = "url.origin === self.location.origin"
PATH_GUARD_API = "url.pathname === '/api' || url.pathname.startsWith('/api/')"
PATH_GUARD_HEALTH = "url.pathname === '/health'"
RESPOND_WITH = "event.respondWith("
PUT_LINE = "cache.put(event.request, clone)"
MATCH_LINE = "caches.match(event.request)"


def read_sw():
    with open(SW_JS, "r", encoding="utf-8") as fh:
        return fh.read()


def baseline_sw():
    """Return the committed pre-fix sw.js, or None when git/baseline is unusable."""
    try:
        proc = subprocess.run(
            ["git", "show", "%s:sw.js" % BASELINE_COMMIT],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def reassemble_without_api_guard(src):
    """`src` with the inserted API guard block cut out.

    Everything from the start of the file through the `method !== GET` line is
    kept, then everything from `event.respondWith(` onward. Removing the
    insertion from the patched file must reproduce the baseline byte-for-byte,
    which proves the insertion is the *only* change to sw.js.
    """
    m = src.find(METHOD_GUARD)
    if m == -1 or src.count(METHOD_GUARD) != 1:
        raise AssertionError("expected exactly one method guard")
    m_end = m + len(METHOD_GUARD)
    r = src.find(RESPOND_WITH, m_end)
    if r == -1 or src.count(RESPOND_WITH) != 1:
        raise AssertionError("expected exactly one event.respondWith")
    return src[:m_end] + src[r:]


def inserted_block(src):
    """The exact text inserted between the method guard and event.respondWith."""
    m = src.find(METHOD_GUARD) + len(METHOD_GUARD)
    r = src.find(RESPOND_WITH, m)
    return src[m:r]


class SwStaticSourceTests(unittest.TestCase):
    """Layer A: shape and blast radius of the change, checked on the real file."""

    @classmethod
    def setUpClass(cls):
        cls.src = read_sw()
        cls.baseline = baseline_sw()

    def test_01_api_guard_exists_inside_fetch_listener(self):
        src = self.src
        self.assertEqual(src.count(FETCH_LISTENER), 1, "one fetch listener expected")
        fetch_at = src.index(FETCH_LISTENER)
        guard_at = src.find(ORIGIN_GUARD)
        self.assertNotEqual(guard_at, -1, "same-origin API guard is missing")
        self.assertGreater(
            guard_at,
            fetch_at,
            "the API guard must live inside the fetch listener, not at top level",
        )
        body = src[fetch_at:]
        self.assertIn(PATH_GUARD_API, body)
        self.assertIn(PATH_GUARD_HEALTH, body)
        self.assertRegex(
            body,
            r"if \(url\.origin === self\.location\.origin &&\s*\n"
            r"\s*\(url\.pathname === '/api' \|\| url\.pathname\.startsWith\('/api/'\) \|\|\s*\n"
            r"\s*url\.pathname === '/health'\)\) \{\s*\n\s*return;\s*\n\s*\}",
            "guard must be the locked same-origin /api + /health early return",
        )

    def test_02_guard_is_after_method_check_and_before_respondwith(self):
        src = self.src
        method_at = src.index(METHOD_GUARD)
        guard_at = src.index(ORIGIN_GUARD)
        respond_at = src.index(RESPOND_WITH)
        self.assertLess(method_at, guard_at, "guard must come after the method check")
        self.assertLess(guard_at, respond_at, "guard must come before respondWith")
        # The guard must short-circuit, never respondWith().
        block = inserted_block(src)
        self.assertIn("return;", block)
        self.assertNotIn("respondWith", block)

    def test_03_guard_is_same_origin_scoped_and_occurs_once(self):
        src = self.src
        self.assertEqual(
            src.count(ORIGIN_GUARD), 1, "guard must be declared exactly once"
        )
        self.assertIn("const url = new URL(event.request.url);", src)
        # Same-origin scoping: the /api test is ANDed with the origin test, so a
        # cross-origin `/api/...` URL cannot be swallowed by this guard.
        block = inserted_block(src)
        self.assertIn("url.origin === self.location.origin", block)
        self.assertIn("&&", block)

    def test_04_static_asset_caching_path_is_intact(self):
        src = self.src
        # Guard was NOT pushed into cache.put() and no second guard was added
        # inside the catch() cache fallback.
        self.assertIn(PUT_LINE, src, "static asset caching (cache.put) must remain")
        self.assertIn(MATCH_LINE, src, "static cache fallback must remain")
        self.assertEqual(src.count(".catch(() => caches.match(event.request))"), 1)
        self.assertLess(
            src.index(ORIGIN_GUARD),
            src.index(PUT_LINE),
            "guard must precede the caching code path",
        )
        self.assertLess(src.index(ORIGIN_GUARD), src.index(MATCH_LINE))
        # respondWith body unchanged: network-first, cache on 200/basic.
        self.assertIn("response.status === 200 && response.type === 'basic'", src)
        self.assertIn("const clone = response.clone();", src)
        self.assertIn("return response;", src)

    def test_05_install_activate_and_cache_name_unchanged(self):
        src = self.src
        self.assertEqual(src.count(CACHE_NAME_LINE), 1, "CACHE_NAME must be unchanged")
        self.assertEqual(src.count(INSTALL_LISTENER), 1)
        self.assertEqual(src.count(ACTIVATE_LISTENER), 1)
        self.assertIn("self.skipWaiting();", src)
        self.assertIn("self.clients.claim()", src)
        # No precache list, no allowlist, no Vary/header-based caching, no new
        # caches.open() call anywhere.
        self.assertNotIn("addAll", src)
        self.assertNotIn("Vary", src)
        self.assertNotIn("allowlist", src.lower())
        self.assertEqual(src.count("caches.open(CACHE_NAME)"), 1)
        self.assertEqual(src.count("addEventListener("), 3, "exactly install/activate/fetch")

    def test_06_only_the_api_guard_was_inserted_vs_baseline(self):
        if self.baseline is None:
            self.skipTest("baseline commit %s not available" % BASELINE_COMMIT)
        try:
            current_rebuilt = reassemble_without_api_guard(self.src)
            baseline_rebuilt = reassemble_without_api_guard(self.baseline)
        except AssertionError as exc:
            self.fail("baseline is not the expected shape: %s" % exc)
        self.assertEqual(
            current_rebuilt,
            baseline_rebuilt,
            "removing the inserted guard must reproduce the committed baseline exactly "
            "(install, activate, CACHE_NAME and the respondWith body are untouched)",
        )
        # And the thing we removed really is the API guard.
        block = inserted_block(self.src)
        self.assertIn(ORIGIN_GUARD, block)
        self.assertIn("/api/", block)
        self.assertIn("/health", block)


NODE_HARNESS = r"""
'use strict';

// Loads the REAL sw.js into a vm sandbox with instrumented caches/fetch and
// dispatches synthetic FetchEvents. Prints JSON keyed by case name.
const fs = require('fs');
const vm = require('vm');

const SW_PATH = process.argv[2];
const ORIGIN = 'https://kandid.example';
const source = fs.readFileSync(SW_PATH, 'utf8');

const listeners = {};
const calls = { fetch: [], cachePut: [], cachesMatch: [], cacheOpen: [], cacheKeys: 0, cacheDelete: [] };
let networkAvailable = true;
let cacheStore = {};

function makeResponse(type) {
  return {
    status: 200,
    type: type,
    body: 'mock-body',
    clone: function () { return makeResponse(type); }
  };
}

const sandbox = {};
sandbox.self = {
  location: { origin: ORIGIN },
  addEventListener: function (type, fn) { listeners[type] = fn; },
  skipWaiting: function () {},
  clients: { claim: function () { return Promise.resolve(); } }
};
sandbox.caches = {
  keys: function () { calls.cacheKeys++; return Promise.resolve(Object.keys(cacheStore)); },
  'delete': function (k) { calls.cacheDelete.push(k); return Promise.resolve(true); },
  open: function (name) {
    calls.cacheOpen.push(name);
    return Promise.resolve({
      put: function (req, res) {
        calls.cachePut.push(req.url);
        cacheStore[req.url] = res;
        return Promise.resolve();
      }
    });
  },
  match: function (req) {
    calls.cachesMatch.push(req.url);
    return Promise.resolve(cacheStore[req.url]);
  }
};
sandbox.fetch = function (req) {
  calls.fetch.push(req.url);
  if (!networkAvailable) { return Promise.reject(new TypeError('Failed to fetch')); }
  var sameOrigin = req.url.indexOf(ORIGIN) === 0;
  return Promise.resolve(makeResponse(sameOrigin ? 'basic' : 'cors'));
};
sandbox.URL = URL;
sandbox.Promise = Promise;
sandbox.console = console;

vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: SW_PATH });

function dispatch(rawUrl, opts) {
  opts = opts || {};
  var u = new URL(rawUrl, ORIGIN);
  var event = {
    request: {
      url: u.href,
      method: opts.method || 'GET',
      headers: opts.headers || {}
    },
    intercepted: false,
    respondWith: function (p) { this.intercepted = true; this.promise = p; }
  };
  listeners.fetch(event);
  return event;
}

function resetCalls() {
  calls.fetch = [];
  calls.cachePut = [];
  calls.cachesMatch = [];
  calls.cacheOpen = [];
}

var results = {};

function runCase(name, cfg) {
  resetCalls();
  cacheStore = cfg.store ? Object.assign({}, cfg.store) : {};
  networkAvailable = cfg.online !== false;
  var preExisting = Object.keys(cacheStore);

  var event = dispatch(cfg.url, { method: cfg.method, headers: cfg.headers });
  var settled = event.intercepted
    ? Promise.resolve(event.promise).then(
        function (r) {
          return { intercepted: true, status: r ? r.status : null, type: r ? r.type : null };
        },
        function (e) { return { intercepted: true, error: String(e) }; })
    : Promise.resolve({ intercepted: false, passthrough: true });

  return settled.then(function (outcome) {
    results[name] = {
      intercepted: event.intercepted,
      outcome: outcome,
      fetchCalls: calls.fetch.slice(),
      cachePut: calls.cachePut.slice(),
      cachesMatch: calls.cachesMatch.slice(),
      cacheOpen: calls.cacheOpen.slice(),
      preExistingCacheKeys: preExisting
    };
  });
}

var PRIVATE_URL = ORIGIN + '/api/notifications';
var seedUserAData = {};
seedUserAData[PRIVATE_URL] = makeResponse('basic');

var seedStatic = {};
seedStatic[ORIGIN + '/index.html'] = makeResponse('basic');

Promise.resolve()
  .then(function () { return runCase('api_notifications', { url: '/api/notifications' }); })
  .then(function () { return runCase('api_chat_messages', { url: '/api/chat/messages?user_id=42' }); })
  .then(function () { return runCase('api_chat_attachment', { url: '/api/chat/attachments/att_123' }); })
  .then(function () { return runCase('api_auth_me', { url: '/api/auth/me' }); })
  .then(function () { return runCase('api_health', { url: '/health' }); })
  .then(function () {
    return runCase('private_cross_user_offline', {
      url: '/api/notifications',
      online: false,
      headers: { Authorization: 'Bearer user-b-token' },
      store: seedUserAData
    });
  })
  .then(function () { return runCase('static_app_js', { url: '/app.js' }); })
  .then(function () {
    return runCase('static_index_html_offline', {
      url: '/index.html',
      online: false,
      store: seedStatic
    });
  })
  .then(function () { return runCase('post_api_chat_send', { url: '/api/chat/send', method: 'POST' }); })
  .then(function () { return runCase('cross_origin_get', { url: 'https://cdn.example.com/lib.js' }); })
  .then(function () {
    process.stdout.write(JSON.stringify(results));
  }, function (err) {
    process.stdout.write(JSON.stringify({ error: String(err) }));
  });
"""


class SwBehavioralTests(unittest.TestCase):
    """Layer B: run the real sw.js under Node and observe what it actually does."""

    @classmethod
    def setUpClass(cls):
        try:
            subprocess.run(["node", "--version"], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise unittest.SkipTest("node unavailable: %s" % exc)
        cls.tmpdir = tempfile.mkdtemp(prefix="kandid_d3_4_")
        cls.harness = os.path.join(cls.tmpdir, "sw_harness.js")
        with open(cls.harness, "w", encoding="utf-8") as fh:
            fh.write(NODE_HARNESS)
        cls.results = cls._run_harness(SW_JS)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmpdir", ""), ignore_errors=True)

    @classmethod
    def _run_harness(cls, sw_path):
        proc = subprocess.run(
            ["node", cls.harness, sw_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError(
                "node harness failed (%s): %s %s" % (sw_path, proc.stdout, proc.stderr)
            )
        out = proc.stdout.strip()
        try:
            parsed = json.loads(out)
        except ValueError:
            raise AssertionError("harness produced non-JSON output: %r" % out)
        if not isinstance(parsed, dict) or "error" in parsed:
            raise AssertionError("harness reported an error: %s" % parsed)
        for name in (
            "api_notifications",
            "api_chat_messages",
            "api_chat_attachment",
            "api_auth_me",
            "api_health",
            "private_cross_user_offline",
            "static_app_js",
            "static_index_html_offline",
            "post_api_chat_send",
            "cross_origin_get",
        ):
            if name not in parsed:
                raise AssertionError("harness did not report case %r" % name)
        return parsed

    def _case(self, name):
        return self.results[name]

    def _assert_not_intercepted_and_untouched(self, name):
        """The SW must not respondWith, must not cache, must not read the cache."""
        c = self._case(name)
        self.assertFalse(
            c["intercepted"],
            "%s: SW must return without respondWith (browser does a normal fetch)" % name,
        )
        self.assertEqual(c["cachePut"], [], "%s: cache.put must not be called" % name)
        self.assertEqual(c["cachesMatch"], [], "%s: caches.match must not be called" % name)
        self.assertEqual(c["cacheOpen"], [], "%s: caches.open must not be called" % name)
        self.assertEqual(c["fetchCalls"], [], "%s: SW must not fetch on the caller's behalf" % name)
        self.assertTrue(c["outcome"].get("passthrough"), "%s: must pass through" % name)

    def test_07_get_api_notifications_not_cached(self):
        self._assert_not_intercepted_and_untouched("api_notifications")

    def test_08_get_api_chat_messages_not_cached(self):
        self._assert_not_intercepted_and_untouched("api_chat_messages")

    def test_09_get_api_chat_attachment_not_cached(self):
        self._assert_not_intercepted_and_untouched("api_chat_attachment")

    def test_10_get_api_auth_me_not_cached(self):
        self._assert_not_intercepted_and_untouched("api_auth_me")

    def test_11_get_health_not_cached(self):
        self._assert_not_intercepted_and_untouched("api_health")

    def test_12_private_data_never_replayed_to_another_user_offline(self):
        """User A's cached private response must not be reachable while offline
        for a *different* Authorization header."""
        c = self._case("private_cross_user_offline")
        self.assertEqual(
            len(c["preExistingCacheKeys"]),
            1,
            "scenario must actually have a pre-existing private cache entry",
        )
        self.assertTrue(
            c["preExistingCacheKeys"][0].endswith("/api/notifications"),
            "the pre-existing entry must be the private API URL",
        )
        self.assertFalse(c["intercepted"], "SW must not intercept the private API GET")
        self.assertEqual(
            c["cachesMatch"], [], "SW must not consult the cache for private API data"
        )
        self.assertEqual(c["cachePut"], [], "SW must not cache private API data")
        self.assertTrue(c["outcome"].get("passthrough"), "browser must handle the request")
        self.assertIsNone(
            c["outcome"].get("status"),
            "the SW must not return user A's cached payload to user B",
        )

    def test_13_static_assets_still_cached(self):
        c = self._case("static_app_js")
        self.assertTrue(c["intercepted"], "static GETs must still go through the SW")
        self.assertIn(
            "https://kandid.example/app.js",
            c["cachePut"],
            "static asset must still be written to Cache Storage",
        )
        self.assertEqual(c["outcome"].get("status"), 200)

    def test_14_static_offline_fallback_still_works(self):
        """index.html with a dead network must still be served from the cache
        (the pre-existing network-first / cache-fallback behaviour)."""
        c = self._case("static_index_html_offline")
        self.assertTrue(c["intercepted"], "static GET must still be intercepted")
        self.assertEqual(
            c["cachesMatch"],
            ["https://kandid.example/index.html"],
            "static fallback must still consult the cache",
        )
        self.assertEqual(c["outcome"].get("status"), 200, "cached static response returned")
        self.assertEqual(c["outcome"].get("type"), "basic")

    def test_15_post_is_not_intercepted(self):
        c = self._case("post_api_chat_send")
        self.assertFalse(c["intercepted"], "non-GET must never be intercepted")
        self.assertEqual(c["cachePut"], [])
        self.assertEqual(c["cachesMatch"], [])
        self.assertEqual(c["fetchCalls"], [])

    def test_16_cross_origin_get_behaviour_unchanged(self):
        """A cross-origin GET is still handled exactly as before: intercepted,
        fetched, and (because it is type 'cors') not written to the cache."""
        c = self._case("cross_origin_get")
        self.assertTrue(c["intercepted"], "cross-origin GET behaviour must not change")
        self.assertEqual(
            c["fetchCalls"], ["https://cdn.example.com/lib.js"], "SW still performs the fetch"
        )
        self.assertEqual(
            c["cachePut"],
            [],
            "non-basic (cross-origin) responses were never cached - unchanged",
        )

    def test_17_baseline_sw_really_did_leak(self):
        """Teeth: the same harness against the committed pre-fix sw.js must show
        the vulnerability, otherwise these behavioural tests prove nothing."""
        baseline = baseline_sw()
        if baseline is None:
            self.skipTest("baseline commit %s not available" % BASELINE_COMMIT)
        path = os.path.join(self.tmpdir, "baseline_sw.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(baseline)
        base = self._run_harness(path)

        self.assertFalse(
            "D3-4" in baseline,
            "baseline must be the pre-fix service worker",
        )
        self.assertTrue(
            base["api_notifications"]["intercepted"],
            "pre-fix SW intercepted API requests (the leak)",
        )
        self.assertIn(
            "https://kandid.example/api/notifications",
            base["api_notifications"]["cachePut"],
            "pre-fix SW cached the private API response (the leak)",
        )
        self.assertIn(
            "https://kandid.example/api/notifications",
            base["private_cross_user_offline"]["cachesMatch"],
            "pre-fix SW consulted the shared cache for private data while offline (the leak)",
        )
        # ...and the fixed worker must not.
        self.assertEqual(self.results["api_notifications"]["cachePut"], [])
        self.assertEqual(self.results["private_cross_user_offline"]["cachesMatch"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
