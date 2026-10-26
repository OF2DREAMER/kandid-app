#!/usr/bin/env node
/*
 * Focused frontend logic tests for the chat reliability upgrade.
 *
 * This is not a browser test. It executes the real cache/overlap helpers with
 * a small fake DOM and fake localStorage, then checks the source contracts that
 * wire optimistic sends, retries, local-first rendering and viewport read
 * receipts. The existing 2.5s poller is intentionally left in place.
 */

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");
let failures = 0;
function check(name, cond, detail) {
  if (cond) {
    console.log("  PASS " + name);
  } else {
    console.log("  FAIL " + name + (detail ? " :: " + detail : ""));
    failures++;
  }
}

function between(start, end) {
  const a = SRC.indexOf(start);
  const b = SRC.indexOf(end, a + start.length);
  if (a < 0 || b < 0) throw new Error("marker not found: " + start);
  return SRC.slice(a, b);
}

// ---------------------------------------------------------------------------
// Fake localStorage
// ---------------------------------------------------------------------------
function makeStorage() {
  const data = new Map();
  return {
    get length() { return data.size; },
    key(i) { return Array.from(data.keys())[i] || null; },
    getItem(k) { return data.has(k) ? data.get(k) : null; },
    setItem(k, v) { data.set(k, String(v)); },
    removeItem(k) { data.delete(k); },
    _data: data,
  };
}

// ---------------------------------------------------------------------------
// Minimal fake DOM used only by the overlap/append helper
// ---------------------------------------------------------------------------
function makeContainer() {
  const children = [];
  const container = {
    children,
    scrollTop: 0,
    scrollHeight: 1000,
    querySelector(selector) {
      const m = selector.match(/^\[data-(msg-id|random-id)="(.*)"\]$/);
      if (!m) return null;
      const key = m[1] === "msg-id" ? "msgId" : "randomId";
      return children.find((n) => String(n.dataset[key]) === m[2]) || null;
    },
    appendChild(node) {
      node.parentNode = container;
      children.push(node);
      refreshLinks();
      return node;
    },
  };
  function refreshLinks() {
    children.forEach((n, i) => {
      n.nextElementSibling = children[i + 1] || null;
      n.previousElementSibling = children[i - 1] || null;
    });
  }
  function makeNode(id, extra) {
    const node = {
      dataset: Object.assign({ msgId: id }, extra || {}),
      className: "flex flex-col items-end",
      nextElementSibling: null,
      previousElementSibling: null,
      parentNode: null,
      remove() {
        const idx = children.indexOf(node);
        if (idx >= 0) children.splice(idx, 1);
        node.parentNode = null;
        refreshLinks();
      },
    };
    return node;
  }
  return { container, makeNode, refreshLinks };
}

// ---------------------------------------------------------------------------
// Execute the real cache/overlap helper block
// ---------------------------------------------------------------------------
const helperCode = between("var CHAT_CACHE_PREFIX =", "function isUserOnline(");
const storage = makeStorage();
const state = {
  currentUser: { id: "user_a" },
  chatPendingSends: {},
  activeChatUser: null,
};
const renderCalls = [];
const renderStub = (container, messages, options) => {
  renderCalls.push({ messages: messages.slice(), options: options || {} });
  messages.forEach((m) => container.appendChild(makeMNode(container, m.id)));
};
function makeMNode(container, id) {
  const node = {
    dataset: { msgId: id },
    className: "bubble",
    nextElementSibling: null,
    previousElementSibling: null,
    parentNode: null,
    remove() {
      const idx = container.children.indexOf(node);
      if (idx >= 0) container.children.splice(idx, 1);
      node.parentNode = null;
    },
  };
  return node;
}
const helpers = new Function(
  "state",
  "getActiveUserId",
  "localStorage",
  "renderChatMessages",
  helperCode + "\nreturn { chatCacheKeyFor, chatCacheStorageKey, readChatCache, writeChatCache, clearChatCachesForUser, chatMessageVisualSignature, chatMessagesSignature, chatCacheOverlapLength, appendFreshChatMessages, restorePendingChatBubbles, scrollChatToBottom };"
)(state, () => state.currentUser.id, storage, renderStub);

