#!/usr/bin/env python3
"""
Focused regression test for D4-04: RateLimiter expired-bucket cleanup.

BEFORE: RateLimiter.check_rate_limit() filtered per-key timestamp lists but
NEVER deleted keys from self.buckets. With six call sites keying on
client_ip / user_id, the dictionary grew without bound (one stale key per
client IP / uploader forever) — an unbounded memory leak on a long-running
production process.

AFTER: an amortized, selective TTL sweep runs under the EXISTING lock at most
once per CLEANUP_INTERVAL (512) checks. It deletes ONLY:
  - empty buckets, or
  - buckets whose NEWEST timestamp is older than MAX_WINDOW_SECONDS (60s),
i.e. buckets that can never contribute a valid timestamp to any future check
because every current call site uses window_seconds=60. Active buckets (and
blocked-but-active buckets) are never touched, so a sweep can never reset an
in-flight rate limit. No clear(), no dict rebuild, no background thread, no
new libraries.

All tests are deterministic: time is provided by a fake clock patched into
the server module namespace (no real sleeps). The limiter is pure in-memory,
so no HTTP server or database is involved; call-site integrity is verified
statically against the real server.py source.
"""

import inspect
import re
import threading
import types
import unittest
from unittest import mock

PROJECT_DIR = "/home/daytona/codebase"
import sys
sys.path.insert(0, PROJECT_DIR)

import server  # noqa: E402
from server import RateLimiter  # noqa: E402

SERVER_PY = PROJECT_DIR + "/server.py"


