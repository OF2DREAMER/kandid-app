#!/usr/bin/env python3
"""
Regression test suite for Camera Context Integrity & Stale activeClusterContext isolation.

Verifies:
TEST 1 — Feed Camera clears stale Perspective
TEST 2 — Perspective entry remains Perspective
TEST 3 — Navigation clears transient camera context
TEST 4 — Review cancellation clears context
TEST 5 — I WAS THERE isolation
TEST 6 — Community camera context
"""

import json
import os
import subprocess
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

NODE_SCRIPT = """
const fs = require('fs');
const vm = require('vm');

const makeEl = (id) => ({
  id: id || '',
  style: {},
  classList: { add: () => {}, remove: () => {} },
  dataset: {},
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
  appendChild: () => {},
  setAttribute: () => {},
  removeAttribute: () => {}
});

const elements = {};
const getEl = (id) => {
  if (!elements[id]) elements[id] = makeEl(id);
  return elements[id];
};

const mockWindow = {
  location: { origin: 'http://localhost:8080' },
  addEventListener: () => {},
  document: {
    getElementById: (id) => getEl(id),
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: () => makeEl(),
    addEventListener: () => {}
  },
  navigator: { userAgent: 'node' },
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  setTimeout: () => 1,
  clearTimeout: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  console: console
};
mockWindow.window = mockWindow;
mockWindow.document.defaultView = mockWindow;

const code = fs.readFileSync('app_core.js', 'utf8');
const context = vm.createContext(mockWindow);
vm.runInContext(code, context);

// Mock KandidCameraEngine methods to prevent hardware calls
context.KandidCameraEngine.initialize = async () => {};
context.KandidCameraEngine.stop = () => {};
context.showToast = () => {};
context.apiRequest = async (url) => {
  if (url.includes('/i-was-there')) {
    return { success: true, message: 'Attended', cluster_id: 'cls_from_iwt' };
  }
  return { success: true };
};

(async () => {
  const results = {};

  // =========================================================================
  // TEST 1 — Feed Camera clears stale Perspective
  // =========================================================================
  context.state.cameraContext = {
    mode: 'PERSPECTIVE',
    clusterId: 'test_cls',
    clusterName: 'Old Event',
    communityId: 'old_comm',
    source: 'event'
  };
  context.state.activeClusterContext = 'test_cls';
  context.state.activeClusterCommunityId = 'old_comm';
  context.state.activeClusterContextName = 'Old Event';

  context.openCameraStudio(); // Called with no args (Feed Shutter)

  results.test1 = {
    mode: context.state.cameraContext.mode,
    clusterId: context.state.cameraContext.clusterId,
    activeClusterContext: context.state.activeClusterContext,
    source: context.state.cameraContext.source
  };

  // =========================================================================
  // TEST 2 — Perspective entry remains Perspective
  // =========================================================================
  context.openPerspectiveCapture('cls_abc', 'comm_xyz', 'North Quad');

  results.test2 = {
    mode: context.state.cameraContext.mode,
    clusterId: context.state.cameraContext.clusterId,
    communityId: context.state.cameraContext.communityId,
    source: context.state.cameraContext.source
  };

  // =========================================================================
  // TEST 3 — Navigation clears transient camera context
  // =========================================================================
  context.openPerspectiveCapture('cls_persp_active', 'comm_nav', 'South Lawn');
  getEl('cameraStudioModal').style.display = 'flex';

  context.switchScreenView('search');

  results.test3 = {
    cameraContextMode: context.state.cameraContext.mode,
    cameraContextClusterId: context.state.cameraContext.clusterId,
    activeClusterContext: context.state.activeClusterContext,
    reviewCameraContext: context.state.reviewCameraContext
  };

  // =========================================================================
  // TEST 4 — Review cancellation clears context
  // =========================================================================
  context.openPerspectiveCapture('cls_review_test', 'comm_rev', 'Quad Center');
  context.state.reviewCameraContext = Object.assign({}, context.state.cameraContext);
  getEl('reviewContentStream').style.display = 'block';

  context.closeMomentReview();

  results.test4 = {
    reviewCameraContext: context.state.reviewCameraContext,
    cameraContextMode: context.state.cameraContext.mode,
    cameraContextClusterId: context.state.cameraContext.clusterId,
    activeClusterContext: context.state.activeClusterContext
  };

  // =========================================================================
  // TEST 5 — I WAS THERE isolation
  // =========================================================================
  context.state.attendedMoments = new Set();
  // Run I WAS THERE
  await context.handleIWasThereClick('moment_xyz', false);
  const attendedBefore = context.state.attendedMoments.has('moment_xyz');

  // Open camera normally from Feed
  context.openCameraStudio();

  results.test5 = {
    attendedBefore: attendedBefore,
    attendedAfter: context.state.attendedMoments.has('moment_xyz'),
    mode: context.state.cameraContext.mode,
    clusterId: context.state.cameraContext.clusterId,
    activeClusterContext: context.state.activeClusterContext
  };

  // =========================================================================
  // TEST 6 — Community camera context
  // =========================================================================
  context.openCommunityMomentCapture('comm_123', 'Design Club');

  results.test6 = {
    mode: context.state.cameraContext.mode,
    communityId: context.state.cameraContext.communityId,
    clusterId: context.state.cameraContext.clusterId,
    source: context.state.cameraContext.source
  };

  // =========================================================================
  // TEST 7 — Missing context in handleAddPerspectiveClick never falls back to camera
  // =========================================================================
  let toastMsg7 = '';
  context.showToast = (msg) => { toastMsg7 = msg; };
  context.state.currentViewingCluster = null;
  context.state.activeClusterMomentId = null;
  context.state.cameraContext = { mode: 'INITIAL_STATE', clusterId: null, source: 'none' };
  let cameraOpened7 = false;
  context.KandidCameraEngine.initialize = async () => { cameraOpened7 = true; };

  context.handleAddPerspectiveClick();

  results.test7 = {
    toastMsg: toastMsg7,
    cameraOpened: cameraOpened7,
    cameraMode: context.state.cameraContext.mode
  };

  // =========================================================================
  // TEST 8 — Community visibility fail-closed evaluation in renderCommunityCards
  // =========================================================================
  const createTestContainer = () => {
    const el = makeEl();
    el.children = [];
    el.appendChild = (child) => { el.children.push(child); };
    return el;
  };

  // 8A: Unknown/missing visibility, non-member -> FAIL CLOSED
  const containerUnknown = createTestContainer();
  context.state.activeCommunityData = null;
  context.state.currentUser = { id: 'u_viewer', role: 'member' };
  context.renderCommunityCards([{
    id: 'm_unk',
    user_id: 'u_author',
    caption: 'Unknown Post',
    cluster_id: 'cls_unk',
    community_visibility: ''
  }], containerUnknown);
  const unkHtml = containerUnknown.children.map(c => c.innerHTML || '').join('');

  // 8B: Confirmed public -> perspective button rendered
  const containerPub = createTestContainer();
  context.renderCommunityCards([{
    id: 'm_pub',
    user_id: 'u_author',
    caption: 'Public Post',
    cluster_id: 'cls_pub',
    community_visibility: 'public'
  }], containerPub);
  const pubHtml = containerPub.children.map(c => c.innerHTML || '').join('');

  // 8C: Private community, authorized member -> perspective button rendered
  const containerPrivMem = createTestContainer();
  context.state.activeCommunityData = { id: 'c_priv', visibility: 'private', is_joined: true };
  context.renderCommunityCards([{
    id: 'm_priv',
    user_id: 'u_author',
    caption: 'Private Post',
    cluster_id: 'cls_priv',
    community_visibility: 'private'
  }], containerPrivMem);
  const privHtml = containerPrivMem.children.map(c => c.innerHTML || '').join('');

  results.test8 = {
    unknownHasPerspective: unkHtml.includes('Perspective'),
    unknownHasIWasThere: unkHtml.includes('I WAS THERE'),
    pubHasPerspective: pubHtml.includes('Perspective'),
    privMemHasPerspective: privHtml.includes('Perspective')
  };

  // =========================================================================
  // TEST 9 — Live Pulse capture preserves active Community context
  // =========================================================================
  context.state.activeCommunityId = 'comm_pulse_test';
  context.state.activeCommunity = 'Design Studio';
  context.openCommunityMomentCapture(context.state.activeCommunityId, context.state.activeCommunity);
  results.test9 = {
    mode: context.state.cameraContext.mode,
    communityId: context.state.cameraContext.communityId,
    source: context.state.cameraContext.source,
    selectedReviewCommunity: context.state.selectedReviewCommunity
  };

  console.log(JSON.stringify(results));
  process.exit(0);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
"""


class TestCameraContextIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cmd = ["node", "-e", NODE_SCRIPT]
        proc = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
        if proc.returncode != 0:
            print("STDERR:", proc.stderr)
            raise RuntimeError(f"Node execution failed with code {proc.returncode}")
        cls.results = json.loads(proc.stdout.strip())

    def test_01_feed_camera_clears_stale_perspective(self):
        """TEST 1 — Feed Camera clears stale Perspective"""
        t1 = self.results["test1"]
        self.assertEqual(t1["mode"], "NORMAL")
        self.assertIsNone(t1["clusterId"])
        self.assertIsNone(t1["activeClusterContext"])
        self.assertEqual(t1["source"], "feed")

    def test_02_perspective_entry_remains_perspective(self):
        """TEST 2 — Perspective entry remains Perspective"""
        t2 = self.results["test2"]
        self.assertEqual(t2["mode"], "PERSPECTIVE")
        self.assertEqual(t2["clusterId"], "cls_abc")
        self.assertEqual(t2["communityId"], "comm_xyz")
        self.assertEqual(t2["source"], "event")

    def test_03_navigation_clears_transient_camera_context(self):
        """TEST 3 — Navigation clears transient camera context"""
        t3 = self.results["test3"]
        self.assertEqual(t3["cameraContextMode"], "NORMAL")
        self.assertIsNone(t3["cameraContextClusterId"])
        self.assertIsNone(t3["activeClusterContext"])
        self.assertIsNone(t3["reviewCameraContext"])

    def test_04_review_cancellation_clears_context(self):
        """TEST 4 — Review cancellation clears context"""
        t4 = self.results["test4"]
        self.assertIsNone(t4["reviewCameraContext"])
        self.assertEqual(t4["cameraContextMode"], "NORMAL")
        self.assertIsNone(t4["cameraContextClusterId"])
        self.assertIsNone(t4["activeClusterContext"])

    def test_05_i_was_there_isolation(self):
        """TEST 5 — I WAS THERE isolation"""
        t5 = self.results["test5"]
        self.assertTrue(t5["attendedBefore"])
        self.assertTrue(t5["attendedAfter"])
        self.assertEqual(t5["mode"], "NORMAL")
        self.assertIsNone(t5["clusterId"])
        self.assertIsNone(t5["activeClusterContext"])

    def test_06_community_camera_context(self):
        """TEST 6 — Community camera context"""
        t6 = self.results["test6"]
        self.assertEqual(t6["mode"], "NORMAL")
        self.assertEqual(t6["communityId"], "comm_123")
        self.assertIsNone(t6["clusterId"])
        self.assertEqual(t6["source"], "community")

    def test_07_handle_add_perspective_missing_context_fails_safely(self):
        """TEST 7 — Missing context in handleAddPerspectiveClick never falls back to camera"""
        t7 = self.results["test7"]
        self.assertIn("Moment context unavailable", t7["toastMsg"])
        self.assertFalse(t7["cameraOpened"])
        self.assertEqual(t7["cameraMode"], "INITIAL_STATE")

    def test_08_community_visibility_fail_closed(self):
        """TEST 8 — Community visibility fail-closed evaluation in renderCommunityCards"""
        t8 = self.results["test8"]
        self.assertFalse(t8["unknownHasPerspective"])
        self.assertFalse(t8["unknownHasIWasThere"])
        self.assertTrue(t8["pubHasPerspective"])
        self.assertTrue(t8["privMemHasPerspective"])

    def test_09_live_pulse_capture_preserves_community_context(self):
        """TEST 9 — Live Pulse capture preserves active Community context"""
        t9 = self.results["test9"]
        self.assertEqual(t9["mode"], "NORMAL")
        self.assertEqual(t9["communityId"], "comm_pulse_test")
        self.assertEqual(t9["source"], "community")
        self.assertEqual(t9["selectedReviewCommunity"], "Design Studio")


if __name__ == "__main__":
    unittest.main()
