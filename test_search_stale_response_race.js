#!/usr/bin/env node
/*
 * Behavioral tests for the Search stale-response race.
 *
 * The real search functions (performSearch, handleSearchInput, clearSearchInput,
 * selectSearchCategory, loadSearchDiscovery, switchScreenView) are sliced out of
 * app_core.js and executed in a minimal DOM sandbox. apiRequest is replaced by a
 * deferred promise so request completion order is fully controlled.
 *
 * Run: node test_search_stale_response_race.js
 */

const fs = require("fs");
const path = require("path");

const SRC_APP = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");

let failures = 0;
let checks = 0;

function check(name, cond, detail) {
  checks++;
  if (cond) {
    console.log("  PASS " + name);
  } else {
    console.log("  FAIL " + name + (detail ? "  [" + detail + "]" : ""));
    failures++;
  }
}

function sliceBetween(startMarker, endMarker) {
  const start = SRC_APP.indexOf(startMarker);
  if (start < 0) throw new Error("Missing start marker: " + startMarker);
  const end = SRC_APP.indexOf(endMarker, start);
  if (end < 0) throw new Error("Missing end marker: " + endMarker);
  return SRC_APP.slice(start, end + endMarker.length);
}

function sliceUntil(startMarker, endMarker) {
  const start = SRC_APP.indexOf(startMarker);
  if (start < 0) throw new Error("Missing start marker: " + startMarker);
  const end = SRC_APP.indexOf(endMarker, start);
  if (end < 0) throw new Error("Missing end marker: " + endMarker);
  return SRC_APP.slice(start, end);
}

// Extracted source blocks — a missing guard makes extraction (and this suite) fail.
const BLOCKS = {
  token: sliceBetween("// Monotonic identity of the newest search.", "var _searchRequestToken = 0;"),
  showView: sliceBetween("function _searchShowView(viewName) {", "window._searchShowView = _searchShowView;"),
  invalidate: sliceBetween("function _invalidatePendingSearch() {", "window._invalidatePendingSearch = _invalidatePendingSearch;"),
  categories: sliceBetween("function selectSearchCategory(cat) {", "window.selectSearchFilter = selectSearchCategory;"),
  categoryResults: sliceUntil("function _displayCategoryResults(cat) {", "function handleSearchInput(event) {"),
  input: sliceBetween("function handleSearchInput(event) {", "window.handleSearchInput = handleSearchInput;"),
  clear: sliceBetween("function clearSearchInput() {", "window.clearSearchInput = clearSearchInput;"),
  discovery: sliceBetween("var _isLoadingSearchDiscovery = false;", "window.loadSearchDiscovery = loadSearchDiscovery;"),
  perform: sliceBetween("async function performSearch(query, category) {", "window.performSearch = performSearch;"),
  switchScreen: sliceBetween("function switchScreenView(screenName) {", "window.switchScreenView = switchScreenView;"),
};

// ── Minimal DOM ───────────────────────────────────────────────────────
function makeClassList() {
  const set = new Set();
  return {
    add: function() { for (let i = 0; i < arguments.length; i++) set.add(arguments[i]); },
    remove: function() { for (let i = 0; i < arguments.length; i++) set.delete(arguments[i]); },
    contains: function(c) { return set.has(c); },
    toggle: function(c, force) {
      const on = force === undefined ? !set.has(c) : Boolean(force);
      if (on) set.add(c); else set.delete(c);
      return on;
    },
  };
}

function makeElement(id) {
  const el = {
    id: id,
    style: {},
    className: "",
    textContent: "",
    value: "",
    attributes: {},
    children: [],
    classList: makeClassList(),
    addEventListener: function() {},
    removeEventListener: function() {},
    appendChild: function(child) { el.children.push(child); return child; },
    setAttribute: function(k, v) { el.attributes[k] = String(v); },
    getAttribute: function(k) { return Object.prototype.hasOwnProperty.call(el.attributes, k) ? el.attributes[k] : null; },
    removeAttribute: function(k) { delete el.attributes[k]; },
    querySelector: function() { return null; },
    closest: function() { return null; },
  };
  let html = "";
  Object.defineProperty(el, "innerHTML", {
    get: function() { return html; },
    set: function(v) { html = String(v); if (html === "") el.children.length = 0; },
  });
  return el;
}

