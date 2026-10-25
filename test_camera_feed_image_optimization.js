#!/usr/bin/env node
/*
 * Camera capture bounds + Cloudinary feed delivery tests.
 *
 * These execute the real functions from app_core.js in a minimal DOM sandbox:
 *   - kandidCloudinaryFeedUrl on plain / transformed / signed / non-Cloudinary URLs
 *   - renderFeedCards (real HTML string generation) main vs PiP delivery widths
 *   - attachCardInteractions optics swap keeps role-appropriate widths
 *   - kandidBoundCaptureSize / kandidDrawVideoFrame bounds, aspect and mirroring
 *   - KandidCameraEngine.capture() end-to-end with a fake 2560x1440 video,
 *     asserting the exact canvases handed to the JPEG serializer
 */

const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");

let checks = 0;
let failures = 0;
function check(name, cond, detail) {
  checks++;
  if (cond) {
    console.log("  PASS " + name);
  } else {
    console.log("  FAIL " + name + (detail ? " :: " + detail : ""));
    failures++;
  }
}

// Extract a top-level function declaration by brace matching, skipping strings
// and comments so braces inside regex/string literals cannot unbalance it.
function extractFunction(name) {
  const markers = ["function " + name + "(", "async function " + name + "("];
  let start = -1;
  for (const m of markers) {
    const i = SRC.indexOf(m);
    if (i !== -1 && (start === -1 || i < start)) start = i;
  }
  if (start === -1) throw new Error("function not found: " + name);
  const open = SRC.indexOf("{", start);
  let depth = 0;
  let quote = null;
  let lineComment = false;
  let blockComment = false;
  for (let i = open; i < SRC.length; i++) {
    const ch = SRC[i];
    const next = SRC[i + 1];
    if (lineComment) {
      if (ch === "\n") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === "*" && next === "/") { blockComment = false; i++; }
      continue;
    }
    if (quote) {
      if (ch === "\\") { i++; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === "/" && next === "/") { lineComment = true; i++; continue; }
    if (ch === "/" && next === "*") { blockComment = true; i++; continue; }
    if (ch === "'" || ch === '"' || ch === "`") { quote = ch; continue; }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return SRC.slice(start, i + 1);
    }
  }
  throw new Error("unbalanced function: " + name);
}

function makeElement(tag) {
  const listeners = {};
  return {
    tagName: tag,
    className: "",
    innerHTML: "",
    textContent: "",
    dataset: {},
    style: {},
    children: [],
    listeners,
    appendChild(child) { this.children.push(child); return child; },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(type, handler) { listeners[type] = handler; },
    querySelector() { return null; },
    setAttribute() {},
    getAttribute() { return null; }
  };
}

// =========================================================================
// 1. Cloudinary feed delivery URL builder
// =========================================================================
console.log("\n=== 1. Cloudinary feed delivery URLs ===");

const helpers = new Function(
  "document",
  extractFunction("kandidCloudinaryFeedUrl") + "\n" +
    "return { kandidCloudinaryFeedUrl };"
)({ createElement: makeElement });

const feedUrl = helpers.kandidCloudinaryFeedUrl;
const MAIN = 1080;
const PIP = 360;
const CLOUD = "https://res.cloudinary.com/vrjljx7y";
const PLAIN = CLOUD + "/image/upload/v1791446599/kandid/images/abc_123.jpg";

check("main URL gets c_limit,w_1080,f_auto,q_auto before the version",
  feedUrl(PLAIN, MAIN) === CLOUD + "/image/upload/c_limit,w_1080,f_auto,q_auto/v1791446599/kandid/images/abc_123.jpg");
