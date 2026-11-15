#!/usr/bin/env node
/**
 * C2 camera lifecycle recovery tests.
 *
 * Deterministic MOCK tests of KandidCameraEngine's lifecycle/recovery control
 * flow: background/foreground, track mute/unmute/ended, recovery limits and
 * race safety. They do NOT reproduce Vivo/Android camera hardware behaviour.
 *
 * Run: node test_camera_lifecycle_recovery.js
 */
'use strict';

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, 'app_core.js'), 'utf8');
const START = src.indexOf('const KandidCameraEngine = {');
const END = src.indexOf('window.KandidCameraEngine = KandidCameraEngine;');
if (START < 0 || END < START) {
  console.error('FATAL: could not locate the KandidCameraEngine object');
  process.exit(1);
}
const engineSource = src.slice(START, END).replace(/^const KandidCameraEngine/, 'var KandidCameraEngine');

let pass = 0;
let fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (detail !== undefined ? '  [' + detail + ']' : '')); }
}
function section(t) { console.log('\n=== ' + t + ' ==='); }
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------- fake DOM / media ---------------- */
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
    muted: false,
    defaultMuted: false,
    playsInline: false,
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
    play() { return Promise.resolve(); },
    pause() {},
    getBoundingClientRect() { return { x: 0, y: 0, width: 300, height: 400 }; }
  };
  // Like a real element: attaching a new source resets the decoded-frame state.
  let srcObject = null;
  Object.defineProperty(el, 'srcObject', {
    get() { return srcObject; },
    set(v) {
      srcObject = v;
      if (v) { el.videoWidth = 0; el.videoHeight = 0; el.readyState = 0; }
    }
  });
  return el;
}

function makeTrack() {
  return {
    kind: 'video',
    readyState: 'live',
    stopped: false,
    muted: false,
    settings: { width: 1280, height: 720, frameRate: 30, facingMode: 'environment', deviceId: 'SECRET-DEVICE-ID' },
    listeners: {},
    getSettings() { return this.settings; },
    stop() { this.stopped = true; this.readyState = 'ended'; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    fire(ev) { (this.listeners[ev] || []).slice().forEach((f) => f()); },
    simulateEnd() { this.readyState = 'ended'; this.stopped = true; this.fire('ended'); },
    simulateMute() { this.muted = true; this.fire('mute'); },
    simulateUnmute() { this.muted = false; this.fire('unmute'); }
  };
}

function makeStream(track) {
  return { getTracks() { return [track]; }, getVideoTracks() { return [track]; } };
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
    visibilityState: 'visible',
    listeners: {},
    body: makeElement('body'),
    getElementById(id) { return elements[id] || findById(viewfinder, id) || null; },
    createElement(tag) { return makeElement(tag); },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev) { (this.listeners[ev] || []).slice().forEach((f) => f({ type: ev })); },
    listenerCount(ev) { return (this.listeners[ev] || []).length; }
  };

  const win = {
    listeners: {},
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev) { (this.listeners[ev] || []).slice().forEach((f) => f({ type: ev })); },
    listenerCount(ev) { return (this.listeners[ev] || []).length; }
  };

  const logs = [];
  const sandbox = {
    console: {
      log: (...a) => logs.push(a.join(' ')),
      warn: (...a) => logs.push(a.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(' ')),
      error: (...a) => logs.push(a.join(' '))
    },
    document: doc,
    window: win,
    state: { cameraFacingMode: '', mainMediaStream: null },
    cameraModalHideTimer: null,
    navigator: { mediaDevices: { getUserMedia: async () => { throw new DOMException('x', 'NotFoundError'); }, enumerateDevices: async () => [] } },
    DOMException: global.DOMException,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Promise, Date, Object, String, Number, Boolean, Math, JSON, Array, Error, isNaN,
    captureCurrentGeoLocation() {},
    showToast() {},
    playTactileFeedback() {}
  };
  vm.createContext(sandbox);
  vm.runInContext(engineSource + '\nthis.KandidCameraEngine = KandidCameraEngine;', sandbox);
  const engine = sandbox.KandidCameraEngine;
  engine.setState = function (s) { this.state = s; };
  engine.readinessTimeoutMs = 800;

  const api = {
    engine, doc, win, video, elements, logs, sandbox,
    calls: 0, tracks: [], lastTrack: null, frameDelayMs: 250,
    ready() { video.videoWidth = 1280; video.videoHeight = 720; video.readyState = 4; },
    /** Each acquisition yields a FRESH track (as a real retry would). */
    installGUM() {
      sandbox.navigator.mediaDevices.getUserMedia = async () => {
        api.calls++;
        const t = makeTrack();
        api.tracks.push(t);
        api.lastTrack = t;
        // decoded frames arrive shortly after acquisition
        setTimeout(() => { if (api.lastTrack === t) api.ready(); }, api.frameDelayMs);
        return makeStream(t);
      };
    },
    failGUM(name) {
      sandbox.navigator.mediaDevices.getUserMedia = async () => {
        api.calls++;
        throw new DOMException('test failure', name || 'NotAllowedError');
      };
    },
    hide() { doc.visibilityState = 'hidden'; doc.dispatch('visibilitychange'); },
    show() { doc.visibilityState = 'visible'; doc.dispatch('visibilitychange'); }
  };
  return api;
}

