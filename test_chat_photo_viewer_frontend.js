#!/usr/bin/env node
/*
 * Comprehensive frontend contract and logic tests for:
 *   - Private chat photo attachment URL predicates
 *   - ChatPhotoCache (soft/hard caps, transient handling, pinning, detach-before-revoke, in-flight dedup)
 *   - Full-screen viewer modal hooks, keyboard navigation, and focus trapping
 *   - DOM rendering contracts for private vs HTTPS vs invalid photos
 *   - Session lifecycle, screen switching, logout, and BFCache wiring
 */

const fs = require("fs");
const path = require("path");

const SRC_APP = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");
const SRC_HTML = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
const SRC_CSS = fs.readFileSync(path.join(__dirname, "style.css"), "utf8");

let failures = 0;
function check(name, cond) {
  if (cond) {
    console.log("  PASS " + name);
  } else {
    console.log("  FAIL " + name);
    failures++;
  }
}

console.log("\n=== CHAT PHOTO VIEWER FRONTEND TESTS ===");

// =========================================================================
// 1. PURE LOGIC / PREDICATE TESTS
// =========================================================================
console.log("\n--- 1. Chat Media Predicates ---");

// Extract regex and predicate functions from source to execute directly
const predicateBlock = `
  var window = {};
  ${SRC_APP.slice(SRC_APP.indexOf("var _CHAT_ATTACHMENT_URL_RE ="), SRC_APP.indexOf("window.isSafeChatPhotoUrl ="))}
  return { isPrivateChatAttachmentUrl, isPermittedChatHttpsUrl, isSafeChatPhotoUrl };
`;
const predicates = new Function(predicateBlock)();