function makeDocument() {
  const byId = new Map();
  return {
    hidden: false,
    _byId: byId,
    getElementById: function(id) {
      if (!byId.has(id)) byId.set(id, makeElement(id));
      return byId.get(id);
    },
    createElement: function(tag) { return makeElement(tag); },
    querySelectorAll: function() { return []; },
    addEventListener: function() {},
    removeEventListener: function() {},
  };
}

const VIEW_IDS = [
  "view-idle", "view-focused", "view-res-people", "view-res-moments",
  "view-res-places", "view-res-communities", "view-loading", "view-error", "view-empty",
];
const VIEW_NAMES = {
  "view-idle": "idle", "view-focused": "focused", "view-res-people": "people",
  "view-res-moments": "moments", "view-res-places": "places",
  "view-res-communities": "communities", "view-loading": "loading",
  "view-error": "error", "view-empty": "empty",
};

function visibleViews(doc) {
  return VIEW_IDS
    .filter(function(id) { return !doc.getElementById(id).classList.contains("hidden"); })
    .map(function(id) { return VIEW_NAMES[id]; });
}

// ── Deferred apiRequest ───────────────────────────────────────────────
function makeApi() {
  const calls = [];
  function apiRequest(endpoint) {
    let resolve;
    const promise = new Promise(function(r) { resolve = r; });
    calls.push({ endpoint: endpoint, promise: promise, resolve: resolve, resolved: false });
    return promise;
  }
  apiRequest.calls = calls;
  apiRequest.searchCalls = function() {
    return calls.filter(function(c) { return c.endpoint.indexOf("/api/search?q=") === 0; });
  };
  apiRequest.discoveryCalls = function() {
    return calls.filter(function(c) { return c.endpoint === "/api/search?type=all"; });
  };
  apiRequest.lastSearch = function() {
    const list = apiRequest.searchCalls();
    return list[list.length - 1];
  };
  apiRequest.lastDiscovery = function() {
    const list = apiRequest.discoveryCalls();
    return list[list.length - 1];
  };
  return apiRequest;
}

function flush() {
  return new Promise(function(r) { setImmediate(r); });
}

async function settle(call, value) {
  if (!call) throw new Error("settle() called without a pending request");
  call.resolved = true;
  call.resolve(value);
  await flush();
}

// Mirrors the real call path: the input handler stores the query in state
// before performSearch() is invoked.
function startSearch(t, query, category) {
  t.state.searchQuery = String(query == null ? "" : query).trim();
  return t.act.performSearch(query, category);
}

function searchData(tag) {
  return {
    success: true,
    people: [{ id: tag + "-p1", name: "Person " + tag, handle: "person_" + tag }],
    moments: [{ id: tag + "-m1", caption: "Moment " + tag }],
    places: [{ id: tag + "-pl1", name: "Place " + tag }],
    communities: [{ id: tag + "-c1", name: "Community " + tag }],
  };
}

function emptySearchData() {
  return { success: true, people: [], moments: [], places: [], communities: [] };
}

