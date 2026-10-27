#!/usr/bin/env node
/*
 * Behavioral coverage for the feed cursor / infinite-scroll frontend.
 *
 * The real renderFeedCards, loadFeedMoments, setupFeedInfiniteScroll and
 * loadMoreFeedMoments functions are sliced out of app_core.js and executed in
 * a minimal DOM. apiRequest is a deferred promise, so completion order and
 * concurrent calls are controlled exactly.
 *
 * This is a DOM-sandbox/logic test, not a live browser or real-device test.
 */

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");
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
  const start = SRC.indexOf(startMarker);
  if (start < 0) throw new Error("Missing start marker: " + startMarker);
  const end = SRC.indexOf(endMarker, start);
  if (end < 0) throw new Error("Missing end marker: " + endMarker);
  return SRC.slice(start, end);
}

const HELPERS = sliceBetween("function _feedApiCircle(circle) {", "async function loadFeedMoments(circle, isRefresh) {");
const LOAD = sliceBetween("async function loadFeedMoments(circle, isRefresh) {", "function formatPostTime(createdStr) {");
const RENDER = sliceBetween("function renderFeedCards(moments, container, options) {", "function attachCardInteractions(card, momentData) {");

// ── Minimal DOM ─────────────────────────────────────────────────────────
function makeElement(tag) {
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    id: "",
    className: "",
    dataset: {},
    style: {},
    parentNode: null,
    children: [],
    _html: "",
    _listeners: {},
    addEventListener: function(name, fn) {
      el._listeners[name] = el._listeners[name] || [];
      el._listeners[name].push(fn);
    },
    removeEventListener: function() {},
    setAttribute: function() {},
    getAttribute: function() { return null; },
    removeAttribute: function() {},
    closest: function() { return null; },
    appendChild: function(child) {
      if (child.parentNode && child.parentNode !== el) {
        child.parentNode.children = child.parentNode.children.filter(function(c) { return c !== child; });
      }
      child.parentNode = el;
      el.children.push(child);
      return child;
    },
    querySelector: function(selector) {
      if (selector === "#feedScrollSentinel") {
        return el.children.filter(function(c) { return c.id === "feedScrollSentinel"; })[0] || null;
      }
      return null;
    },
    querySelectorAll: function(selector) {
      if (selector === "[data-post-id]") {
        return el.children.filter(function(c) { return c.dataset && c.dataset.postId; });
      }
      return [];
    },
  };
  Object.defineProperty(el, "innerHTML", {
    get: function() { return el._html; },
    set: function(value) {
      el._html = String(value);
      el.children.forEach(function(c) { c.parentNode = null; });
      el.children = [];
    },
  });
  return el;
}

function makeClassList() {
  const set = new Set();
  return {
    add: function() { for (let i = 0; i < arguments.length; i++) set.add(arguments[i]); },
    remove: function() { for (let i = 0; i < arguments.length; i++) set.delete(arguments[i]); },
    contains: function(c) { return set.has(c); },
  };
}

function makeDocument() {
  const byId = new Map();
  return {
    hidden: false,
    _byId: byId,
    getElementById: function(id) {
      if (!byId.has(id)) {
        const el = makeElement("div");
        el.id = id;
        el.classList = makeClassList();
        byId.set(id, el);
      }
      return byId.get(id);
    },
    createElement: function(tag) { return makeElement(tag); },
    querySelectorAll: function() { return []; },
    addEventListener: function() {},
  };
}

function makeStorage() {
  const data = new Map();
  return {
    getItem: function(key) { return data.has(key) ? data.get(key) : null; },
    setItem: function(key, value) { data.set(key, String(value)); },
    removeItem: function(key) { data.delete(key); },
    clear: function() { data.clear(); },
    _data: data,
  };
}

function makeIO() {
  const instances = [];
  function MockIO(callback, options) {
    this.callback = callback;
    this.options = options || {};
    this.observed = [];
    this.disconnected = false;
    instances.push(this);
  }
  MockIO.prototype.observe = function(el) { this.observed.push(el); };
  MockIO.prototype.disconnect = function() { this.disconnected = true; };
  MockIO.prototype.trigger = function(isIntersecting) {
    this.callback([{ isIntersecting: Boolean(isIntersecting) }]);
  };
  MockIO.instances = instances;
  return MockIO;
}