// ---------------------------------------------------------------------------
// 1. Cache key and local-first storage
// ---------------------------------------------------------------------------
console.log("\n=== CHAT MESSAGING UPGRADE FRONTEND TESTS ===");
console.log("\n--- 1. Local cache ---");

const keyA = helpers.chatCacheKeyFor("user_a", "user_b");
const keyB = helpers.chatCacheKeyFor("user_b", "user_b");
check("cache key is account-scoped", keyA !== keyB);
check("cache key is partner-scoped",
  helpers.chatCacheKeyFor("user_a", "user_b") !== helpers.chatCacheKeyFor("user_a", "user_c"));
check("cache key uses the documented prefix", keyA.indexOf("kandid_chat_cache_v1_") === 0);

const sixty = [];
for (let i = 0; i < 60; i++) {
  sixty.push({ id: "m_" + i, content: "m" + i, created_at: "2026-01-01T00:00:00", read_at: null, reactions: [] });
}
helpers.writeChatCache("user_b", sixty);
const cached = helpers.readChatCache("user_b");
check("cache keeps the newest 50 messages", cached.length === 50, "got " + cached.length);
check("cache drops the oldest messages", cached[0].id === "m_10" && cached[49].id === "m_59");

const beforeClear = storage.length;
helpers.clearChatCachesForUser();
check("logout cache purge removes account chat caches", beforeClear > 0 && storage.length === 0);

// ---------------------------------------------------------------------------
// 2. Overlap / append-only reconciliation
// ---------------------------------------------------------------------------
console.log("\n--- 2. Append-only reconciliation ---");

const a = { id: "a", created_at: "2026-01-01T00:00:00", read_at: null, reactions: [] };
const b = { id: "b", created_at: "2026-01-01T00:00:01", read_at: null, reactions: [] };
const c = { id: "c", created_at: "2026-01-01T00:00:02", read_at: null, reactions: [] };
const d = { id: "d", created_at: "2026-01-01T00:00:03", read_at: null, reactions: [] };

check("shared suffix/prefix yields dropped-count 0", helpers.chatCacheOverlapLength([a, b], [a, b, c]) === 0);
check("shifted 50-message window prunes one old bubble", helpers.chatCacheOverlapLength([a, b, c], [b, c, d]) === 1);
check("unrelated pages are not treated as append-safe", helpers.chatCacheOverlapLength([a, b], [c, d]) === -1);
check("read_at change forces full reconcile", helpers.chatCacheOverlapLength([a], [Object.assign({}, a, { read_at: "2026-01-01T00:00:09" })]) === -1);

const fake = makeContainer();
fake.container.appendChild(fake.makeNode("a"));
fake.container.appendChild(fake.makeNode("b"));
renderCalls.length = 0;
const appended = helpers.appendFreshChatMessages(fake.container, [a, b], [b, c]);
check("append helper accepts a safe overlap", appended === true);
check("dropped bubble is removed from the DOM", !fake.container.querySelector('[data-msg-id="a"]'));
check("new bubble is appended without wiping retained ones",
  Boolean(fake.container.querySelector('[data-msg-id="b"]')) &&
  Boolean(fake.container.querySelector('[data-msg-id="c"]')));
check("append uses the append mode and last date group",
  renderCalls.length === 1 && renderCalls[0].options.append === true &&
  renderCalls[0].messages.length === 1 && renderCalls[0].messages[0].id === "c",
  JSON.stringify(renderCalls));

// ---------------------------------------------------------------------------
// 3. Source contracts for optimistic send, retry and read receipts
// ---------------------------------------------------------------------------
console.log("\n--- 3. Wiring contracts ---");

