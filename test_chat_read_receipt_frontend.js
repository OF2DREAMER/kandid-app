#!/usr/bin/env node
/*
 * Focused behavioral tests for the viewport-triggered read receipt client.
 *
 * The real markActiveChatRead() source is executed with a minimal fake DOM and
 * a deferred-free apiRequest stub. This proves the visibility/focus gates and
 * the max_message_id request shape without pretending to be a real browser.
 */

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");
let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log("  PASS " + name);
  else {
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

const readCode = between("async function markActiveChatRead", "function maybeMarkActiveChatRead");
const baseMessages = () => ([
  { id: "m1", sender_id: "u_b", receiver_id: "u_a", content: "one", created_at: "2026-02-01T10:00:01", read_at: null, reactions: [] },
  { id: "m2", sender_id: "u_b", receiver_id: "u_a", content: "two", created_at: "2026-02-01T10:00:02", read_at: null, reactions: [] },
  { id: "m3", sender_id: "u_a", receiver_id: "u_b", content: "mine", created_at: "2026-02-01T10:00:03", read_at: null, reactions: [] },
]);

function makeHarness(opts) {
  opts = opts || {};
  const calls = [];
  const writes = [];
  let badgeCalls = 0;
  const state = {
    activeScreen: opts.screen || "chat-conversation",
    activeChatUser: "u_b",
    chatMyId: "u_a",
    chatLoadedMessages: opts.messages || baseMessages(),
    chatReadInFlight: null,
    chatLastReadReceipt: null,
  };
  const document = {
    hidden: !!opts.hidden,
    hasFocus: () => opts.focused !== false,
    getElementById: () => ({ dataset: {} }),
  };
  const apiRequest = async (endpoint, options) => {
    calls.push({ endpoint, body: JSON.parse(options.body) });
    if (opts.fail) return { success: false, error: "nope" };
    return { success: true, read_at: "2026-02-01T10:00:05" };
  };
  const writeChatCache = (partnerId, messages) => {
    writes.push(messages.map((m) => m.id + ":" + (m.read_at || "")).join(","));
  };
  const factory = new Function(
    "state",
    "document",
    "apiRequest",
    "getActiveUserId",
    "writeChatCache",
    "chatMessagesSignature",
    "checkChatUnreadBadge",
    readCode + "\nreturn markActiveChatRead;"
  );
  const fn = factory(
    state,
    document,
    apiRequest,
    () => "u_a",
    writeChatCache,
    () => "sig",
    () => { badgeCalls++; }
  );
  return { fn, state, calls, writes, badgeCalls: () => badgeCalls };
}

async function main() {
  console.log("\n=== CHAT READ RECEIPT FRONTEND BEHAVIOR ===");

  let h = makeHarness({ hidden: true });
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("hidden tab sends no read request", h.calls.length === 0);

  h = makeHarness({ focused: false });
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("unfocused tab sends no read request", h.calls.length === 0);

  h = makeHarness({ screen: "chat-home" });
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("non-chat screen sends no read request", h.calls.length === 0);

  h = makeHarness({});
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("visible focused thread sends exactly one read request", h.calls.length === 1);
  check("read request uses the dedicated endpoint", h.calls[0].endpoint === "/api/chat/read");
  check("read request targets the partner", h.calls[0].body.partner_id === "u_b");
  check("read request uses the latest unread inbound message",
    h.calls[0].body.max_message_id === "m2", JSON.stringify(h.calls[0].body));
  check("inbound messages are marked read locally",
    h.state.chatLoadedMessages[0].read_at === "2026-02-01T10:00:05" &&
    h.state.chatLoadedMessages[1].read_at === "2026-02-01T10:00:05");
  check("outbound message is untouched", h.state.chatLoadedMessages[2].read_at === null);
  check("cache is rewritten after a successful receipt", h.writes.length === 1);
  check("unread badge is refreshed", h.badgeCalls() === 1);
  check("receipt key is recorded", h.state.chatLastReadReceipt === "u_b|m2");

  await h.fn("u_b", h.state.chatLoadedMessages);
  check("repeated call for the same cursor is a no-op", h.calls.length === 1);

  h.state.chatLoadedMessages.push({
    id: "m4", sender_id: "u_b", receiver_id: "u_a", content: "new",
    created_at: "2026-02-01T10:00:04", read_at: null, reactions: [],
  });
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("a newer inbound message advances the cursor", h.calls.length === 2 && h.calls[1].body.max_message_id === "m4");

  h = makeHarness({ fail: true });
  await h.fn("u_b", h.state.chatLoadedMessages);
  check("failed receipt leaves local state unread",
    h.state.chatLoadedMessages[0].read_at === null &&
    h.state.chatLoadedMessages[1].read_at === null &&
    h.state.chatLastReadReceipt === null);

  console.log("\n=========================================");
  if (failures) {
    console.log("TOTAL FAILURES: " + failures);
    process.exit(1);
  }
  console.log("ALL CHAT READ RECEIPT FRONTEND TESTS PASSED");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