// ── Sandbox ───────────────────────────────────────────────────────────
function createEnv() {
  const doc = makeDocument();
  const apiRequest = makeApi();
  const state = {
    activeScreen: "search",
    searchQuery: "",
    searchCategory: "people",
    searchFocused: false,
    lastSearchResults: null,
    lastSearchResultsQuery: "",
  };
  const renders = { people: null, moments: null, places: null, communities: null };
  const saved = [];

  const env = {
    document: doc,
    apiRequest: apiRequest,
    state: state,
    closeSearchActivitySheet: function() {},
    loadRadar: function() {},
    escapeHtml: function(v) { return String(v == null ? "" : v); },
    saveRecentSearch: function(q, c) { saved.push({ q: q, c: c }); },
    renderPeopleSearchResults: function(list) { renders.people = list; },
    renderMomentsSearchResults: function(list) { renders.moments = list; },
    renderPlacesSearchResults: function(list) { renders.places = list; },
    renderCommunitiesSearchResults: function(list) { renders.communities = list; },
    closeChatPhotoViewer: function() {},
    ChatPhotoCache: { detachDomReferences: function() {}, clearAll: function() {} },
    hydrateChatPhotos: function() {},
    handleNewUserFeedEntry: function() {},
    handleNewUserFeedExit: function() {},
    loadChatConversations: function() {},
    loadYouScreen: function() {},
    loadMemoriesScreen: function() {},
    loadProgressScreen: function() {},
    loadSettingsScreen: function() {},
    loadNotifications: function() {},
    loadBlockList: function() {},
    loadRecentlyDeletedScreen: function() {},
    loadChatNewSuggestions: function() {},
  };

  const body = [
    "var window = {};",
    "var document = env.document;",
    "var state = env.state;",
    "var searchDebounceTimer = null;",
    "var searchAbortCtrl = null;",
    "var apiRequest = env.apiRequest;",
    "var closeSearchActivitySheet = env.closeSearchActivitySheet;",
    "var loadRadar = env.loadRadar;",
    "var escapeHtml = env.escapeHtml;",
    "var saveRecentSearch = env.saveRecentSearch;",
    "var renderPeopleSearchResults = env.renderPeopleSearchResults;",
    "var renderMomentsSearchResults = env.renderMomentsSearchResults;",
    "var renderPlacesSearchResults = env.renderPlacesSearchResults;",
    "var renderCommunitiesSearchResults = env.renderCommunitiesSearchResults;",
    "var closeChatPhotoViewer = env.closeChatPhotoViewer;",
    "var ChatPhotoCache = env.ChatPhotoCache;",
    "var hydrateChatPhotos = env.hydrateChatPhotos;",
    "var handleNewUserFeedEntry = env.handleNewUserFeedEntry;",
    "var handleNewUserFeedExit = env.handleNewUserFeedExit;",
    "var loadChatConversations = env.loadChatConversations;",
    "var loadYouScreen = env.loadYouScreen;",
    "var loadMemoriesScreen = env.loadMemoriesScreen;",
    "var loadProgressScreen = env.loadProgressScreen;",
    "var loadSettingsScreen = env.loadSettingsScreen;",
    "var loadNotifications = env.loadNotifications;",
    "var loadBlockList = env.loadBlockList;",
    "var loadRecentlyDeletedScreen = env.loadRecentlyDeletedScreen;",
    "var loadChatNewSuggestions = env.loadChatNewSuggestions;",
    BLOCKS.token,
    BLOCKS.showView,
    BLOCKS.invalidate,
    BLOCKS.categories,
    BLOCKS.categoryResults,
    BLOCKS.input,
    BLOCKS.clear,
    BLOCKS.discovery,
    BLOCKS.perform,
    BLOCKS.switchScreen,
    "return { performSearch: performSearch, handleSearchInput: handleSearchInput, clearSearchInput: clearSearchInput, selectSearchCategory: selectSearchCategory, loadSearchDiscovery: loadSearchDiscovery, switchScreenView: switchScreenView, _searchShowView: _searchShowView, _invalidatePendingSearch: _invalidatePendingSearch };",
  ].join("\n");

  const act = new Function("env", body)(env);
  return { document: doc, apiRequest: apiRequest, state: state, renders: renders, saved: saved, act: act };
}