class FakeClock:
    """Deterministic time source for the limiter (no real sleeping)."""

    def __init__(self, start=1_000_000.0):
        self.t = float(start)

    def time(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


class LimiterTestBase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._patcher = mock.patch.object(server, "time", types.SimpleNamespace(time=self.clock.time))
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.rl = RateLimiter()

    # ---- helpers -------------------------------------------------------------
    def seed(self, key, ts_list):
        """Directly inject a bucket (deterministic fixture construction)."""
        self.rl.buckets[key] = list(ts_list)

    def force_sweep(self):
        self.rl._sweep_expired(self.clock.t)

    def trigger_amortized_sweep(self, probe_key=None):
        """Fire the sweep through the real amortized path (ops counter)."""
        self.rl._ops = RateLimiter.CLEANUP_INTERVAL - 1
        self.rl.check_rate_limit(probe_key or "__probe__", 10, 60)
        return self.rl._ops % RateLimiter.CLEANUP_INTERVAL == 0


class TestExistingBehavior(LimiterTestBase):
    """Requirements 1, 2, 11, 12: limit semantics unchanged, call sites intact."""

    def test_01_allows_up_to_limit_then_blocks_then_recovers(self):
        results = [self.rl.check_rate_limit("login:1.2.3.4", 10, 60) for _ in range(10)]
        self.assertTrue(all(results))
        self.assertFalse(self.rl.check_rate_limit("login:1.2.3.4", 10, 60))  # 11th blocked
        self.clock.advance(61)  # whole window elapsed
        self.assertTrue(self.rl.check_rate_limit("login:1.2.3.4", 10, 60))   # recovered

    def test_02_key_reaches_configured_limit_and_is_blocked(self):
        for _ in range(15):
            self.rl.check_rate_limit("verify_reset_otp:5.6.7.8", 15, 60)
        self.assertFalse(self.rl.check_rate_limit("verify_reset_otp:5.6.7.8", 15, 60))

    def test_03_pure_in_memory_no_database_involvement(self):
        src = inspect.getsource(RateLimiter)
        for forbidden in ("get_db", "cursor", "sqlite", "psycopg", "execute(", "DATABASE_URL"):
            self.assertNotIn(forbidden, src)

    def test_04_all_six_call_sites_unchanged(self):
        with open(SERVER_PY, "r", encoding="utf-8") as fh:
            src = fh.read()
        expected = [
            ('forgot_pw:', 10, 60), ('login:', 10, 60), ('verify_reset_otp:', 15, 60),
            ('reset_pw:', 10, 60), ('chat_attach:', 20, 60), ('chat_send:', 60, 60),
        ]
        for prefix, maxr, win in expected:
            pat = re.compile(
                r"check_rate_limit\(f\"%s\{?[^\"]*\"?,\s*max_requests=%d,\s*window_seconds=%d\)" % (re.escape(prefix), maxr, win)
            )
            self.assertTrue(pat.search(src), f"call site missing/changed: {prefix} {maxr}/{win}")
        self.assertIn("rate_limiter = RateLimiter()", src)


class TestSelectiveCleanup(LimiterTestBase):
    """Requirements 3, 4, 5, 6, 10: what the sweep deletes and preserves."""

    def test_05_active_blocked_bucket_survives_sweep(self):
        key = "chat_send:u42"
        for _ in range(60):
            self.assertTrue(self.rl.check_rate_limit(key, 60, 60))
        self.assertFalse(self.rl.check_rate_limit(key, 60, 60))  # now blocked+active
        self.force_sweep()
        self.assertIn(key, self.rl.buckets)
        self.assertEqual(len(self.rl.buckets[key]), 60)

    def test_06_expired_buckets_deleted(self):
        self.seed("forgot_pw:old-ip", [self.clock.t - 120, self.clock.t - 90])
        self.seed("login:old-ip", [self.clock.t - 61])
        self.force_sweep()
        self.assertNotIn("forgot_pw:old-ip", self.rl.buckets)
        self.assertNotIn("login:old-ip", self.rl.buckets)

    def test_07_empty_buckets_deleted(self):
        self.rl.buckets["ghost"] = []
        self.force_sweep()
        self.assertNotIn("ghost", self.rl.buckets)

    def test_08_boundary_newest_exactly_max_window_old_is_kept(self):
        # newest == now - 60 is NOT "older than" the window -> conservative keep
        self.seed("edge:ip", [self.clock.t - 60])
        self.force_sweep()
        self.assertIn("edge:ip", self.rl.buckets)
        self.clock.advance(1)
        self.force_sweep()
        self.assertNotIn("edge:ip", self.rl.buckets)

    def test_09_multiple_keys_independently_preserved_or_removed(self):
        active = "chat_attach:u1"
        blocked = "chat_send:u2"
        expired = "login:9.9.9.9"
        empty = "ghost"
        for _ in range(20):
            self.assertTrue(self.rl.check_rate_limit(active, 20, 60))
        for _ in range(60):
            self.assertTrue(self.rl.check_rate_limit(blocked, 60, 60))
        self.assertFalse(self.rl.check_rate_limit(blocked, 60, 60))
        self.seed(expired, [self.clock.t - 500])
        self.rl.buckets[empty] = []

        before = len(self.rl.buckets)
        self.force_sweep()
        after = len(self.rl.buckets)

        self.assertIn(active, self.rl.buckets)
        self.assertIn(blocked, self.rl.buckets)
        self.assertNotIn(expired, self.rl.buckets)
        self.assertNotIn(empty, self.rl.buckets)
        self.assertLess(after, before)
        self.assertEqual(after, 2)

    def test_10_bucket_count_monotonic_non_increasing_across_sweep(self):
        for i in range(300):
            self.seed(f"stale:{i}", [self.clock.t - 1000])
        self.seed("alive", [self.clock.t])
        before = len(self.rl.buckets)
        self.force_sweep()
        self.assertEqual(len(self.rl.buckets), 1)
        # amortized path: sweep runs BEFORE the probe key's bucket is created,
        # so a single call may add at most one new bucket on top of the sweep.
        before2 = len(self.rl.buckets)
        self.trigger_amortized_sweep(probe_key="fresh:new")
        self.assertLessEqual(len(self.rl.buckets), before2 + 1)
        self.assertIn("fresh:new", self.rl.buckets)


class TestNoRateLimitReset(LimiterTestBase):
    """Requirement 7: cleanup must never reset an active key's history."""

    def test_11_blocked_key_still_blocked_after_many_sweeps(self):
        key = "login:1.1.1.1"
        for _ in range(10):
            self.assertTrue(self.rl.check_rate_limit(key, 10, 60))
        self.assertFalse(self.rl.check_rate_limit(key, 10, 60))
        for _ in range(10):
            self.force_sweep()
            self.assertFalse(self.rl.check_rate_limit(key, 10, 60),
                             "sweep reset an active block")
        self.clock.advance(30)  # still inside the 60s window
        self.force_sweep()
        self.assertFalse(self.rl.check_rate_limit(key, 10, 60))
        self.clock.advance(31)  # window elapsed -> recovery allowed
        self.assertTrue(self.rl.check_rate_limit(key, 10, 60))

    def test_12_history_timestamps_preserved_by_sweep(self):
        key = "forgot_pw:2.2.2.2"
        for _ in range(5):
            self.assertTrue(self.rl.check_rate_limit(key, 10, 60))
        snapshot = list(self.rl.buckets[key])
        self.force_sweep()
        self.assertEqual(self.rl.buckets[key], snapshot)


class TestMemoryBehavior(LimiterTestBase):
    """Requirements 8, 13 + the deterministic MEMORY TEST."""

    def test_13_memory_many_expired_buckets_swept_active_survives_limited(self):
        # 5000 long-expired buckets + 2 active buckets (one blocked).
        for i in range(5000):
            self.seed(f"chat_send:stale-{i}", [self.clock.t - 3600])
        active = "chat_send:active-user"
        for _ in range(60):
            self.assertTrue(self.rl.check_rate_limit(active, 60, 60))
        self.assertFalse(self.rl.check_rate_limit(active, 60, 60))
        self.seed("login:recent", [self.clock.t - 10])

        self.assertEqual(len(self.rl.buckets), 5002)
        self.assertTrue(self.trigger_amortized_sweep(probe_key="__probe__"))
        # 2 active + 1 probe bucket remain; all 5000 expired buckets gone.
        self.assertEqual(len(self.rl.buckets), 3)
        self.assertIn(active, self.rl.buckets)
        self.assertIn("login:recent", self.rl.buckets)
        # Active bucket is STILL rate-limited (not reset by cleanup).
        self.assertFalse(self.rl.check_rate_limit(active, 60, 60))

    def test_14_same_key_never_grows_unbounded(self):
        key = "chat_send:chatty"
        for round_no in range(200):
            for _ in range(20):
                self.rl.check_rate_limit(key, 60, 60)
            self.clock.advance(10)  # rolling window; sweeps fire every 512 ops
            self.assertLessEqual(len(self.rl.buckets[key]), 60)
            self.assertEqual(len(self.rl.buckets), 1)  # never more than one bucket

    def test_15_sweep_is_amortized_not_every_call(self):
        self.seed("stale:x", [self.clock.t - 9999])
        for _ in range(RateLimiter.CLEANUP_INTERVAL - 1):
            self.rl.check_rate_limit("k", 10, 60)
        self.assertIn("stale:x", self.rl.buckets)  # not swept yet
        self.rl.check_rate_limit("k", 10, 60)      # 512th op fires the sweep
        self.assertNotIn("stale:x", self.rl.buckets)


class TestConcurrency(LimiterTestBase):
    """Requirement 9: thread safety under the existing lock."""

    def test_16_concurrent_access_thread_safe(self):
        results = []
        lock = threading.Lock()

        def worker(thread_no):
            local = []
            for i in range(150):
                ok = self.rl.check_rate_limit(f"login:t{thread_no % 4}", 10, 60)
                local.append(ok)
                if i % 50 == 0:
                    self.clock.advance(0.001)
            with lock:
                results.extend(local)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), "deadlock detected")
        # Per-key window invariant: at most 10 successful admissions per window.
        for key, history in self.rl.buckets.items():
            self.assertIsInstance(history, list)
            self.assertLessEqual(len(history), 12)  # <= limit + boundary churn
            if history:
                self.assertEqual(history, sorted(history))
        # Global admissions within the (barely advancing) window are bounded.
        self.assertLessEqual(sum(1 for r in results if r), 4 * 10 + 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)
