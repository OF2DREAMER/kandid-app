#!/usr/bin/env node
/**
 * C1 camera startup hardening tests.
 *
 * These are DETERMINISTIC MOCK tests for the KandidCameraEngine state machine:
 * they assert our own control flow (READY only after real preview readiness,
 * recoverable failure, listener/track cleanup). They do NOT reproduce or claim
 * to reproduce Vivo/Android camera hardware behaviour.
 *
 * Run: node test_camera_startup_hardening.js
 */
'use strict';

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const APP = path.join(__dirname, 'app_core.js');
const src = fs.readFileSync(APP, 'utf8');

const START = src.indexOf('const KandidCameraEngine = {');
const END = src.indexOf('window.KandidCameraEngine = KandidCameraEngine;');
if (START < 0 || END < 0 || END < START) {
  console.error('FATAL: could not locate the KandidCameraEngine object in app_core.js');
  process.exit(1);
}
const engineSource = src.slice(START, END).replace(/^const KandidCameraEngine/, 'var KandidCameraEngine');

let pass = 0;
let fail = 0;
function check(name, cond, detail) {
  if (cond) {
    pass++;
    console.log('  PASS ' + name);
  } else {
    fail++;
    console.log('  FAIL ' + name + (detail !== undefined ? '  [' + detail + ']' : ''));
  }
}
function section(t) { console.log('\n=== ' + t + ' ==='); }
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ *
 * Minimal fake DOM / media surface
 * ------------------------------------------------------------------ */
function makeElement(tag, id) {
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    id: id || '',
    style: { cssText: '', display: '', transform: '', willChange: '' },
    textContent: '',
    type: '',
    children: [],
    parentElement: null,
    listeners: {},
    videoWidth: 0,
    videoHeight: 0,
    readyState: 0,
    srcObject: null,
    muted: false,
    defaultMuted: false,
    playsInline: false,
    _playImpl: null,
    classList: {
      _s: new Set(),
      add() { for (const c of arguments) this._s.add(c); },
      remove() { for (const c of arguments) this._s.delete(c); },
      contains(c) { return this._s.has(c); }
    },
    setAttribute(k, v) { this[k] = v; },
    appendChild(child) { this.children.push(child); child.parentElement = this; return child; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev) { (this.listeners[ev] || []).slice().forEach((f) => f({ type: ev })); },
    listenerCount(ev) { return (this.listeners[ev] || []).length; },
    querySelector(sel) {
      if (sel && sel.charAt(0) === '#') return this.children.find((c) => c.id === sel.slice(1)) || null;
      return null;
    },
    play() { return this._playImpl ? this._playImpl() : Promise.resolve(); },
    pause() {},
    getBoundingClientRect() { return { x: 0, y: 0, width: 300, height: 400 }; }
  };
  return el;
}