function makeApi() {
  const calls = [];
  function apiRequest(url) {
    let resolve;
    const promise = new Promise(function(r) { resolve = r; });
    calls.push({ url: url, promise: promise, resolve: resolve });
    return promise;
  }
  apiRequest.calls = calls;
  apiRequest.last = function() { return calls[calls.length - 1]; };
  return apiRequest;
}

function flush() {
  return new Promise(function(resolve) { setImmediate(resolve); });
}

async function settle(call, value) {
  if (!call) throw new Error("settle() without a pending call");
  call.resolve(value);
  await flush();
  await flush();
}

function post(id) {
  return {
    id: id,
    author_handle: "tester",
    author_name: "Tester",
    caption: "caption " + id,
    created_at: "2026-01-01T12:00:00",
    main_img: "https://example.test/main_" + id + ".jpg",
    pip_img: "https://example.test/pip_" + id + ".jpg",
  };
}

function ids(container) {
  return container.children
    .filter(function(c) { return c.dataset && c.dataset.postId; })
    .map(function(c) { return c.dataset.postId; });
}

function createEnv() {
  const doc = makeDocument();
  const container = doc.getElementById("feedStreamContainer");
  doc.getElementById("mainViewport");
  const apiRequest = makeApi();
  const storage = makeStorage();
  const IOMock = makeIO();
  const state = { activeScreen: "feed", activeCircle: "foryou", momentCache: {} };
  const attachments = [];
  const windowObj = { KandidObservability: null };

  const env = {
    document: doc,
    window: windowObj,
    state: state,
    localStorage: storage,
    apiRequest: apiRequest,
    IntersectionObserver: IOMock,
    escapeHtml: function(v) { return String(v == null ? "" : v); },
    jsAttr: function(v) { return String(v == null ? "" : v); },
    formatTimeAgoClean: function() { return "JUST NOW"; },
    updateAllMomentTimestamps: function() {},
    attachCardInteractions: function(card, moment) { attachments.push({ card: card, moment: moment }); },
  };

  const body = [
    "var window = env.window;",
    "var document = env.document;",
    "var state = env.state;",
    "var localStorage = env.localStorage;",
    "var apiRequest = env.apiRequest;",
    "var IntersectionObserver = env.IntersectionObserver;",
    "var escapeHtml = env.escapeHtml;",
    "var jsAttr = env.jsAttr;",
    "var formatTimeAgoClean = env.formatTimeAgoClean;",
    "var updateAllMomentTimestamps = env.updateAllMomentTimestamps;",
    "var attachCardInteractions = env.attachCardInteractions;",
    HELPERS,
    LOAD,
    RENDER,
    "return { renderFeedCards: renderFeedCards, loadFeedMoments: loadFeedMoments, loadMoreFeedMoments: loadMoreFeedMoments, setupFeedInfiniteScroll: setupFeedInfiniteScroll, _feedEnsureState: _feedEnsureState };",
  ].join("\n");

  const act = new Function("env", body)(env);
  return {
    document: doc,
    container: container,
    apiRequest: apiRequest,
    storage: storage,
    state: state,
    attachments: attachments,
    IO: IOMock,
    window: windowObj,
    act: act,
  };
}