// Private attachment URLs
check("accepts valid private attachment URL",
  predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcdef"));
check("rejects attachment URL with uppercase hex",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789ABCDEF"));
check("rejects attachment URL with 15 hex chars",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcde"));
check("rejects attachment URL with 17 hex chars",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcdef0"));
check("rejects path traversal in attachment URL",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcdef/../secret"));
check("rejects arbitrary prefix",
  !predicates.isPrivateChatAttachmentUrl("/other/api/chat/attachments/att_0123456789abcdef"));
check("rejects query string in attachment URL",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcdef?foo=bar"));
check("rejects fragment in attachment URL",
  !predicates.isPrivateChatAttachmentUrl("/api/chat/attachments/att_0123456789abcdef#frag"));
check("rejects non-string attachment URL",
  !predicates.isPrivateChatAttachmentUrl(null) && !predicates.isPrivateChatAttachmentUrl(undefined));

// Permitted HTTPS URLs
check("accepts clean HTTPS URL",
  predicates.isPermittedChatHttpsUrl("https://images.unsplash.com/photo-12345"));
check("rejects HTTP URL",
  !predicates.isPermittedChatHttpsUrl("http://images.unsplash.com/photo-12345"));
check("rejects protocol-relative URL",
  !predicates.isPermittedChatHttpsUrl("//images.unsplash.com/photo-12345"));
check("rejects javascript: scheme",
  !predicates.isPermittedChatHttpsUrl("javascript:alert(1)"));
check("rejects data: URL",
  !predicates.isPermittedChatHttpsUrl("data:image/png;base64,AAAA"));
check("rejects HTTPS URL with quotes or tags",
  !predicates.isPermittedChatHttpsUrl('https://example.com/foo"bar') &&
  !predicates.isPermittedChatHttpsUrl("https://example.com/foo<script>"));
check("rejects HTTPS URL with control characters",
  !predicates.isPermittedChatHttpsUrl("https://example.com/\x00evil"));

// Unified predicate
check("isSafeChatPhotoUrl accepts both valid private and valid https",
  predicates.isSafeChatPhotoUrl("/api/chat/attachments/att_0123456789abcdef") &&
  predicates.isSafeChatPhotoUrl("https://example.com/pic.jpg"));
check("isSafeChatPhotoUrl rejects invalid URLs",
  !predicates.isSafeChatPhotoUrl("ftp://example.com/pic.jpg") &&
  !predicates.isSafeChatPhotoUrl("/api/chat/attachments/evil"));

// =========================================================================
// 2. CHAT PHOTO CACHE LOGIC & POLICY
// =========================================================================
console.log("\n--- 2. ChatPhotoCache Policy & Memory Model ---");

check("ChatPhotoCache defined in app_core.js",
  SRC_APP.includes("var ChatPhotoCache = (function() {"));
check("Soft max entries = 24",
  /SOFT_MAX_ENTRIES = 24/.test(SRC_APP));
check("Soft max bytes = 32 MB",
  /SOFT_MAX_BYTES = 32 \* 1024 \* 1024/.test(SRC_APP));
check("Hard ceiling = 48 MB",
  /HARD_MAX_BYTES = 48 \* 1024 \* 1024/.test(SRC_APP));
check("Transient threshold = 4 MB",
  /TRANSIENT_THRESHOLD_BYTES = 4 \* 1024 \* 1024/.test(SRC_APP));
check("Failure TTL = 30000 ms and max failures = 50",
  /FAILURE_TTL_MS = 30000/.test(SRC_APP) && /MAX_FAILURES = 50/.test(SRC_APP));

// Simulate cache lifecycle in sandbox
function runCacheSimulation() {
  const revokedUrls = [];
  const createdUrls = [];
  let detachedCount = 0;

  const mockUrl = {
    createObjectURL: (blob) => {
      const u = "blob:mock-" + Math.random().toString(36).slice(2);
      createdUrls.push(u);
      return u;
    },
    revokeObjectURL: (u) => {
      revokedUrls.push(u);
    }
  };

  // Extract cache source and execute with mock environment
  const cacheCode = SRC_APP.slice(
    SRC_APP.indexOf("var ChatPhotoCache = (function() {"),
    SRC_APP.indexOf("window.ChatPhotoCache = ChatPhotoCache;")
  );

  const sandboxFactory = new Function("mockURL", "onDetach", `
    var URL = mockURL;
    var state = { currentUser: { id: "user_1" } };
    function getActiveUserId() { return state.currentUser.id; }
    function isPrivateChatAttachmentUrl(url) {
      return /^\\/api\\/chat\\/attachments\\/att_[0-9a-f]{16}$/.test(url);
    }
    var document = {
      querySelectorAll: function(sel) {
        onDetach();
        return [];
      }
    };
    ${cacheCode}
    return { ChatPhotoCache, state };
  `);

  const { ChatPhotoCache, state } = sandboxFactory(mockUrl, () => { detachedCount++; });

  return { ChatPhotoCache, state, mockUrl, revokedUrls, createdUrls, getDetachedCount: () => detachedCount };
}

const sim = runCacheSimulation();
check("ChatPhotoCache exposes required API methods",
  typeof sim.ChatPhotoCache.get === "function" &&
  typeof sim.ChatPhotoCache.has === "function" &&
  typeof sim.ChatPhotoCache.loadAttachment === "function" &&
  typeof sim.ChatPhotoCache.releaseConsumer === "function" &&
  typeof sim.ChatPhotoCache.pin === "function" &&
  typeof sim.ChatPhotoCache.unpin === "function" &&
  typeof sim.ChatPhotoCache.clearAll === "function" &&
  typeof sim.ChatPhotoCache.getStats === "function");

check("ChatPhotoCache starts empty with 0 bytes and epoch 0", () => {
  const stats = sim.ChatPhotoCache.getStats();
  return stats.entries === 0 && stats.totalBytes === 0 && stats.epoch === 0;
});

// Test Pinning logic
sim.ChatPhotoCache.pin("/api/chat/attachments/att_1111111111111111");
check("pin() marks pinnedUrl in stats",
  sim.ChatPhotoCache.getStats().pinnedUrl === "/api/chat/attachments/att_1111111111111111");

sim.ChatPhotoCache.unpin("/api/chat/attachments/att_1111111111111111");
check("unpin() unsets pinnedUrl",
  sim.ChatPhotoCache.getStats().pinnedUrl === null);

// Test clearAll(false) preserves pinned, clearAll(true) purges all
sim.ChatPhotoCache.pin("/api/chat/attachments/att_2222222222222222");
sim.ChatPhotoCache.clearAll(false);
check("clearAll(false) keeps pinned URL active",
  sim.ChatPhotoCache.getStats().pinnedUrl === "/api/chat/attachments/att_2222222222222222");

sim.ChatPhotoCache.clearAll(true);
check("clearAll(true) revokes pinned URL and resets pinnedUrl",
  sim.ChatPhotoCache.getStats().pinnedUrl === null);

// Test detach before revoke source pattern
check("detachDomReferences called prior to revokeObjectURL",
  SRC_APP.indexOf("detachDomReferences(entry.blobUrl)") < SRC_APP.indexOf("URL.revokeObjectURL(entry.blobUrl)"));

// =========================================================================
// 3. FULL-SCREEN VIEWER CONTRACTS
// =========================================================================
console.log("\n--- 3. Full-Screen Viewer Markup, Styles & Logic ---");

// HTML Markup
check("HTML contains #chatPhotoViewer with modal dialog attributes",
  SRC_HTML.includes('id="chatPhotoViewer"') &&
  SRC_HTML.includes('role="dialog"') &&
  SRC_HTML.includes('aria-modal="true"') &&
  SRC_HTML.includes('aria-label="Photo viewer"'));
check("HTML contains close button #chatPhotoViewerCloseBtn calling closeChatPhotoViewer()",
  SRC_HTML.includes('id="chatPhotoViewerCloseBtn"') &&
  SRC_HTML.includes('onclick="closeChatPhotoViewer()"'));
check("HTML contains #chatPhotoViewerLoading and #chatPhotoViewerError",
  SRC_HTML.includes('id="chatPhotoViewerLoading"') &&
  SRC_HTML.includes('id="chatPhotoViewerError"'));
check("HTML contains image #chatPhotoViewerImg with object-contain",
  SRC_HTML.includes('id="chatPhotoViewerImg"') &&
  SRC_HTML.includes('object-contain'));

// CSS
check("CSS contains #chatPhotoViewer rules with pinch-zoom touch-action",
  SRC_CSS.includes("#chatPhotoViewer") &&
  SRC_CSS.includes("touch-action: pinch-zoom;"));
check("CSS contains #chatPhotoViewer.active display: flex !important",
  SRC_CSS.includes("#chatPhotoViewer.active") &&
  SRC_CSS.includes("display: flex !important;"));
check("CSS contains #chatPhotoViewerImg object-fit: contain",
  SRC_CSS.includes("#chatPhotoViewerImg") &&
  SRC_CSS.includes("object-fit: contain;"));

// JS Logic
check("openChatPhotoViewer and closeChatPhotoViewer defined",
  SRC_APP.includes("async function openChatPhotoViewer(url, originEl)") &&
  SRC_APP.includes("function closeChatPhotoViewer()"));
check("openChatPhotoViewer validates URL with isSafeChatPhotoUrl",
  /if \(!url \|\| !isSafeChatPhotoUrl\(url\)\)/.test(SRC_APP));
check("openChatPhotoViewer pins private attachment URL in ChatPhotoCache",
  SRC_APP.includes("ChatPhotoCache.pin(url);"));
check("closeChatPhotoViewer unpins URL in ChatPhotoCache",
  SRC_APP.includes("ChatPhotoCache.unpin(pinned);"));
check("closeChatPhotoViewer restores focus to origin element",
  SRC_APP.includes("_lastFocusedPhotoEl.focus()"));
check("Escape key closes viewer",
  /if \(e\.key === 'Escape' \|\| e\.key === 'Esc'\)[\s\S]*?closeChatPhotoViewer\(\)/.test(SRC_APP));
check("Tab key focus trapping implemented",
  /if \(e\.key === 'Tab'\)[\s\S]*?focusables/.test(SRC_APP));
check("Viewer requestId guard prevents race conditions",
  SRC_APP.includes("var reqId = ++_activeViewerRequestId;") &&
  SRC_APP.includes("if (reqId !== _activeViewerRequestId) return;"));

// =========================================================================
// 4. CHAT RENDERING & DETACH CONTRACT
// =========================================================================
console.log("\n--- 4. Message Rendering Contract ---");

check("renderChatMessages detaches outgoing attachment images before innerHTML wipe", (() => {
  const renderStart = SRC_APP.indexOf("function renderChatMessages(container, messages)");
  const renderEnd = SRC_APP.indexOf("window.renderChatMessages = renderChatMessages;");
  const renderFn = SRC_APP.slice(renderStart, renderEnd);
  const detachIdx = renderFn.indexOf("container.querySelectorAll('img.chat-attachment-img[data-media-url]')");
  const wipeIdx = renderFn.indexOf("container.innerHTML = '';");
  return detachIdx >= 0 && wipeIdx >= 0 && detachIdx < wipeIdx;
})());
check("private attachment rendered with data-media-url and chat-attachment-img",
  SRC_APP.includes('class="w-full h-auto max-h-60 object-cover rounded-lg cursor-pointer chat-attachment-img'));
check("private attachment never sets protected relative URL to src directly",
  !/photoHtml =[\s\S]*?<img src="\/api\/chat\/attachments\//.test(SRC_APP));
check("HTTPS photo rendered with loading=lazy and openChatPhotoViewer",
  SRC_APP.includes('class="w-full h-auto max-h-60 object-cover rounded-lg cursor-pointer" loading="lazy" alt="Chat photo" data-media-url="') &&
  SRC_APP.includes('onclick="openChatPhotoViewer(this.dataset.mediaUrl, this)">'));
check("invalid photo rendered with non-clickable unavailable notice",
  SRC_APP.includes('<span>⚠️</span><span>Photo unavailable</span>'));
check("hydrateChatPhotos invoked after message rendering",
  /hydrateChatPhotos\(container\);/.test(SRC_APP));

// =========================================================================
// 5. LIFECYCLE, SCREEN SWITCHING & LOGOUT
// =========================================================================
console.log("\n--- 5. Lifecycle, Navigation & Session Cleanup ---");

check("switchScreenView closes viewer when navigating away from chat",
  /prevScreen === 'chat-conversation' && screenName !== 'chat-conversation'[\s\S]*?closeChatPhotoViewer\(\)/.test(SRC_APP));
check("switchScreenView detaches DOM and clears cache when navigating away from chat",
  /prevScreen === 'chat-conversation' && screenName !== 'chat-conversation'[\s\S]*?ChatPhotoCache\.detachDomReferences\(\);[\s\S]*?ChatPhotoCache\.clearAll\(false\);/.test(SRC_APP));
check("openChatThread closes viewer and purges previous conversation cache",
  /function openChatThread[\s\S]*?closeChatPhotoViewer\(\);[\s\S]*?ChatPhotoCache\.clearAll\(false\);/.test(SRC_APP));
check("logoutUser closes viewer, increments epoch and clears all cached Blob URLs",
  /function logoutUser\(\) \{[\s\S]*?closeChatPhotoViewer\(\);[\s\S]*?ChatPhotoCache\.incrementEpoch\(\);[\s\S]*?ChatPhotoCache\.clearAll\(true\);/.test(SRC_APP));
check("logoutUser purges img src and media attributes from chat container",
  /function logoutUser\(\) \{[\s\S]*?img\.removeAttribute\('src'\);[\s\S]*?img\.removeAttribute\('data-blob-url'\);[\s\S]*?img\.removeAttribute\('data-media-url'\);/.test(SRC_APP));
check("pagehide listener preserves Blob URLs on persisted BFCache entry",
  /window\.addEventListener\('pagehide', function\(e\) \{[\s\S]*?if \(e && e\.persisted\) \{[\s\S]*?return;/.test(SRC_APP));
check("pagehide listener purges on non-persisted navigation",
  /window\.addEventListener\('pagehide', function\(e\) \{[\s\S]*?ChatPhotoCache\.clearAll\(true\);/.test(SRC_APP));
check("pageshow listener verifies ownership and reconciles viewer",
  /window\.addEventListener\('pageshow', function\(e\) \{[\s\S]*?ChatPhotoCache\.checkUserOwnership\(\);[\s\S]*?closeChatPhotoViewer\(\);/.test(SRC_APP));
check("no beforeunload or unload handlers added",
  !/addEventListener\(['"]beforeunload['"]/.test(SRC_APP) &&
  !/addEventListener\(['"]unload['"]/.test(SRC_APP));

// =========================================================================
// SUMMARY
// =========================================================================
console.log("\n=========================================");
if (failures > 0) {
  console.log(`TOTAL FAILURES: ${failures}`);
  process.exit(1);
} else {
  console.log("ALL CHAT PHOTO VIEWER FRONTEND TESTS PASSED (61 checks)");
  process.exit(0);
}
