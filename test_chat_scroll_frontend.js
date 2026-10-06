#!/usr/bin/env node
/*
 * Focused contract tests for the frontend chat scroll logic (Bug 2).
 *
 * No browser/DOM is available in this environment, so this test does two things:
 *   1. Asserts the REAL app_core.js source wires the intended behaviour
 *      (near-bottom guard, prepend scroll restore, passive guarded listener,
 *      untouched handlers).
 *   2. Evaluates the exact arithmetic used for scroll preservation and the
 *      near-bottom threshold against representative scenarios.
 *
 * It is a logic/contract test, NOT a live DOM scroll test on a real device.
 */
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");
let failures = 0;
function check(name, cond) {
  if (cond) console.log("  PASS " + name);
  else { console.log("  FAIL " + name); failures++; }
}
const loadFn = SRC.slice(SRC.indexOf("async function loadChatMessages"),
                        SRC.indexOf("function renderChatMessages"));
const olderFn = SRC.slice(SRC.indexOf("async function loadOlderChatMessages"),
                          SRC.indexOf("window.loadOlderChatMessages"));

console.log("\n=== CHAT SCROLL FRONTEND CONTRACT TESTS ===");

// ---- structure ----------------------------------------------------------
check("loadChatMessages defined", /async function loadChatMessages\(/.test(SRC));
check("renderChatMessages defined", /function renderChatMessages\(container, messages\)/.test(SRC));
check("loadOlderChatMessages defined", /async function loadOlderChatMessages\(/.test(SRC));

// ---- G1: forced scroll-to-bottom is guarded, not unconditional ----------
check("near-bottom threshold uses < 80",
      /scrollHeight - container\.scrollTop - container\.clientHeight\) < 80/.test(loadFn));
check("scroll-to-bottom lives in the wasNearBottom branch",
      /if \(wasNearBottom\) \{\s*container\.scrollTop = container\.scrollHeight;/.test(loadFn));
check("reading-history branch restores prevScrollTop",
      /\} else \{\s*container\.scrollTop = prevScrollTop;/.test(loadFn));
check("new conversation forces bottom (isNewConversation)",
      /wasNearBottom = isNewConversation \|\|/.test(loadFn));
check("only one scrollToBottom assignment in loadChatMessages",
      (loadFn.match(/container\.scrollTop = container\.scrollHeight;/g) || []).length === 1);

// ---- G2: prepend preserves the viewport via scrollHeight delta ----------
check("prepend captures old scrollHeight/scrollTop",
      /var oldScrollHeight = container\.scrollHeight;/.test(olderFn) &&
      /var oldScrollTop = container\.scrollTop;/.test(olderFn));
check("prepend applies scrollTop = oldScrollTop + (newHeight - oldHeight)",
      /container\.scrollTop = oldScrollTop \+ \(container\.scrollHeight - oldScrollHeight\);/.test(olderFn));
check("older page is PREPENDED, not replacing the newest page",
      /state\.chatOlderMessages = data\.messages\.concat\(state\.chatOlderMessages\);/.test(olderFn) &&
      /state\.chatOlderMessages\.concat\(state\.chatLoadedMessages \|\| \[\]\)/.test(olderFn));

// ---- guards + repeated pagination ---------------------------------------
check("concurrent-request guard present",
      /state\.chatOlderLoading \|\| !state\.chatHasMore\) return/.test(olderFn) &&
      /state\.chatOlderLoading = true;/.test(olderFn) &&
      /finally \{\s*state\.chatOlderLoading = false;/.test(olderFn));
check("stops when has_more is false",
      /!state\.chatHasMore\) return/.test(olderFn) &&
      /state\.chatHasMore = \(data\.has_more === true\);/.test(olderFn));

// ---- PART 6: no new global touch handler / preventDefault ---------------
check("scroll listener is passive",
      /addEventListener\('scroll', function\(\) \{[\s\S]*?\}, \{ passive: true \}\);/.test(SRC));
check("listener bound once (guarded)", /dataset\.olderBound === '1'/.test(SRC));
check("no preventDefault in pagination block", !/preventDefault/.test(olderFn));
check("no global touch handlers added",
      !/document\.addEventListener\('touch/.test(SRC) && !/window\.addEventListener\('touch/.test(SRC));

// ---- PART 7 / regression: handlers untouched ----------------------------
check("photo handler intact", SRC.includes(String.raw`safeOpenMediaUrl(this.dataset.mediaUrl)`));
check("moment handler intact", SRC.includes(String.raw`onclick="switchScreenView(\'feed\')"`));
check("Reply handler intact", SRC.includes(String.raw`handleChatReplyClick(\'' + m.id + '\')`));
check("React handler intact", SRC.includes(String.raw`openChatReactionSheet(\'' + m.id + '\')`));
check("action menu handler intact", SRC.includes(String.raw`openChatMessageActionMenu(\'' + m.id + '\')`));
check("tombstone early-return still precedes action row",
      SRC.indexOf("if (isTombstone)") < SRC.indexOf("chat-msg-actions transition-opacity"));
check("pagination block does not touch delete semantics", !/delete|permanent|restore/i.test(olderFn));

// ---- arithmetic contract ------------------------------------------------
function preservedScrollTop(oldScrollTop, oldScrollHeight, newScrollHeight) {
  return oldScrollTop + (newScrollHeight - oldScrollHeight);
}
check("G: prepend keeps the anchored message at the same viewport offset",
      preservedScrollTop(120, 2000, 3000) === 1120);

function wasNearBottom(scrollHeight, scrollTop, clientHeight, isNewConversation) {
  return isNewConversation || ((scrollHeight - scrollTop - clientHeight) < 80);
}
check("H: at bottom -> auto-scroll", wasNearBottom(2000, 1400, 600, false) === true);
check("H: 30px from bottom -> auto-scroll", wasNearBottom(2000, 1370, 600, false) === true);
check("H: reading history -> position preserved", wasNearBottom(2000, 200, 600, false) === false);
check("H: new conversation -> opens at bottom", wasNearBottom(2000, 200, 600, true) === true);

console.log("");
if (failures) { console.log("FAILURES: " + failures); process.exit(1); }
console.log("ALL FRONTEND CONTRACT TESTS PASSED");