function makeTrack(opts) {
  opts = opts || {};
  return {
    kind: 'video',
    readyState: 'live',
    stopped: false,
    // deviceId/groupId are deliberately present to prove diagnostics never log them.
    settings: { width: 1280, height: 720, frameRate: 30, facingMode: 'environment', deviceId: 'SECRET-DEVICE-ID', groupId: 'SECRET-GROUP-ID' },
    listeners: {},
    getSettings() { return this.settings; },
    stop() { this.stopped = true; this.readyState = 'ended'; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    fire(ev) { (this.listeners[ev] || []).slice().forEach((f) => f()); },
    simulateEnd() { this.readyState = 'ended'; this.stopped = true; this.fire('ended'); }
  };
}

function makeStream(tracks) {
  return {
    getTracks() { return tracks; },
    getVideoTracks() { return tracks; }
  };
}

function harness() {
  const elements = {};
  const viewfinder = makeElement('div', 'viewfinder');
  const video = makeElement('video', 'cameraMainVideo');
  viewfinder.appendChild(video);
  elements.cameraMainVideo = video;
  elements.cameraMainPreviewImg = makeElement('img', 'cameraMainPreviewImg');
  elements.cameraShutterInstruction = makeElement('p', 'cameraShutterInstruction');
  elements.cameraDualCaptureHUD = makeElement('div', 'cameraDualCaptureHUD');
  elements.cameraShutterControls = makeElement('div', 'cameraShutterControls');
  elements.cameraStudioModal = makeElement('div', 'cameraStudioModal');
  elements.cameraFlashOverlay = makeElement('div', 'cameraFlashOverlay');

  function findById(root, id) {
    if (!root) return null;
    if (root.id === id) return root;
    for (const child of root.children) {
      const hit = findById(child, id);
      if (hit) return hit;
    }
    return null;
  }

  const doc = {
    getElementById(id) { return elements[id] || findById(viewfinder, id) || findById(doc.body, id) || null; },
    createElement(tag) { return makeElement(tag); },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    body: makeElement('body')
  };

  const logs = [];
  const sandbox = {
    console: {
      log: (...a) => logs.push(a.join(' ')),
      warn: (...a) => logs.push(a.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(' ')),
      error: (...a) => logs.push(a.join(' '))
    },
    document: doc,
    window: {},
    state: { cameraFacingMode: '', mainMediaStream: null, cameraContext: {} },
    // module-level timer declared next to the engine in app_core.js
    cameraModalHideTimer: null,
    navigator: {
      mediaDevices: {
        getUserMedia: async () => { throw new DOMException('not stubbed', 'NotFoundError'); },
        enumerateDevices: async () => []
      }
    },
    DOMException: global.DOMException,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Promise, Date, Object, String, Number, Boolean, Math, JSON, Array, Error, isNaN,
    captureCurrentGeoLocation() {},
    showToast() {},
    playTactileFeedback() {},
    kandidDrawVideoFrame() { return null; },
    kandidSerializeCanvasJpeg: async () => '',
    record3SecAmbientAudio: async () => ''
  };
  vm.createContext(sandbox);
  vm.runInContext(engineSource + '\nthis.KandidCameraEngine = KandidCameraEngine;', sandbox);
  const engine = sandbox.KandidCameraEngine;
  engine.setState = function (s, d) { this.state = s; }; // silence state logs
  return { engine, elements, video, viewfinder, sandbox, logs, doc };
}

async function run() {
  /* ---------------------------------------------------------------- */
  section('1. getUserMedia rejects with NotAllowedError');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 200;
    const Err = global.DOMException;
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => { throw new Err('denied', 'NotAllowedError'); };
    await h.engine.initialize();
    check('state is ERROR, not READY', h.engine.state === 'ERROR', h.engine.state);
    check('error code is permission', h.engine._lastError && h.engine._lastError.code === 'permission', JSON.stringify(h.engine._lastError));
    const overlay = h.doc.getElementById('cameraErrorOverlay');
    check('error overlay is visible', !!overlay && overlay.style.display === 'flex');
    check('overlay title is the permission message', !!overlay && overlay.querySelector('#cameraErrorTitle').textContent.indexOf('CAMERA ACCESS BLOCKED') === 0);
    check('no raw exception text in user copy', !!overlay && overlay.querySelector('#cameraErrorMessage').textContent.indexOf('NotAllowedError') === -1);
    check('no stream retained', h.engine.mainStream === null && h.sandbox.state.mainMediaStream === null);
    check('no device id/groupId in diagnostics', !h.logs.join('\n').includes('SECRET-'), 'leaked identifier');
  }

  /* ---------------------------------------------------------------- */
  section('2. Stream acquired but preview never becomes ready');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 120;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    await h.engine.initialize();
    check('state is ERROR, not READY', h.engine.state === 'ERROR', h.engine.state);
    check('error code is preview', h.engine._lastError && h.engine._lastError.code === 'preview', JSON.stringify(h.engine._lastError));
    check('readiness reason is timeout', h.engine._readyInfo && h.engine._readyInfo.reason === 'timeout', h.engine._readyInfo && h.engine._readyInfo.reason);
    check('stream tracks stopped on failure', track.stopped === true);
    check('video srcObject cleared', h.video.srcObject === null);
    check('readiness listeners removed', h.video.listenerCount('loadedmetadata') === 0 && h.video.listenerCount('playing') === 0);
  }

  /* ---------------------------------------------------------------- */
  section('3. Delayed readiness via loadedmetadata -> READY');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 1500;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    setTimeout(() => {
      h.video.videoWidth = 1280;
      h.video.videoHeight = 720;
      h.video.readyState = 4;
      h.video.dispatch('loadedmetadata');
    }, 400);
    const t0 = Date.now();
    await h.engine.initialize();
    const elapsed = Date.now() - t0;
    check('state is READY', h.engine.state === 'READY', h.engine.state);
    check('readiness came from an event', h.engine._readyInfo && h.engine._readyInfo.reason === 'event', h.engine._readyInfo && h.engine._readyInfo.reason);
    check('settled before the deadline', elapsed < 1500, elapsed + 'ms');
    check('healthy track not stopped', track.stopped === false);
    check('readiness listeners removed after success', h.video.listenerCount('loadedmetadata') === 0 && h.video.listenerCount('resize') === 0);
  }

  /* ---------------------------------------------------------------- */
  section('4. Dimensions appear without media events (poll fallback)');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 1200;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    setTimeout(() => { h.video.videoWidth = 640; h.video.videoHeight = 480; h.video.readyState = 2; }, 400);
    await h.engine.initialize();
    check('state is READY', h.engine.state === 'READY', h.engine.state);
    check('readiness came from the poll fallback', h.engine._readyInfo && h.engine._readyInfo.reason === 'poll', h.engine._readyInfo && h.engine._readyInfo.reason);
  }

  /* ---------------------------------------------------------------- */
  section('5. play() rejects but the preview still becomes ready');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 1200;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    h.video._playImpl = () => Promise.reject(new (global.DOMException)('blocked', 'NotAllowedError'));
    setTimeout(() => { h.video.videoWidth = 1280; h.video.videoHeight = 720; h.video.readyState = 4; h.video.dispatch('canplay'); }, 400);
    await h.engine.initialize();
    check('play() rejection is not fatal', h.engine.state === 'READY', h.engine.state);
    check('play rejection recorded in diagnostics', h.engine._readyInfo && h.engine._readyInfo.playRejected === true);
  }

  /* ---------------------------------------------------------------- */
  section('6. Duplicate initialize() while READY is ignored');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 800;
    const track = makeTrack();
    let calls = 0;
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => { calls++; return makeStream([track]); };
    h.video.videoWidth = 1280; h.video.videoHeight = 720; h.video.readyState = 4;
    await h.engine.initialize();
    const afterFirst = calls;
    await h.engine.initialize();
    check('state stays READY', h.engine.state === 'READY', h.engine.state);
    check('no second getUserMedia call', calls === afterFirst, 'calls=' + calls);
  }

  /* ---------------------------------------------------------------- */
  section('7. Retry after failed startup succeeds');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 300;
    let attempt = 0;
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => {
      attempt++;
      if (attempt === 1) throw new (global.DOMException)('denied', 'NotAllowedError');
      // A real retry yields a fresh, live track (the failed attempt's track was stopped).
      return makeStream([makeTrack()]);
    };
    // First attempt fails (every constraint retry counts as an attempt)
    await h.engine.initialize();
    check('first attempt ends in ERROR', h.engine.state === 'ERROR', h.engine.state);
    // Retry: preview becomes ready
    h.video.videoWidth = 1280; h.video.videoHeight = 720; h.video.readyState = 4;
    await h.engine.initialize();
    check('ERROR is retryable -> READY', h.engine.state === 'READY', h.engine.state);
    check('error overlay hidden after recovery', h.doc.getElementById('cameraErrorOverlay').style.display === 'none');
  }

  /* ---------------------------------------------------------------- */
  section('8. Close -> reopen recovery');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 800;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    h.video.videoWidth = 1280; h.video.videoHeight = 720; h.video.readyState = 4;
    await h.engine.initialize();
    check('open -> READY', h.engine.state === 'READY', h.engine.state);
    h.engine.stop();
    check('stop() -> IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('stop() releases the stream', track.stopped === true && h.video.srcObject === null);
    const track2 = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track2]);
    await h.engine.initialize();
    check('reopen -> READY again', h.engine.state === 'READY', h.engine.state);
  }

  /* ---------------------------------------------------------------- */
  section('9. Track ends before the preview is ready');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 1500;
    const track = makeTrack();
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => makeStream([track]);
    setTimeout(() => track.simulateEnd(), 120);
    await h.engine.initialize();
    check('state is ERROR', h.engine.state === 'ERROR', h.engine.state);
    check('error code is track-ended', h.engine._lastError && h.engine._lastError.code === 'track-ended', JSON.stringify(h.engine._lastError));
    check('interrupted track is stopped', track.stopped === true);
  }

  /* ---------------------------------------------------------------- */
  section('10. Engine never reports READY on a failed acquisition');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 200;
    h.sandbox.navigator.mediaDevices.getUserMedia = async () => { throw new (global.DOMException)('busy', 'NotReadableError'); };
    const transitions = [];
    const original = h.engine.setState.bind(h.engine);
    h.engine.setState = function (s, d) { transitions.push(s); this.state = s; };
    await h.engine.initialize();
    check('never entered READY', transitions.indexOf('READY') === -1, transitions.join(','));
    check('ended in ERROR', transitions[transitions.length - 1] === 'ERROR', transitions.join(','));
    check('camera-busy copy is used', h.doc.getElementById('cameraErrorOverlay').querySelector('#cameraErrorTitle').textContent.indexOf('CAMERA UNAVAILABLE') === 0);
    h.engine.setState = original;
  }

  console.log('\n=========================================');
  console.log(pass + ' passed, ' + fail + ' failed');
  if (fail > 0) {
    console.log('CAMERA STARTUP HARDENING TESTS FAILED');
    process.exit(1);
  }
  console.log('ALL CAMERA STARTUP HARDENING TESTS PASSED');
}

run().catch((err) => {
  console.error('HARNESS ERROR:', err && err.stack ? err.stack : err);
  process.exit(1);
});