(async function run() {
  console.log("\n=== SEARCH STALE-RESPONSE RACE TESTS ===");

  // ── 1. Reversed completion order ───────────────────────────────────
  console.log("\n--- 1. Reversed completion (A starts, B starts, B resolves, then A) ---");
  {
    const t = createEnv();
    const dataA = searchData("A");
    const dataB = searchData("B");

    startSearch(t, "alpha", "people");
    const callA = t.apiRequest.lastSearch();
    startSearch(t, "beta", "places");
    const callB = t.apiRequest.lastSearch();

    check("both searches issued their own request",
      callA !== callB && t.apiRequest.searchCalls().length === 2);
    check("newest search owns the loading view",
      visibleViews(t.document).join(",") === "loading", visibleViews(t.document).join(","));

    await settle(callB, dataB);
    check("newest response is stored", t.state.lastSearchResults === dataB);
    check("newest response shows the requested category view",
      visibleViews(t.document).join(",") === "places", visibleViews(t.document).join(","));
    check("newest response selects the requested category", t.state.searchCategory === "places");

    await settle(callA, dataA);
    check("stale response cannot overwrite newer results", t.state.lastSearchResults === dataB);
    check("stale response cannot restore its old category view",
      visibleViews(t.document).join(",") === "places", visibleViews(t.document).join(","));
    check("stale response cannot reset the category selection", t.state.searchCategory === "places");
    check("stale payload never reached the renderers",
      t.renders.places === dataB.places && t.renders.people === dataB.people);
    check("only the newest search is written to recent searches",
      t.saved.length === 1 && t.saved[0].q === "beta", JSON.stringify(t.saved));
  }

  // ── 1b. Stale completes while the newer request is still loading ───
  console.log("\n--- 1b. Stale completion while the newer request is still pending ---");
  {
    const t = createEnv();
    startSearch(t, "first", "people");
    const first = t.apiRequest.lastSearch();
    startSearch(t, "second", "people");
    const second = t.apiRequest.lastSearch();

    await settle(first, searchData("STALE"));
    check("stale completion cannot clear the newer request's loading view",
      visibleViews(t.document).join(",") === "loading", visibleViews(t.document).join(","));
    check("stale completion stores nothing while newer request is pending",
      t.state.lastSearchResults === null && t.renders.people === null);

    const fresh = searchData("FRESH");
    await settle(second, fresh);
    check("newer request still renders after the stale completion",
      t.state.lastSearchResults === fresh && visibleViews(t.document).join(",") === "people");
  }

  // ── 1c. Query text edited during the debounce gap ──────────────────
  console.log("\n--- 1c. Query edited while the request is in flight (debounce gap) ---");
  {
    const t = createEnv();
    startSearch(t, "alpha", "people");
    const pending = t.apiRequest.lastSearch();

    // The user keeps typing. The box now holds a new value, but the 300ms
    // debounce has not fired, so no newer request exists yet.
    t.act.handleSearchInput({ target: { value: "alpha beta" } });
    await settle(pending, searchData("OLD"));
    check("result is dropped when the query text has moved on",
      t.state.lastSearchResults === null && t.renders.people === null);
    check("dropped result cannot change the visible view",
      visibleViews(t.document).join(",") === "loading", visibleViews(t.document).join(","));
    t.act.clearSearchInput(); // cancels the pending debounce timer
  }

  // ── 1d. Same query text, different request identity ────────────────
  console.log("\n--- 1d. Repeated search with unchanged query text ---");
  {
    const t = createEnv();
    startSearch(t, "same", "people");
    const first = t.apiRequest.lastSearch();
    startSearch(t, "same", "places");
    const second = t.apiRequest.lastSearch();
    check("identical query still issues distinct requests", first !== second);

    const fresh = searchData("SECOND");
    await settle(second, fresh);
    await settle(first, searchData("FIRST"));
    check("older duplicate request cannot overwrite newer results for the same query",
      t.state.lastSearchResults === fresh);
    check("older duplicate request cannot pull the view back",
      t.state.searchCategory === "places" && visibleViews(t.document).join(",") === "places",
      visibleViews(t.document).join(","));
  }

  // ── 2. Query cleared, discovery rendered, stale response arrives ───
  console.log("\n--- 2. Query cleared before the response arrives ---");
  {
    const t = createEnv();
    startSearch(t, "campus", "people");
    const stale = t.apiRequest.lastSearch();

    t.act.clearSearchInput();
    const discovery = t.apiRequest.lastDiscovery();
    check("clearing the input starts the discovery load", Boolean(discovery));
    check("clearing the input shows the idle view immediately",
      visibleViews(t.document).join(",") === "idle");

    await settle(discovery, { success: true, sectors: [{ name: "Library" }] });
    const around = t.document.getElementById("searchAroundYouContainer");
    const discoveryCards = around.children.length;
    check("discovery view rendered its content", discoveryCards === 1, String(discoveryCards));

    await settle(stale, searchData("STALE"));
    check("stale query result cannot overwrite the discovery state",
      t.state.lastSearchResults === null);
    check("stale query result cannot replace the discovery view",
      visibleViews(t.document).join(",") === "idle", visibleViews(t.document).join(","));
    check("stale query result leaves discovery content untouched",
      around.children.length === discoveryCards && around.innerHTML === "");
    check("stale query result never reached the renderers",
      t.renders.people === null && t.renders.places === null);
  }

  // ── 2b. Query cleared by deleting the text ─────────────────────────
  console.log("\n--- 2b. Query cleared by editing the input to empty ---");
  {
    const t = createEnv();
    t.state.searchQuery = "typing";
    startSearch(t, "typing", "people");
    const stale = t.apiRequest.lastSearch();

    t.act.handleSearchInput({ target: { value: "" } });
    check("empty input returns to the idle view",
      visibleViews(t.document).join(",") === "idle");

    await settle(stale, searchData("EDIT"));
    check("stale result cannot resurrect a cleared query",
      t.state.lastSearchResults === null && visibleViews(t.document).join(",") === "idle");
  }

  // ── 3. Stale failure arrives after the newest success ──────────────
  console.log("\n--- 3. Stale failure after a newer success ---");
  {
    const t = createEnv();
    startSearch(t, "slow", "people");
    const slow = t.apiRequest.lastSearch();
    startSearch(t, "fast", "moments");
    const fast = t.apiRequest.lastSearch();

    const good = searchData("GOOD");
    await settle(fast, good);
    await settle(slow, { success: false, error: "network down" });

    check("stale failure cannot replace valid newer results",
      t.state.lastSearchResults === good);
    check("stale failure cannot show the error view",
      visibleViews(t.document).join(",") === "moments", visibleViews(t.document).join(","));
    check("stale failure cannot reset the selected category", t.state.searchCategory === "moments");
  }

  // ── 4. Category changed while the request is in flight ─────────────
  console.log("\n--- 4. Category changed during the request ---");
  {
    const t = createEnv();
    t.state.lastSearchResults = searchData("CACHED");
    startSearch(t, "park", "people");
    const pending = t.apiRequest.lastSearch();

    t.act.selectSearchCategory("places");
    check("category switch during loading does not fire a duplicate request",
      t.apiRequest.searchCalls().length === 1, String(t.apiRequest.searchCalls().length));
    check("category switch shows the chosen category view",
      visibleViews(t.document).join(",") === "places", visibleViews(t.document).join(","));

    const fresh = searchData("FRESH");
    await settle(pending, fresh);
    check("late response keeps the user's chosen category", t.state.searchCategory === "places");
    check("late response cannot restore the request-time category view",
      visibleViews(t.document).join(",") === "places", visibleViews(t.document).join(","));
    check("late response still refreshes the result data", t.state.lastSearchResults === fresh);
  }

  // ── 4b. Explicit category search keeps its requested tab ───────────
  console.log("\n--- 4b. Explicit-category search (e.g. frequency filter) ---");
  {
    const t = createEnv();
    t.state.searchCategory = "people";
    startSearch(t, "golden hour", "moments");
    const pending = t.apiRequest.lastSearch();
    await settle(pending, searchData("FREQ"));
    check("explicit category request still opens that category",
      visibleViews(t.document).join(",") === "moments", visibleViews(t.document).join(","));
    check("explicit category request updates the selected category",
      t.state.searchCategory === "moments");
  }

  // ── 5. Navigation away while a request is pending ──────────────────
  console.log("\n--- 5. Navigating away from Search while pending ---");
  {
    const t = createEnv();
    t.state.activeScreen = "search";
    startSearch(t, "navigate", "people");
    const pending = t.apiRequest.lastSearch();

    t.act.switchScreenView("feed");
    check("navigation leaves the Search screen", t.state.activeScreen === "feed");

    await settle(pending, searchData("NAV"));
    check("completion after navigation stores nothing", t.state.lastSearchResults === null);
    check("completion after navigation renders nothing",
      t.renders.people === null && t.renders.places === null);
    check("completion after navigation shows no error or results view",
      ["error", "people", "moments", "places", "communities", "empty"]
        .indexOf(visibleViews(t.document)[0]) === -1, visibleViews(t.document).join(","));

    // Coming back must not leave the user on a dead loading view.
    t.act.switchScreenView("search");
    const resumed = t.apiRequest.lastSearch();
    check("re-entering Search resumes the cancelled query",
      Boolean(resumed) && resumed !== pending);
    const resumedData = searchData("RESUMED");
    await settle(resumed, resumedData);
    check("resumed search renders its results",
      t.state.lastSearchResults === resumedData && visibleViews(t.document).join(",") === "people",
      visibleViews(t.document).join(","));
  }

  // ── 6. Current (non-stale) search behaviour is preserved ───────────
  console.log("\n--- 6. Current search behaviour ---");
  {
    const t = createEnv();
    startSearch(t, "valid", "people");
    check("current search shows the loading view",
      visibleViews(t.document).join(",") === "loading");
    const call = t.apiRequest.lastSearch();
    const data = searchData("VALID");
    await settle(call, data);
    check("current search stores and renders its results",
      t.state.lastSearchResults === data && t.renders.people === data.people);
    check("current search opens its category view",
      visibleViews(t.document).join(",") === "people");
    check("current search is saved to recents",
      t.saved.length === 1 && t.saved[0].q === "valid");
  }
  {
    const t = createEnv();
    startSearch(t, "nothing", "people");
    await settle(t.apiRequest.lastSearch(), emptySearchData());
    check("current search with zero results shows the empty view",
      visibleViews(t.document).join(",") === "empty", visibleViews(t.document).join(","));
  }
  {
    const t = createEnv();
    startSearch(t, "boom", "people");
    await settle(t.apiRequest.lastSearch(), { success: false, error: "server error" });
    check("current search failure shows the error view",
      visibleViews(t.document).join(",") === "error", visibleViews(t.document).join(","));
    check("current search failure stores no results", t.state.lastSearchResults === null);
  }
  {
    const t = createEnv();
    startSearch(t, "   ", "people");
    check("blank query short-circuits to idle plus discovery",
      visibleViews(t.document).join(",") === "idle" && t.apiRequest.discoveryCalls().length === 1);
  }

  // ── 7. loadSearchDiscovery protection unchanged ────────────────────
  console.log("\n--- 7. loadSearchDiscovery mutex and empty-state protection ---");
  {
    const t = createEnv();
    const p1 = t.act.loadSearchDiscovery();
    const p2 = t.act.loadSearchDiscovery();
    check("concurrent discovery loads collapse into one request",
      t.apiRequest.discoveryCalls().length === 1, String(t.apiRequest.discoveryCalls().length));

    await settle(t.apiRequest.lastDiscovery(), { success: false });
    const around = t.document.getElementById("searchAroundYouContainer");
    check("failed discovery still shows the quiet empty state",
      around.innerHTML.indexOf("TOO QUIET") !== -1, around.innerHTML);
    await Promise.all([p1, p2]);
  }
  {
    const t = createEnv();
    const around = t.document.getElementById("searchAroundYouContainer");
    around.appendChild(makeElement("existing-card"));
    const p = t.act.loadSearchDiscovery();
    await settle(t.apiRequest.lastDiscovery(), { success: false });
    check("failed discovery does not overwrite existing content",
      around.innerHTML.indexOf("TOO QUIET") === -1 && around.children.length === 1);
    await p;
  }
  {
    const t = createEnv();
    const p = t.act.loadSearchDiscovery();
    const people = [
      { id: "p1", name: "A", handle: "a" },
      { id: "p2", name: "B", handle: "b" },
      { id: "p3", name: "C", handle: "c" },
    ];
    await settle(t.apiRequest.lastDiscovery(), { success: true, people: people });
    const around = t.document.getElementById("searchAroundYouContainer");
    check("discovery renders suggested people cards", around.children.length === 3);
    await p;
    t.act.loadSearchDiscovery();
    check("discovery mutex releases after completion",
      t.apiRequest.discoveryCalls().length === 2);
  }

  console.log("\n=========================================");
  if (failures > 0) {
    console.log("TOTAL FAILURES: " + failures + " / " + checks + " checks");
    process.exit(1);
  }
  console.log("ALL SEARCH STALE-RESPONSE RACE TESTS PASSED (" + checks + " checks)");
  process.exit(0);
})().catch(function(err) {
  console.error("\nTEST HARNESS ERROR:", err && err.stack ? err.stack : err);
  process.exit(1);
});