check("PiP URL gets c_limit,w_360,f_auto,q_auto",
  feedUrl(PLAIN, PIP) === CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1791446599/kandid/images/abc_123.jpg");
check("non-versioned folder URL is transformed before the folder",
  feedUrl(CLOUD + "/image/upload/kandid/moments/frame_01.jpg", MAIN) ===
    CLOUD + "/image/upload/c_limit,w_1080,f_auto,q_auto/kandid/moments/frame_01.jpg");
check("public id containing underscores is not mistaken for a transformation",
  feedUrl(CLOUD + "/image/upload/v1/kandid/images/campus_2026_final.jpg", PIP) ===
    CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1/kandid/images/campus_2026_final.jpg");
check("already transformed q_auto URL is left untouched",
  feedUrl(CLOUD + "/image/upload/q_auto/v1/kandid/a.jpg", MAIN) ===
    CLOUD + "/image/upload/q_auto/v1/kandid/a.jpg");
check("existing crop transformation (c_fill,w_800,h_1000) is preserved verbatim",
  feedUrl(CLOUD + "/image/upload/c_fill,w_800,h_1000/v1/kandid/a.jpg", MAIN) ===
    CLOUD + "/image/upload/c_fill,w_800,h_1000/v1/kandid/a.jpg");
check("signed delivery URL is never rewritten",
  feedUrl(CLOUD + "/image/upload/s--AbCdEf--/v1/kandid/a.jpg", MAIN) ===
    CLOUD + "/image/upload/s--AbCdEf--/v1/kandid/a.jpg");
check("non-Cloudinary https URL is unchanged",
  feedUrl("https://images.example.com/photo.jpg", MAIN) === "https://images.example.com/photo.jpg");
check("local /uploads URL is unchanged",
  feedUrl("/uploads/main_1.png", MAIN) === "/uploads/main_1.png");
check("Cloudinary video URL is unchanged",
  feedUrl(CLOUD + "/video/upload/v1/kandid/audio/motion.mp4", MAIN) === CLOUD + "/video/upload/v1/kandid/audio/motion.mp4");
check("http Cloudinary URL is unchanged (no scheme upgrade)",
  feedUrl("http://res.cloudinary.com/vrjljx7y/image/upload/v1/kandid/a.jpg", MAIN) ===
    "http://res.cloudinary.com/vrjljx7y/image/upload/v1/kandid/a.jpg");
check("data URL is unchanged",
  feedUrl("data:image/jpeg;base64,AAAA", MAIN) === "data:image/jpeg;base64,AAAA");
check("empty string is returned unchanged", feedUrl("", MAIN) === "");
check("null/undefined become empty string", feedUrl(null, MAIN) === "" && feedUrl(undefined, MAIN) === "");
check("non-positive width returns the URL untouched", feedUrl(PLAIN, 0) === PLAIN && feedUrl(PLAIN, -1) === PLAIN);
check("query string survives transformation",
  feedUrl(CLOUD + "/image/upload/v1/kandid/a.jpg?foo=bar", PIP) ===
    CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1/kandid/a.jpg?foo=bar");
check("never emits an upscaling transform (c_limit only)",
  !/c_fill|c_fit|c_scale/.test(feedUrl(PLAIN, MAIN)) && /c_limit/.test(feedUrl(PLAIN, MAIN)));

// =========================================================================
// 2. Real feed renderer uses the delivery builder for main + PiP
// =========================================================================
console.log("\n=== 2. renderFeedCards delivery URLs ===");

function loadRenderer() {
  const sandboxState = {};
  return new Function(
    "document",
    "escapeHtml",
    "jsAttr",
    "formatTimeAgoClean",
    "kandidCloudinaryFeedUrl",
    "KANDID_FEED_MAIN_MAX_WIDTH",
    "KANDID_FEED_PIP_MAX_WIDTH",
    "attachCardInteractions",
    "updateAllMomentTimestamps",
    "state",
    extractFunction("renderFeedCards") + "\nreturn renderFeedCards;"
  )(
    { createElement: makeElement },
    (s) => String(s == null ? "" : s),
    (s) => String(s == null ? "" : s),
    () => "JUST NOW",
    feedUrl,
    MAIN,
    PIP,
    () => {},
    () => {},
    sandboxState
  );
}

const renderFeedCards = loadRenderer();
const container = { innerHTML: "", children: [], appendChild(c) { this.children.push(c); } };
const moment = {
  id: "post_test_1",
  author_handle: "tester",
  campus: "Near Quad",
  caption: "Test moment",
  created_at: "2026-10-25T00:00:00Z",
  main_img: PLAIN,
  pip_img: CLOUD + "/image/upload/v1791446599/kandid/images/pip_9.jpg"
};
renderFeedCards([moment], container);
const cardHtml = container.children[0] ? container.children[0].innerHTML : "";

check("feed card renders transformed main-stage image",
  cardHtml.includes('src="' + CLOUD + "/image/upload/c_limit,w_1080,f_auto,q_auto/v1791446599/kandid/images/abc_123.jpg" + '"'));
check("feed card renders transformed PiP image",
  cardHtml.includes('src="' + CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1791446599/kandid/images/pip_9.jpg" + '"'));
check("main-stage img comes before the pip img in the stage markup",
  cardHtml.indexOf("main-stage-img") < cardHtml.indexOf("pip-sub-img") &&
    cardHtml.indexOf("main-stage-img") !== -1);
check("raw untransformed Cloudinary URL is not used directly in feed HTML",
  !cardHtml.includes('src="' + PLAIN + '"'));

// =========================================================================
// 3. Optics swap keeps role-appropriate widths
// =========================================================================
console.log("\n=== 3. Optics swap (PiP <-> main) ===");

const stage = makeElement("div");
const pipEl = makeElement("div");
const mainEl = makeElement("img");
const pipImgEl = makeElement("img");
const fakeCard = {
  dataset: { postId: moment.id },
  querySelector(sel) {
    if (sel === ".moment-viewport-stage") return stage;
    if (sel === ".sub-camera-pip") return pipEl;
    if (sel === ".main-stage-img") return mainEl;
    if (sel === ".pip-sub-img") return pipImgEl;
    return null;
  },
  addEventListener() {}
};
const attachCardInteractions = new Function(
  "document",
  "kandidCloudinaryFeedUrl",
  "KANDID_FEED_MAIN_MAX_WIDTH",
  "KANDID_FEED_PIP_MAX_WIDTH",
  extractFunction("attachCardInteractions") + "\nreturn attachCardInteractions;"
)({ createElement: makeElement }, feedUrl, MAIN, PIP);

attachCardInteractions(fakeCard, moment);
const pipClick = pipEl.listeners.click;
check("pip click handler is registered", typeof pipClick === "function");

pipClick({ stopPropagation() {} });
check("swap shows the selfie at main width (1080), not its 360 thumbnail",
  mainEl.src === CLOUD + "/image/upload/c_limit,w_1080,f_auto,q_auto/v1791446599/kandid/images/pip_9.jpg");
check("swap shows the rear moment at PiP width (360)",
  pipImgEl.src === CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1791446599/kandid/images/abc_123.jpg");

pipClick({ stopPropagation() {} });
check("second swap restores the main moment at 1080",
  mainEl.src === CLOUD + "/image/upload/c_limit,w_1080,f_auto,q_auto/v1791446599/kandid/images/abc_123.jpg");
check("second swap restores the selfie at 360",
  pipImgEl.src === CLOUD + "/image/upload/c_limit,w_360,f_auto,q_auto/v1791446599/kandid/images/pip_9.jpg");

const localMoment = { id: "post_local", main_img: "/uploads/main_1.png", pip_img: "/uploads/pip_1.png" };
const localStage = makeElement("div");
const localPip = makeElement("div");
const localMain = makeElement("img");
const localPipImg = makeElement("img");
const localCard = {
  dataset: {},
  querySelector(sel) {
    return sel === ".moment-viewport-stage" ? localStage :
      sel === ".sub-camera-pip" ? localPip :
      sel === ".main-stage-img" ? localMain :
      sel === ".pip-sub-img" ? localPipImg : null;
  },
  addEventListener() {}
};
attachCardInteractions(localCard, localMoment);
localPip.listeners.click({ stopPropagation() {} });
check("swap leaves local /uploads media unchanged",
  localMain.src === "/uploads/pip_1.png" && localPipImg.src === "/uploads/main_1.png");

// =========================================================================
// 4. Bounded capture geometry
// =========================================================================
console.log("\n=== 4. Capture bounds, aspect, upscaling ===");

const bound = new Function(
  "var KANDID_CAPTURE_MAX_WIDTH = 1080; var KANDID_CAPTURE_MAX_HEIGHT = 1440;" +
  extractFunction("kandidBoundCaptureSize") + "\nreturn kandidBoundCaptureSize;"
)();

function assertBounds(label, w, h, expW, expH) {
  const r = bound(w, h);
  check(label + " -> " + r.width + "x" + r.height,
    r.width === expW && r.height === expH &&
    r.width <= 1080 && r.height <= 1440 &&
    Math.abs((w / h) - (r.width / r.height)) < 0.01,
    "expected " + expW + "x" + expH);
}

assertBounds("landscape 2560x1440", 2560, 1440, 1080, 608);
assertBounds("landscape 3840x2160 (4K)", 3840, 2160, 1080, 608);
assertBounds("portrait 1080x1920", 1080, 1920, 810, 1440);
assertBounds("portrait 2160x3840 (4K)", 2160, 3840, 810, 1440);
assertBounds("square 3000x3000", 3000, 3000, 1080, 1080);
assertBounds("small 640x480 is not upscaled", 640, 480, 640, 480);
assertBounds("already bounded 1080x1440 is unchanged", 1080, 1440, 1080, 1440);
assertBounds("narrow portrait 720x2560", 720, 2560, 405, 1440);

const invalid = bound(0, 0);
check("invalid source returns 0x0", invalid.width === 0 && invalid.height === 0);

// =========================================================================
// 5. kandidDrawVideoFrame canvas size + mirroring
// =========================================================================
console.log("\n=== 5. Frame drawing (canvas size + mirror transform) ===");

function makeCanvas() {
  const ops = [];
  return {
    width: 0,
    height: 0,
    ops,
    getContext() {
      return {
        translate(x, y) { ops.push(["translate", x, y]); },
        scale(x, y) { ops.push(["scale", x, y]); },
        drawImage(...args) { ops.push(["drawImage"].concat(args)); }
      };
    }
  };
}

const drawSandboxDocs = [];
const drawFrame = new Function(
  "document",
  "var KANDID_CAPTURE_MAX_WIDTH = 1080; var KANDID_CAPTURE_MAX_HEIGHT = 1440;" +
  extractFunction("kandidBoundCaptureSize") + "\n" +
  extractFunction("kandidDrawVideoFrame") + "\nreturn kandidDrawVideoFrame;"
)({
  createElement() {
    const c = makeCanvas();
    drawSandboxDocs.push(c);
    return c;
  }
});

const rearVideo = { videoWidth: 2560, videoHeight: 1440 };
const rearCanvas = drawFrame(rearVideo, false);
check("rear landscape canvas is 1080x608 (16:9, width-limited)", rearCanvas.width === 1080 && rearCanvas.height === 608);
check("rear frame is not mirrored",
  rearCanvas.ops.length === 1 && rearCanvas.ops[0][0] === "drawImage");
check("rear drawImage covers the bounded canvas",
  rearCanvas.ops[0][4] === 1080 && rearCanvas.ops[0][5] === 608);

const frontVideo = { videoWidth: 1080, videoHeight: 1920 };
const frontCanvas = drawFrame(frontVideo, true);
check("front portrait canvas is 810x1440", frontCanvas.width === 810 && frontCanvas.height === 1440);
check("front selfie applies translate(width,0) then scale(-1,1)",
  frontCanvas.ops.length === 3 &&
  frontCanvas.ops[0][0] === "translate" && frontCanvas.ops[0][1] === 810 && frontCanvas.ops[0][2] === 0 &&
  frontCanvas.ops[1][0] === "scale" && frontCanvas.ops[1][1] === -1 && frontCanvas.ops[1][2] === 1 &&
  frontCanvas.ops[2][0] === "drawImage");
check("front drawImage uses bounded dimensions",
  frontCanvas.ops[2][4] === 810 && frontCanvas.ops[2][5] === 1440);
check("empty video returns no canvas", drawFrame({ videoWidth: 0, videoHeight: 0 }, false) === null);

// =========================================================================
// 6. Real KandidCameraEngine.capture() uses bounded canvases
// =========================================================================
console.log("\n=== 6. KandidCameraEngine.capture() end-to-end ===");

const capStart = SRC.indexOf("  async capture() {");
if (capStart === -1) throw new Error("capture() not found");
const capOpen = SRC.indexOf("{", capStart);
let capDepth = 0;
let capEnd = -1;
for (let i = capOpen; i < SRC.length; i++) {
  if (SRC[i] === "{") capDepth++;
  else if (SRC[i] === "}") {
    capDepth--;
    if (capDepth === 0) { capEnd = i; break; }
  }
}
const capBody = SRC.slice(capOpen, capEnd + 1);

const previewImg = { src: "", classList: { add() {}, remove() {} } };
const video = {
  videoWidth: 2560,
  videoHeight: 1440,
  readyState: 4,
  style: {},
  classList: { add() {}, remove() {} }
};
const serialized = [];
const fakeDoc = {
  getElementById(id) {
    if (id === "cameraMainVideo") return video;
    if (id === "cameraMainPreviewImg") return previewImg;
    return null;
  },
  createElement() {
    const c = makeCanvas();
    c.toBlob = function () { throw new Error("serializer should be stubbed"); };
    return c;
  }
};

const captureState = {};
let reviewOpened = 0;
const engine = {
  _gen: 1,
  state: "READY",
  activeFacing: "environment",
  rearFrame: null,
  frontFrame: null,
  compositeImage: null,
  audioClip: "",
  _captureStartedAt: 0,
  _isBusy() { return false; },
  setState(next) { this.state = next; },
  _setShutterEnabled() {},
  startAmbientAudioCapture() {},
  startMainPreview(facing) {
    if (facing === "user") { video.videoWidth = 1080; video.videoHeight = 1920; }
    else { video.videoWidth = 2560; video.videoHeight = 1440; }
    return true;
  },
  stop() {}
};

const capture = new Function(
  "document",
  "navigator",
  "performance",
  "state",
  "kandidDrawVideoFrame",
  "kandidSerializeCanvasJpeg",
  "showToast",
  "closeCameraStudio",
  "openMomentReview",
  "setTimeout",
  "return async function capture() " + capBody + ";"
)(
  fakeDoc,
  { vibrate() {} },
  { now() { return 0; } },
  captureState,
  drawFrame,
  async function (canvas, quality) {
    serialized.push({
      width: canvas.width,
      height: canvas.height,
      quality: quality,
      ops: canvas.ops.slice()
    });
    return "data:image/jpeg;base64," + (serialized.length === 1 ? "REAR" : "FRONT");
  },
  () => {},
  () => {},
  () => { reviewOpened++; },
  (fn) => { fn(); return 0; }
);

(async function () {
  await capture.call(engine);

  check("capture serialized exactly two frames", serialized.length === 2);
  check("rear capture canvas is bounded to 1080x608 (from 2560x1440)",
    serialized[0] && serialized[0].width === 1080 && serialized[0].height === 608);
  check("front capture canvas is bounded to 810x1440",
    serialized[1] && serialized[1].width === 810 && serialized[1].height === 1440);
  check("JPEG quality remains the existing 0.98",
    serialized[0] && serialized[0].quality === 0.98 && serialized[1].quality === 0.98);
  check("rear frame is drawn unmirrored",
    serialized[0] && serialized[0].ops.length === 1 && serialized[0].ops[0][0] === "drawImage");
  check("front selfie is mirrored",
    serialized[1] && serialized[1].ops.length === 3 &&
    serialized[1].ops[0][0] === "translate" && serialized[1].ops[0][1] === 810 &&
    serialized[1].ops[1][0] === "scale" && serialized[1].ops[1][1] === -1);
  check("captured payload keeps rear=mainImg and selfie=pipImg roles",
    captureState.capturedMomentData &&
    captureState.capturedMomentData.mainImg === "data:image/jpeg;base64,REAR" &&
    captureState.capturedMomentData.pipImg === "data:image/jpeg;base64,FRONT");
  check("review opens once with the composed moment", reviewOpened === 1 && engine.rearFrame === "data:image/jpeg;base64,REAR");
  check("capture leaves the preview frozen on the rear frame", previewImg.src === "data:image/jpeg;base64,REAR");

  // ---------------------------------------------------------------------
  // 7. Source wiring (supplementary static assertions)
  // ---------------------------------------------------------------------
  console.log("\n=== 7. Wiring assertions ===");
  check("capture uses bounded first frame helper",
    /firstCanvas = kandidDrawVideoFrame\(mainVideo, startFacing === 'user'\)/.test(SRC));
  check("capture uses bounded second frame helper",
    /secondCanvas = kandidDrawVideoFrame\(mainVideo, nextFacing === 'user'\)/.test(SRC));
  check("capture no longer sizes canvases from raw videoWidth",
    !/firstCanvas\.width = mainVideo\.videoWidth/.test(SRC) &&
    !/secondCanvas\.width = mainVideo\.videoWidth/.test(SRC));
  check("all three feed renderers use the delivery builder",
    (SRC.match(/var mainImgSrc = kandidCloudinaryFeedUrl\(m\.main_img/g) || []).length === 3);
  check("PiP delivery width constant is 360", /var KANDID_FEED_PIP_MAX_WIDTH = 360;/.test(SRC));
  check("main delivery width constant is 1080", /var KANDID_FEED_MAIN_MAX_WIDTH = 1080;/.test(SRC));
  check("capture bound constants are 1080 x 1440",
    /var KANDID_CAPTURE_MAX_WIDTH = 1080;/.test(SRC) &&
    /var KANDID_CAPTURE_MAX_HEIGHT = 1440;/.test(SRC));

  console.log("\n=== RESULT: " + (checks - failures) + "/" + checks + " checks passed ===");
  process.exit(failures ? 1 : 0);
})();