(async function run() {
  console.log("\n=== FEED INFINITE-SCROLL FRONTEND TESTS ===");

  // ── 1. Append preserves existing cards and attaches new interactions ──
  console.log("\n--- 1. Append mode ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1"), post("p2")], t.container, { append: false, circle: "foryou" });
    check("first page renders both cards", ids(t.container).join(",") === "p1,p2", ids(t.container).join(","));
    check("first page attaches interactions", t.attachments.length === 2, String(t.attachments.length));
    const originalFirst = t.container.children[0];

    t.act.renderFeedCards([post("p2"), post("p3")], t.container, { append: true, circle: "foryou" });
    check("append does not clear previous cards", ids(t.container).join(",") === "p1,p2,p3", ids(t.container).join(","));
    check("append preserves the original DOM node", t.container.children[0] === originalFirst);
    check("append attaches only the newly added card", t.attachments.length === 3, String(t.attachments.length));
    check("appended card gets the new moment", t.attachments[2].moment.id === "p3");
  }

  // ── 2. Deduplication even if loadedIds was lost ───────────────────────
  console.log("\n--- 2. Deduplication ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1"), post("p2")], t.container, { append: false, circle: "foryou" });
    t.state.feedState.foryou.loadedIds = new Set();
    t.act.renderFeedCards([post("p1"), post("p2"), post("p4")], t.container, { append: true, circle: "foryou" });
    check("already-rendered post IDs are not duplicated in the DOM", ids(t.container).join(",") === "p1,p2,p4", ids(t.container).join(","));
    check("only p4 is attached again", t.attachments.length === 3, String(t.attachments.length));

    t.act.renderFeedCards([post("p9")], t.container, { append: false, circle: "foryou" });
    check("non-append render resets the list", ids(t.container).join(",") === "p9", ids(t.container).join(","));
    check("reset render updates loadedIds", t.state.feedState.foryou.loadedIds.has("p9") && !t.state.feedState.foryou.loadedIds.has("p1"));
  }

  // ── 3. First page: cache paint then network reconciliation ───────────
  console.log("\n--- 3. First-page cache/reconciliation ---");
  {
    const t = createEnv();
    t.storage.setItem("kandid_feed_cache_foryou", JSON.stringify({
      success: true,
      feed: [post("c1"), post("c2")],
      next_cursor: "",
      has_more: false,
    }));

    const pending = t.act.loadFeedMoments("foryou");
    check("cache paints synchronously before the network resolves", ids(t.container).join(",") === "c1,c2", ids(t.container).join(","));
    check("first-page request includes a 20-row limit",
      t.apiRequest.last().url === "/api/feed?circle=all&limit=20", t.apiRequest.last().url);

    await settle(t.apiRequest.last(), {
      success: true,
      feed: [post("c1"), post("c2")],
      next_cursor: "cursor-1",
      has_more: true,
    });
    await pending;
    check("first page stores the next cursor", t.state.feedState.foryou.nextCursor === "cursor-1", t.state.feedState.foryou.nextCursor);
    check("first page stores hasMore", t.state.feedState.foryou.hasMore === true);
    check("first page keeps the two cards and adds a sentinel", ids(t.container).join(",") === "c1,c2" && Boolean(t.container.querySelector("#feedScrollSentinel")));
    check("sentinel is the last child", t.container.children[t.container.children.length - 1].id === "feedScrollSentinel");
    const cached = JSON.parse(t.storage.getItem("kandid_feed_cache_foryou"));
    check("cache contains the first 20 moments", cached.feed.length === 2 && cached.next_cursor === "cursor-1");
  }

  // ── 4. loadMore concurrency guard and append ──────────────────────────
  console.log("\n--- 4. loadMore guard and append ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1"), post("p2")], t.container, { append: false, circle: "foryou" });
    const s = t.act._feedEnsureState("foryou");
    s.nextCursor = "cursor-1";
    s.hasMore = true;
    t.act.setupFeedInfiniteScroll(t.container, "foryou");

    const first = t.act.loadMoreFeedMoments("foryou");
    check("loadMore issues exactly one request", t.apiRequest.calls.length === 1, String(t.apiRequest.calls.length));
    check("loadMore marks loading", s.isLoading === true);
    check("loading state is shown in the sentinel", t.container.querySelector("#feedScrollSentinel").innerHTML.indexOf("LOADING MORE MOMENTS") >= 0);

    const duplicate = t.act.loadMoreFeedMoments("foryou");
    check("concurrent loadMore is ignored", t.apiRequest.calls.length === 1, String(t.apiRequest.calls.length));
    await duplicate;

    const call = t.apiRequest.last();
    check("next-page URL carries the encoded cursor and limit",
      call.url === "/api/feed?circle=all&limit=20&cursor=cursor-1", call.url);

    await settle(call, {
      success: true,
      feed: [post("p2"), post("p5")],
      next_cursor: "cursor-2",
      has_more: true,
    });
    await first;
    check("next page appends new cards without duplicates", ids(t.container).join(",") === "p1,p2,p5", ids(t.container).join(","));
    check("next page advances the cursor", s.nextCursor === "cursor-2", s.nextCursor);
    check("next page keeps hasMore true", s.hasMore === true);
    check("loading flag is cleared after completion", s.isLoading === false);
    check("sentinel stays below the appended card", t.container.children[t.container.children.length - 1].id === "feedScrollSentinel");
  }

  // ── 5. Terminal page shows caught-up and stops further calls ──────────
  console.log("\n--- 5. End of feed ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1")], t.container, { append: false, circle: "foryou" });
    const s = t.act._feedEnsureState("foryou");
    s.nextCursor = "cursor-2";
    s.hasMore = true;
    t.act.setupFeedInfiniteScroll(t.container, "foryou");

    const pending = t.act.loadMoreFeedMoments("foryou");
    await settle(t.apiRequest.last(), {
      success: true,
      feed: [post("p6")],
      next_cursor: "",
      has_more: false,
    });
    await pending;
    check("terminal page is appended", ids(t.container).join(",") === "p1,p6", ids(t.container).join(","));
    check("hasMore becomes false", s.hasMore === false);
    check("caught-up indicator is rendered",
      t.container.querySelector("#feedScrollSentinel").innerHTML.indexOf("ALL CAUGHT UP") >= 0);
    const callsBefore = t.apiRequest.calls.length;
    await t.act.loadMoreFeedMoments("foryou");
    check("further loadMore is a no-op at the end", t.apiRequest.calls.length === callsBefore);
  }

  // ── 6. A late page from another circle cannot mutate the new view ─────
  console.log("\n--- 6. Navigation/context guard ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1")], t.container, { append: false, circle: "foryou" });
    const s = t.act._feedEnsureState("foryou");
    s.nextCursor = "cursor-3";
    s.hasMore = true;
    t.act.setupFeedInfiniteScroll(t.container, "foryou");

    const pending = t.act.loadMoreFeedMoments("foryou");
    t.state.activeCircle = "campus";
    await settle(t.apiRequest.last(), {
      success: true,
      feed: [post("late")],
      next_cursor: "cursor-4",
      has_more: true,
    });
    await pending;
    check("a page from the old circle is not appended", ids(t.container).indexOf("late") === -1, ids(t.container).join(","));
    check("the late response does not leave isLoading stuck", s.isLoading === false);
    check("the late response does not replace the old cursor", s.nextCursor === "cursor-3", s.nextCursor);
  }

  // ── 7. Failure keeps the cursor and reports a retry state ─────────────
  console.log("\n--- 7. Next-page failure ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1")], t.container, { append: false, circle: "foryou" });
    const s = t.act._feedEnsureState("foryou");
    s.nextCursor = "cursor-5";
    s.hasMore = true;
    t.act.setupFeedInfiniteScroll(t.container, "foryou");

    const pending = t.act.loadMoreFeedMoments("foryou");
    await settle(t.apiRequest.last(), { success: false, error: "network" });
    await pending;
    check("failure clears loading", s.isLoading === false);
    check("failure does not discard the cursor", s.nextCursor === "cursor-5", s.nextCursor);
    check("failure keeps the current cards", ids(t.container).join(",") === "p1", ids(t.container).join(","));
    check("retry message is shown",
      t.container.querySelector("#feedScrollSentinel").innerHTML.indexOf("COULDN") >= 0);
  }

  // ── 8. IntersectionObserver wiring ────────────────────────────────────
  console.log("\n--- 8. Sentinel observer ---");
  {
    const t = createEnv();
    t.act.renderFeedCards([post("p1")], t.container, { append: false, circle: "foryou" });
    const s = t.act._feedEnsureState("foryou");
    s.nextCursor = "cursor-io";
    s.hasMore = true;
    t.act.setupFeedInfiniteScroll(t.container, "foryou");
    const io = t.IO.instances[t.IO.instances.length - 1];
    check("IntersectionObserver is created", Boolean(io));
    check("observer uses a 400px root margin", io.options.rootMargin === "400px", io.options.rootMargin);
    check("observer uses the 0.1 threshold", io.options.threshold === 0.1, String(io.options.threshold));
    check("observer watches the sentinel", io.observed.length === 1 && io.observed[0].id === "feedScrollSentinel");
    const before = t.apiRequest.calls.length;
    io.trigger(true);
    await flush();
    check("observer triggers the next page", t.apiRequest.calls.length === before + 1);
  }

  // ── 9. Empty first page remains a valid empty state ──────────────────
  console.log("\n--- 9. Empty first page ---");
  {
    const t = createEnv();
    const pending = t.act.loadFeedMoments("foryou");
    check("no-cache first load renders the skeleton", t.container.innerHTML.indexOf("animate-pulse") >= 0);
    await settle(t.apiRequest.last(), { success: true, feed: [], next_cursor: "", has_more: false });
    await pending;
    check("empty first page keeps an empty state", t.container.innerHTML.indexOf("Your Canvas is Empty") >= 0);
    check("empty first page has no cursor", t.state.feedState.foryou.nextCursor === "");
    check("empty first page disables hasMore", t.state.feedState.foryou.hasMore === false);
  }

  console.log("\n" + (checks - failures) + "/" + checks + " checks passed");
  if (failures > 0) process.exit(1);
})().catch(function(err) {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