async function open(h) {
  h.installGUM();
  await h.engine.initialize();
  return h;
}

async function run() {
  section('1. Background + foreground with a healthy stream');
  {
    const h = harness();
    await open(h);
    check('open -> READY', h.engine.state === 'READY', h.engine.state);
    check('lifecycle bound once', h.doc.listenerCount('visibilitychange') === 1, h.doc.listenerCount('visibilitychange'));
    const track = h.lastTrack;
    h.hide();
    await tick(60);
    check('no recovery while hidden', h.calls === 1, 'calls=' + h.calls);
    h.show();
    await tick(350);
    check('healthy stream retained', h.calls === 1, 'calls=' + h.calls);
    check('still READY', h.engine.state === 'READY', h.engine.state);
    check('track still live', track.stopped === false);
  }

  section('2. Background + foreground after the stream died');
  {
    const h = harness();
    await open(h);
    const first = h.lastTrack;
    h.hide();
    first.simulateEnd();               // died while hidden: no recovery yet
    await tick(80);
    check('no recovery attempt while hidden', h.calls === 1, 'calls=' + h.calls);
    h.show();
    await tick(900);
    check('exactly one reacquisition', h.calls === 2, 'calls=' + h.calls);
    check('recovered to READY', h.engine.state === 'READY', h.engine.state);
  }

  section('3. Track mute then unmute inside the grace period');
  {
    const h = harness();
    h.engine.muteGraceMs = 300;
    await open(h);
    const track = h.lastTrack;
    track.simulateMute();
    await tick(80);
    track.simulateUnmute();
    await tick(500);
    check('no reacquisition for a transient mute', h.calls === 1, 'calls=' + h.calls);
    check('retained the original stream', h.engine.state === 'READY' && track.stopped === false);
  }

  section('4. Track mute without unmute');
  {
    const h = harness();
    h.engine.muteGraceMs = 120;
    await open(h);
    h.lastTrack.simulateMute();
    await tick(100);
    check('no immediate reacquisition', h.calls === 1, 'calls=' + h.calls);
    await tick(900);
    check('one recovery after the grace period', h.calls === 2, 'calls=' + h.calls);
    check('recovered to READY', h.engine.state === 'READY', h.engine.state);
  }

  section('5. Track ended while the studio stays open');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd();
    await tick(900);
    check('one automatic recovery', h.calls === 2, 'calls=' + h.calls);
    check('ends READY', h.engine.state === 'READY', h.engine.state);
    check('old track released', h.tracks[0].stopped === true);
  }

  section('6. Track ended after a manual close');
  {
    const h = harness();
    await open(h);
    const track = h.lastTrack;
    h.engine.stop();
    check('closed -> IDLE', h.engine.state === 'IDLE', h.engine.state);
    track.simulateEnd();
    await tick(600);
    check('no reacquisition after close', h.calls === 1, 'calls=' + h.calls);
    check('still IDLE', h.engine.state === 'IDLE', h.engine.state);
  }

  section('7. Duplicate visibilitychange / pageshow events');
  {
    const h = harness();
    await open(h);
    h.hide();
    h.lastTrack.simulateEnd();
    h.show();
    h.show();
    h.win.dispatch('pageshow');
    h.doc.dispatch('visibilitychange');
    await tick(900);
    check('only one reacquisition', h.calls === 2, 'calls=' + h.calls);
    check('READY once', h.engine.state === 'READY', h.engine.state);
    check('one lifecycle listener still', h.doc.listenerCount('visibilitychange') === 1);
  }

  section('8. Close while a recovery is pending');
  {
    const h = harness();
    await open(h);
    const pending = h.engine._attemptRecovery('test-pending');
    h.engine.stop();                       // user closes mid-recovery
    await pending;
    await tick(600);
    check('stays IDLE (no READY resurrection)', h.engine.state === 'IDLE', h.engine.state);
    check('no stream retained', h.engine.mainStream === null);
    check('no error card visible', !h.elements.cameraErrorOverlay || h.elements.cameraErrorOverlay.style.display !== 'flex');
  }

  section('9. Recovery failure falls back to ERROR + manual retry');
  {
    const h = harness();
    await open(h);
    h.failGUM('NotReadableError');
    h.lastTrack.simulateEnd();
    await tick(800);
    // One recovery *cycle* (the constraint ladder may call getUserMedia several times).
    check('one recovery cycle attempted', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    check('state is ERROR after failed recovery', h.engine.state === 'ERROR', h.engine.state);
    const overlay = h.doc.getElementById('cameraErrorOverlay');
    check('TRY AGAIN card is visible', !!overlay && overlay.style.display === 'flex');
    check('manual retry button exists', !!h.doc.getElementById('cameraErrorRetryBtn'));
    check('no retry loop after failure', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    check('no stream left behind', h.engine.mainStream === null);
    h.installGUM();                       // user taps TRY AGAIN, camera now works
    await h.engine.initialize();
    check('manual retry -> READY', h.engine.state === 'READY', h.engine.state);
    check('card hidden after manual retry', overlay.style.display === 'none');
  }

  section('10. No duplicate acquisition during an in-flight recovery');
  {
    const h = harness();
    await open(h);
    const a = h.engine._attemptRecovery('dup-1');
    const b = h.engine._attemptRecovery('dup-2');
    const c = h.engine._attemptRecovery('dup-3');
    const [ra, rb, rc] = await Promise.all([a, b, c]);
    await tick(300);
    check('concurrent attempts are rejected', rb === false && rc === false, String(rb) + '/' + String(rc));
    check('first attempt recovered', ra === true && h.engine.state === 'READY', h.engine.state);
    check('streams acquired once per attempt', h.calls === 2, 'calls=' + h.calls);
  }

  section('11. Stale session cannot transition a closed studio to READY');
  {
    const h = harness();
    await open(h);
    h.engine.stop();
    const transitions = [];
    h.engine.setState = function (s) { transitions.push(s); this.state = s; };
    const pending = h.engine.initialize();  // opened again
    setTimeout(() => h.engine.stop(), 80);  // closed mid-initialization
    await pending;
    await tick(600);
    check('close during init stays IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('never READY after the close', transitions.indexOf('READY') === -1, transitions.join(','));
    check('no retained stream', h.engine.mainStream === null);
  }

  section('12. Lifecycle binding is idempotent across opens');
  {
    const h = harness();
    await open(h);
    h.engine.stop();
    await open(h);
    h.engine.stop();
    await open(h);
    check('visibilitychange listener not duplicated', h.doc.listenerCount('visibilitychange') === 1, h.doc.listenerCount('visibilitychange'));
    check('pageshow listener not duplicated', h.win.listenerCount('pageshow') === 1, h.win.listenerCount('pageshow'));
    check('pagehide listener not duplicated', h.win.listenerCount('pagehide') === 1, h.win.listenerCount('pagehide'));
  }

  console.log('\n=========================================');
  console.log(pass + ' passed, ' + fail + ' failed');
  if (fail > 0) { console.log('LIFECYCLE RECOVERY TESTS FAILED'); process.exit(1); }
  console.log('ALL LIFECYCLE RECOVERY TESTS PASSED');
}

run().catch((e) => { console.error('HARNESS ERROR:', e && e.stack ? e.stack : e); process.exit(1); });
