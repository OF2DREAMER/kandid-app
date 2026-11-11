#!/usr/bin/env python3
"""
Permanent regression coverage for the Capture Context / Community Destination picker.

The test runs the real `app_core.js` functions in a Node VM. Only browser/DOM
and network boundaries are mocked:

  - /api/community/my returns controlled membership fixtures.
  - /api/moments/capture records the exact payload.
  - Camera initialization/audio waiting are no-ops.

No production database, credentials, or network access is used.

Run: python3 test_capture_destination_picker.py
"""

import json
import os
import subprocess
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

NODE_SCRIPT = """
const fs = require('fs');
const vm = require('vm');

function makeEl(id) {
  return {
    id: id || '',
    style: {},
    innerHTML: '',
    textContent: '',
    value: '',
    disabled: false,
    dataset: {},
    children: [],
    scrollTop: 0,
    classList: {
      add: function() {},
      remove: function() {},
      toggle: function() {},
      contains: function() { return false; }
    },
    querySelector: function() { return null; },
    querySelectorAll: function() { return []; },
    addEventListener: function() {},
    removeEventListener: function() {},
    appendChild: function(child) { this.children.push(child); },
    setAttribute: function() {},
    removeAttribute: function() {},
    focus: function() {},
    blur: function() {},
    closest: function() { return null; },
    play: function() { return Promise.resolve(); },
    pause: function() {}
  };
}

const elements = {};
const getEl = function(id) {
  if (!elements[id]) elements[id] = makeEl(id);
  return elements[id];
};
const publishBtn = makeEl('publishBtn');
const mockWindow = {
  location: { origin: 'http://localhost:8080' },
  addEventListener: function() {},
  document: {
    getElementById: function(id) { return getEl(id); },
    querySelectorAll: function() { return []; },
    querySelector: function(selector) {
      return selector === 'button[onclick="publishCapturedMoment()"]' ? publishBtn : null;
    },
    createElement: function() { return makeEl(); },
    addEventListener: function() {}
  },
  navigator: { userAgent: 'node', mediaDevices: { getUserMedia: async function() { return null; } } },
  localStorage: {
    getItem: function() { return null; },
    setItem: function() {},
    removeItem: function() {},
    clear: function() {}
  },
  setTimeout: function() { return 1; },
  clearTimeout: function() {},
  setInterval: function() { return 1; },
  clearInterval: function() {},
  console: console
};
mockWindow.window = mockWindow;
mockWindow.document.defaultView = mockWindow;

const context = vm.createContext(mockWindow);
vm.runInContext(fs.readFileSync('app_core.js', 'utf8'), context);

// External boundaries only: no camera hardware, no audio recording, no feed refreshes.
context.KandidCameraEngine.initialize = async function() {};
context.KandidCameraEngine.stop = function() {};
context.KandidCameraEngine.awaitPendingAudio = async function() {};
context.KandidCameraEngine.startAmbientAudioCapture = function() {};
context.openCameraStudio = async function() {};
context.closeCameraStudio = function() {};
context.selectSubTab = function() {};
context.loadFeedMoments = async function() {};
context.loadCampusScreen = async function() {};
context.loadYouScreen = async function() {};
context.markDailyAlertCompleted = function() {};
context.openMomentClusterModal = function() {};
context.handleNewUserFeedEntry = function() {};
context.handleNewUserFeedExit = function() {};

let membershipResponse = { success: true, communities: [] };
let membershipCalls = 0;
let publishPayloads = [];
let toasts = [];
let publishResponse = { success: true };

context.apiRequest = async function(url, options) {
  if (url === '/api/community/my') {
    membershipCalls++;
    return membershipResponse;
  }
  if (url === '/api/moments/capture') {
    publishPayloads.push(JSON.parse(options.body));
    return publishResponse;
  }
  return { success: true };
};
context.showToast = function(message) {
  toasts.push(String(message));
};

function community(n) {
  const num = String(n).padStart(2, '0');
  return {
    id: 'comm_' + num,
    name: 'Community ' + num,
    type: 'Interest',
    icon: 'C',
    city: 'City ' + num
  };
}

function makeCommunities(count) {
  const list = [];
  for (let i = 1; i <= count; i++) list.push(community(i));
  return list;
}

function resetFixture() {
  const s = context.state;
  s.currentUser = { campus: 'Supaul' };
  s.currentGeoApprox = null;
  s.activeCircle = 'campus';
  s.activeScreen = 'feed';
  s.activeCommunityId = '';
  s.activeCommunity = '';
  s.selectedReviewCommunity = null;
  s.reviewJoinedCommunities = [];
  s.reviewDestinationMode = 'personal';
  s.reviewCommunitiesLoading = false;
  s.reviewCommunitiesError = '';
  s.reviewContextRequestId = 0;
  s.reviewCommunityPickerQuery = '';
  s.reviewCommunityPickerLimit = 20;
  s.reviewCameraContext = null;
  s.cameraContext = {
    mode: 'NORMAL',
    clusterId: null,
    clusterName: null,
    communityId: null,
    source: 'feed'
  };
  s.capturedMomentData = {
    mainImg: 'data:image/jpeg;base64,MAIN',
    pipImg: 'data:image/jpeg;base64,PIP',
    audioData: ''
  };
  s.isOpeningReview = false;
  s.activeEventId = '';
  s.activeClusterContext = null;
  s.activeClusterCommunityId = null;
  s.activeClusterContextName = null;

  getEl('reviewCommunityOptionsList').innerHTML = '';
  getEl('reviewCommunityPickerList').innerHTML = '';
  getEl('reviewCommunityPickerModal').style.display = 'none';
  getEl('reviewCommunitySearchInput').value = '';
  getEl('reviewCaptionInput').value = 'Test caption';
  getEl('reviewContentStream').style.display = 'block';
  getEl('cameraStudioModal').style.display = 'none';
  publishBtn.disabled = false;
  publishBtn.innerHTML = 'PUBLISH';

  membershipResponse = { success: true, communities: [] };
  membershipCalls = 0;
  publishPayloads = [];
  toasts = [];
  publishResponse = { success: true };
}

function optionsHtml() {
  return getEl('reviewCommunityOptionsList').innerHTML;
}

function pickerHtml() {
  return getEl('reviewCommunityPickerList').innerHTML;
}

function countOccurrences(value, needle) {
  return value.split(needle).length - 1;
}

function communityButtonCount() {
  return countOccurrences(optionsHtml(), 'id="reviewDestinationCommunityBtn"');
}

function pickerRowCount() {
  return countOccurrences(pickerHtml(), 'onclick="selectReviewDestinationCommunity(');
}

async function setupWith(list) {
  membershipResponse = { success: true, communities: list };
  await context.setupReviewContextUI();
  return optionsHtml();
}

(async function() {
  const results = {};

  // 1. Zero memberships: only Personal (Feed) is rendered.
  resetFixture();
  membershipResponse = { success: true, communities: [] };
  await context.setupReviewContextUI();
  results.zero = {
    html: optionsHtml(),
    mode: context.state.reviewDestinationMode,
    joined: context.state.reviewJoinedCommunities.length,
    communityButtons: communityButtonCount()
  };

  // 2. Membership API failure: Personal remains selectable, retry is shown,
  // and a later successful setup recovers the membership selector.
  resetFixture();
  membershipResponse = { success: false, error: 'offline' };
  await context.setupReviewContextUI();
  const errorHtml = optionsHtml();
  const errorState = {
    mode: context.state.reviewDestinationMode,
    joined: context.state.reviewJoinedCommunities.length,
    communityButtons: communityButtonCount(),
    calls: membershipCalls
  };
  const recoveryHtml = await setupWith(makeCommunities(1));
  results.apiError = {
    html: errorHtml,
    state: errorState,
    recovery: {
      html: recoveryHtml,
      joined: context.state.reviewJoinedCommunities.length,
      communityButtons: communityButtonCount(),
      calls: membershipCalls
    }
  };

  // 3. One membership: one compact selector, no permanently rendered card list.
  resetFixture();
  const one = makeCommunities(1);
  await setupWith(one);
  results.one = {
    html: optionsHtml(),
    mode: context.state.reviewDestinationMode,
    joined: context.state.reviewJoinedCommunities.length,
    communityButtons: communityButtonCount(),
    hasMemberName: optionsHtml().indexOf('Community 01') !== -1,
    hasChooseLabel: optionsHtml().indexOf('Choose a community') !== -1
  };

  // 4. Three memberships: still one compact selector; the full list is not
  // expanded into the camera/review screen.
  resetFixture();
  await setupWith(makeCommunities(3));
  results.three = {
    html: optionsHtml(),
    joined: context.state.reviewJoinedCommunities.length,
    communityButtons: communityButtonCount(),
    hasFirst: optionsHtml().indexOf('Community 01') !== -1,
    hasSecond: optionsHtml().indexOf('Community 02') !== -1,
    hasThird: optionsHtml().indexOf('Community 03') !== -1
  };

  // 5. Twenty memberships: compact summary, picker has the full page.
  resetFixture();
  await setupWith(makeCommunities(20));
  context.openReviewCommunityPicker();
  results.twenty = {
    communityButtons: communityButtonCount(),
    joined: context.state.reviewJoinedCommunities.length,
    pickerRows: pickerRowCount(),
    pickerLimit: context.state.reviewCommunityPickerLimit,
    hasLoadMore: pickerHtml().indexOf('Load ') !== -1,
    hasFirst: pickerHtml().indexOf('Community 01') !== -1,
    hasLast: pickerHtml().indexOf('Community 20') !== -1
  };

  // 6. Fifty memberships: no camera-screen expansion, only the first page is rendered.
  resetFixture();
  await setupWith(makeCommunities(50));
  context.openReviewCommunityPicker();
  results.fifty = {
    communityButtons: communityButtonCount(),
    joined: context.state.reviewJoinedCommunities.length,
    pickerRows: pickerRowCount(),
    pickerLimit: context.state.reviewCommunityPickerLimit,
    hasTwentyFirst: pickerHtml().indexOf('Community 21') !== -1,
    hasLoadMore: pickerHtml().indexOf('Load 20 more') !== -1
  };

  // 7. Fifty memberships: incremental rendering reaches the full membership list.
  context.loadMoreReviewCommunities();
  const fortyRows = pickerRowCount();
  const fortyHasLoadMore = pickerHtml().indexOf('Load 10 more') !== -1;
  context.loadMoreReviewCommunities();
  results.incremental = {
    fortyRows: fortyRows,
    fortyHasLoadMore: fortyHasLoadMore,
    finalRows: pickerRowCount(),
    finalHasLoadMore: pickerHtml().indexOf('Load ') !== -1,
    finalLimit: context.state.reviewCommunityPickerLimit,
    hasFiftieth: pickerHtml().indexOf('Community 50') !== -1
  };

  // 8. Search filters the full joined list and reports an empty state.
  resetFixture();
  await setupWith(makeCommunities(50));
  context.openReviewCommunityPicker();
  context.filterReviewCommunityPicker('Community 07');
  const searchRows = pickerRowCount();
  const searchHtml = pickerHtml();
  const searchHasTarget = searchHtml.indexOf('Community 07') !== -1;
  const searchHasOther = searchHtml.indexOf('Community 08') !== -1;
  context.filterReviewCommunityPicker('not a joined community');
  const emptyHtml = pickerHtml();
  context.filterReviewCommunityPicker('');
  const resetRows = pickerRowCount();
  results.search = {
    rows: searchRows,
    hasTarget: searchHasTarget,
    hasOther: searchHasOther,
    emptyText: emptyHtml.indexOf('No joined communities match that search.') !== -1,
    resetRows: resetRows
  };

  // 9. Selecting a community updates the destination and closes the picker.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.openReviewCommunityPicker();
  context.selectReviewDestinationCommunity('comm_02');
  results.select = {
    mode: context.state.reviewDestinationMode,
    activeId: context.state.activeCommunityId,
    selectedName: context.state.selectedReviewCommunity,
    modalDisplay: getEl('reviewCommunityPickerModal').style.display,
    summaryHasName: optionsHtml().indexOf('Community 02') !== -1,
    summaryHasSelected: optionsHtml().indexOf('SELECTED') !== -1
  };

  // 10. Switching back to Personal clears the community destination.
  context.onReviewCommunityChange({ getAttribute: function() { return ''; } });
  results.switchPersonal = {
    mode: context.state.reviewDestinationMode,
    activeId: context.state.activeCommunityId,
    selectedName: context.state.selectedReviewCommunity,
    summaryHasPersonal: optionsHtml().indexOf('Personal (Feed)') !== -1,
    summaryHasSelected: optionsHtml().indexOf('SELECTED') !== -1
  };

  // 11. A removed membership cannot remain selected after a fresh setup.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.selectReviewDestinationCommunity('comm_02');
  context.state.cameraContext = {
    mode: 'NORMAL',
    clusterId: null,
    clusterName: null,
    communityId: 'comm_02',
    source: 'community'
  };
  await setupWith([community(1)]);
  results.removed = {
    mode: context.state.reviewDestinationMode,
    activeId: context.state.activeCommunityId,
    selectedName: context.state.selectedReviewCommunity,
    joined: context.state.reviewJoinedCommunities.length,
    communityButtons: communityButtonCount(),
    html: optionsHtml()
  };

  // 12. Personal publishing preserves the existing Personal Feed payload.
  resetFixture();
  await setupWith(makeCommunities(1));
  await context.publishCapturedMoment();
  results.publishPersonal = {
    calls: publishPayloads.length,
    payload: publishPayloads[0] || null,
    toast: toasts[toasts.length - 1] || ''
  };

  // 13. Community publishing preserves the existing single-community payload.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.selectReviewDestinationCommunity('comm_02');
  await context.publishCapturedMoment();
  results.publishCommunity = {
    calls: publishPayloads.length,
    payload: publishPayloads[0] || null,
    toast: toasts[toasts.length - 1] || ''
  };

  // 14. A new review setup refreshes memberships without an app refresh.
  resetFixture();
  await setupWith(makeCommunities(1));
  const firstJoined = context.state.reviewJoinedCommunities.length;
  await setupWith(makeCommunities(2));
  context.openReviewCommunityPicker();
  results.refresh = {
    firstJoined: firstJoined,
    secondJoined: context.state.reviewJoinedCommunities.length,
    calls: membershipCalls,
    communityButtons: communityButtonCount(),
    pickerRows: pickerRowCount(),
    hasNewCommunity: pickerHtml().indexOf('Community 02') !== -1
  };

  // 15. Retake preserves a valid community destination for the next review.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.selectReviewDestinationCommunity('comm_02');
  await context.retakeMomentFromReview();
  const retakeMode = context.state.reviewDestinationMode;
  const retakeActiveId = context.state.activeCommunityId;
  const retakeSelectedName = context.state.selectedReviewCommunity;
  const retakeCaptured = context.state.capturedMomentData;
  await setupWith(makeCommunities(3));
  results.retake = {
    mode: retakeMode,
    activeId: retakeActiveId,
    selectedName: retakeSelectedName,
    capturedMomentData: retakeCaptured,
    afterSetupMode: context.state.reviewDestinationMode,
    afterSetupSelected: context.state.selectedReviewCommunity
  };

  // 16. Closing review clears the destination state.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.selectReviewDestinationCommunity('comm_02');
  context.closeMomentReview();
  results.close = {
    mode: context.state.reviewDestinationMode,
    activeId: context.state.activeCommunityId,
    selectedName: context.state.selectedReviewCommunity,
    joined: context.state.reviewJoinedCommunities.length,
    reviewContext: context.state.reviewCameraContext,
    cameraMode: context.state.cameraContext.mode
  };

  // 17. Leaving the review screen through navigation clears destination state.
  resetFixture();
  await setupWith(makeCommunities(3));
  context.selectReviewDestinationCommunity('comm_02');
  getEl('reviewContentStream').style.display = 'block';
  getEl('cameraStudioModal').style.display = 'none';
  context.state.isOpeningReview = false;
  context.state.activeScreen = 'feed';
  context.switchScreenView('search');
  results.navigation = {
    mode: context.state.reviewDestinationMode,
    activeId: context.state.activeCommunityId,
    selectedName: context.state.selectedReviewCommunity,
    joined: context.state.reviewJoinedCommunities.length,
    reviewContext: context.state.reviewCameraContext,
    cameraMode: context.state.cameraContext.mode
  };

  // 18. Invalid community selection is rejected and cannot reach publishing.
  resetFixture();
  await setupWith(makeCommunities(1));
  context.selectReviewDestinationCommunity('comm_removed');
  const selectToast = toasts[toasts.length - 1] || '';
  const selectMode = context.state.reviewDestinationMode;
  context.state.reviewDestinationMode = 'community';
  context.state.activeCommunityId = 'comm_removed';
  context.state.selectedReviewCommunity = 'Removed Community';
  publishPayloads = [];
  toasts = [];
  await context.publishCapturedMoment();
  results.invalidPublish = {
    selectMode: selectMode,
    selectToast: selectToast,
    publishCalls: publishPayloads.length,
    publishToast: toasts[toasts.length - 1] || ''
  };

  console.log(JSON.stringify(results));
  process.exit(0);
})().catch(function(err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
"""


class TestCaptureDestinationPicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            ["node", "-e", NODE_SCRIPT],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "Node picker regression harness failed:\n"
                + proc.stdout
                + "\n"
                + proc.stderr
            )
        cls.results = json.loads(proc.stdout.strip())

    def test_01_zero_memberships(self):
        data = self.results["zero"]
        self.assertEqual(data["mode"], "personal")
        self.assertEqual(data["joined"], 0)
        self.assertEqual(data["communityButtons"], 0)
        self.assertIn("Personal (Feed)", data["html"])
        self.assertNotIn("reviewDestinationCommunityBtn", data["html"])

    def test_02_membership_api_failure_and_retry(self):
        data = self.results["apiError"]
        self.assertEqual(data["state"]["mode"], "personal")
        self.assertEqual(data["state"]["joined"], 0)
        self.assertEqual(data["state"]["communityButtons"], 0)
        self.assertEqual(data["state"]["calls"], 1)
        self.assertIn("Personal (Feed)", data["html"])
        self.assertIn("Communities unavailable", data["html"])
        self.assertIn("RETRY", data["html"])
        self.assertEqual(data["recovery"]["joined"], 1)
        self.assertEqual(data["recovery"]["communityButtons"], 1)
        self.assertEqual(data["recovery"]["calls"], 2)

    def test_03_one_membership_compact_selector(self):
        data = self.results["one"]
        self.assertEqual(data["mode"], "personal")
        self.assertEqual(data["joined"], 1)
        self.assertEqual(data["communityButtons"], 1)
        self.assertIn("Personal (Feed)", data["html"])
        self.assertIn("Choose a community", data["html"])
        self.assertFalse(data["hasMemberName"])

    def test_04_three_memberships_do_not_expand_camera_screen(self):
        data = self.results["three"]
        self.assertEqual(data["joined"], 3)
        self.assertEqual(data["communityButtons"], 1)
        self.assertIn("Personal (Feed)", data["html"])
        self.assertFalse(data["hasFirst"])
        self.assertFalse(data["hasSecond"])
        self.assertFalse(data["hasThird"])

    def test_05_twenty_memberships_compact_picker(self):
        data = self.results["twenty"]
        self.assertEqual(data["joined"], 20)
        self.assertEqual(data["communityButtons"], 1)
        self.assertEqual(data["pickerRows"], 20)
        self.assertEqual(data["pickerLimit"], 20)
        self.assertFalse(data["hasLoadMore"])
        self.assertTrue(data["hasFirst"])
        self.assertTrue(data["hasLast"])

    def test_06_fifty_memberships_do_not_expand_camera_screen(self):
        data = self.results["fifty"]
        self.assertEqual(data["joined"], 50)
        self.assertEqual(data["communityButtons"], 1)
        self.assertEqual(data["pickerRows"], 20)
        self.assertEqual(data["pickerLimit"], 20)
        self.assertFalse(data["hasTwentyFirst"])
        self.assertTrue(data["hasLoadMore"])

    def test_07_fifty_memberships_incremental_picker(self):
        data = self.results["incremental"]
        self.assertEqual(data["fortyRows"], 40)
        self.assertTrue(data["fortyHasLoadMore"])
        self.assertEqual(data["finalRows"], 50)
        self.assertFalse(data["finalHasLoadMore"])
        self.assertGreaterEqual(data["finalLimit"], 50)
        self.assertTrue(data["hasFiftieth"])

    def test_08_community_search(self):
        data = self.results["search"]
        self.assertEqual(data["rows"], 1)
        self.assertTrue(data["hasTarget"])
        self.assertFalse(data["hasOther"])
        self.assertTrue(data["emptyText"])
        self.assertEqual(data["resetRows"], 20)

    def test_09_selecting_community_updates_destination(self):
        data = self.results["select"]
        self.assertEqual(data["mode"], "community")
        self.assertEqual(data["activeId"], "comm_02")
        self.assertEqual(data["selectedName"], "Community 02")
        self.assertEqual(data["modalDisplay"], "none")
        self.assertTrue(data["summaryHasName"])
        self.assertTrue(data["summaryHasSelected"])

    def test_10_switching_to_personal_updates_destination(self):
        data = self.results["switchPersonal"]
        self.assertEqual(data["mode"], "personal")
        self.assertEqual(data["activeId"], "")
        self.assertEqual(data["selectedName"], "Personal (Feed)")
        self.assertTrue(data["summaryHasPersonal"])
        self.assertTrue(data["summaryHasSelected"])

    def test_11_removed_membership_is_not_selectable(self):
        data = self.results["removed"]
        self.assertEqual(data["mode"], "personal")
        self.assertEqual(data["activeId"], "")
        self.assertEqual(data["selectedName"], "Personal (Feed)")
        self.assertEqual(data["joined"], 1)
        self.assertEqual(data["communityButtons"], 1)
        self.assertNotIn("Community 02", data["html"])

    def test_12_publish_personal_preserves_existing_payload(self):
        data = self.results["publishPersonal"]
        payload = data["payload"]
        self.assertEqual(data["calls"], 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["community"], "Personal (Feed)")
        self.assertEqual(payload["community_id"], "")
        self.assertEqual(payload["primary_community_id"], "")
        self.assertEqual(payload["context_community_id"], "")
        self.assertEqual(payload["cluster_id"], "")
        self.assertEqual(payload["mainImg"], "data:image/jpeg;base64,MAIN")
        self.assertEqual(payload["pipImg"], "data:image/jpeg;base64,PIP")

    def test_13_publish_community_preserves_existing_payload(self):
        data = self.results["publishCommunity"]
        payload = data["payload"]
        self.assertEqual(data["calls"], 1)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["community"], "Community 02")
        self.assertEqual(payload["community_id"], "comm_02")
        self.assertEqual(payload["primary_community_id"], "comm_02")
        self.assertEqual(payload["context_community_id"], "")
        self.assertEqual(payload["cluster_id"], "")
        self.assertNotIn("comm_01", json.dumps(payload))

    def test_14_new_review_setup_refreshes_memberships(self):
        data = self.results["refresh"]
        self.assertEqual(data["firstJoined"], 1)
        self.assertEqual(data["secondJoined"], 2)
        self.assertEqual(data["calls"], 2)
        self.assertEqual(data["communityButtons"], 1)
        self.assertEqual(data["pickerRows"], 2)
        self.assertTrue(data["hasNewCommunity"])

    def test_15_retake_preserves_valid_destination(self):
        data = self.results["retake"]
        self.assertEqual(data["mode"], "community")
        self.assertEqual(data["activeId"], "comm_02")
        self.assertEqual(data["selectedName"], "Community 02")
        self.assertIsNone(data["capturedMomentData"])
        self.assertEqual(data["afterSetupMode"], "community")
        self.assertEqual(data["afterSetupSelected"], "Community 02")

    def test_16_close_review_clears_destination(self):
        data = self.results["close"]
        self.assertEqual(data["mode"], "personal")
        self.assertIsNone(data["activeId"])
        self.assertIsNone(data["selectedName"])
        self.assertEqual(data["joined"], 0)
        self.assertIsNone(data["reviewContext"])
        self.assertEqual(data["cameraMode"], "NORMAL")

    def test_17_navigation_clears_destination(self):
        data = self.results["navigation"]
        self.assertEqual(data["mode"], "personal")
        self.assertIsNone(data["selectedName"])
        self.assertEqual(data["joined"], 0)
        self.assertIsNone(data["reviewContext"])
        self.assertEqual(data["cameraMode"], "NORMAL")

    def test_18_invalid_community_cannot_reach_publishing(self):
        data = self.results["invalidPublish"]
        self.assertEqual(data["selectMode"], "personal")
        self.assertTrue(data["selectToast"])
        self.assertIn("no longer available", data["selectToast"])
        self.assertEqual(data["publishCalls"], 0)
        self.assertIn("no longer available", data["publishToast"])

    def test_19_picker_markup_is_wired(self):
        with open(os.path.join(PROJECT_DIR, "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('id="reviewCommunityPickerModal"', html)
        self.assertIn('id="reviewCommunitySearchInput"', html)
        self.assertIn('id="reviewCommunityPickerList"', html)
        self.assertIn('oninput="filterReviewCommunityPicker(this.value)"', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