const sendFn = between("async function sendChatMessageV2() {", "window.sendChatMessageV2");
check("send creates a client random_id", /createChatRandomId\(\)/.test(sendFn));
check("send payload includes random_id", /random_id:\s*randomId/.test(between("function buildChatSendPayload", "function setChatBubbleStatus")));
check("optimistic bubble carries a temporary message id", /dataset\.msgId = 'temp_' \+ randomId/.test(SRC));
check("optimistic bubble starts with a clock status", /data-chat-status="clock"/.test(SRC) && /⏱/.test(SRC));
check("successful ack replaces the temporary id and shows a single check",
  /pending\.bubble\.dataset\.msgId = canonical\.id/.test(SRC) && /setChatBubbleStatus\(pending\.bubble, 'sent'\)/.test(SRC));
check("failed bubble stays mounted with a retry hook",
  /state\.chatPendingSends\[pending\.randomId\] = pending/.test(SRC) &&
  /setChatBubbleStatus\(pending\.bubble, 'failed'\)/.test(SRC) &&
  /function retryChatSend\(randomId\)/.test(SRC));
check("retry reuses the same pending random_id", /deliverChatMessage\(pending\)/.test(between("function retryChatSend", "window.retryChatSend")));

const loadFn = between("async function loadChatMessages", "window.loadChatMessages");
check("load reads the local cache before awaiting the network", /readChatCache\(userId\)/.test(loadFn));
check("load paints cached messages without the loading spinner", /if \(cachedMessages\.length\)/.test(loadFn) && /renderChatMessages\(container, cachedMessages\)/.test(loadFn));
check("load still uses the silent server reconciliation path", /apiRequest\('\/api\/chat\/messages/.test(loadFn));
check("load caches the server page", /writeChatCache\(userId, data\.messages\)/.test(loadFn));
check("load guards against a superseded request", /state\.chatLoadToken !== loadToken/.test(loadFn));

const readFn = between("async function markActiveChatRead", "function maybeMarkActiveChatRead");
check("read receipts require a visible focused thread", /document\.hidden/.test(readFn) && /document\.hasFocus/.test(readFn));
check("read receipts call the dedicated endpoint", /\/api\/chat\/read/.test(readFn));
check("read receipt updates the local cache and signature", /writeChatCache\(partnerId/.test(readFn) && /dataset\.msgSig = chatMessagesSignature/.test(readFn));
check("read receipts are also triggered on visibility/focus", /visibilitychange/.test(SRC) && /window\.addEventListener\('focus', maybeMarkActiveChatRead\)/.test(SRC));

const poller = between("window.chatSyncGlobalInterval = setInterval", "}, 2500);");
check("existing 2.5s poller remains unchanged", /loadChatMessages\(state\.activeChatUser, true\)/.test(poller));
check("logout purges local chat caches", /clearChatCachesForUser\(\)/.test(between("function logoutUser()", "window.logoutUser")));
check("render supports append mode without changing its public signature",
  /function renderChatMessages\(container, messages\)/.test(SRC) && /arguments\[2\]/.test(SRC) && /appendMode/.test(SRC));

// ---------------------------------------------------------------------------
// 4. Pure random id / payload helpers
// ---------------------------------------------------------------------------
console.log("\n--- 4. Random id and payload ---");
const idCode = between("var _chatRandomSequence = 0;", "function setChatBubbleStatus");
const idHelpers = new Function(
  "getActiveUserId",
  idCode + "\nreturn { createChatRandomId, buildChatSendPayload };"
)(() => "user_a");
const rid = idHelpers.createChatRandomId();
check("random id matches the server validator",
  /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(rid), rid);
check("random id is unique across 5000 calls",
  new Set(Array.from({ length: 5000 }, () => idHelpers.createChatRandomId())).size === 5000);
const payload = idHelpers.buildChatSendPayload("msg_rand_test_1234", "user_b", "hello", "m_reply");
check("payload carries the random id", payload.random_id === "msg_rand_test_1234");
check("payload still carries both receiver aliases", payload.receiverId === "user_b" && payload.receiver_id === "user_b");
check("payload still carries text and reply target", payload.content === "hello" && payload.reply_to_id === "m_reply");

console.log("\n=========================================");
if (failures) {
  console.log("TOTAL FAILURES: " + failures);
  process.exit(1);
}
console.log("ALL CHAT MESSAGING UPGRADE FRONTEND TESTS PASSED");
