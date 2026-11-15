#!/usr/bin/env node
/**
 * C2.1 lifecycle race regression tests.
 *
 * Deterministic MOCK tests for: pagehide while getUserMedia is pending, late
 * stream resolution after pagehide / manual close, a stale initialization
 * resolving after a newer session, and automatic-recovery accounting.
 * These do NOT reproduce Vivo/Android camera hardware behaviour.
 *
 * Run: node test_camera_lifecycle_races.js
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
  let srcObject = null;
  Object.defineProperty(el, 'srcObject', {
    get() { return srcObject; },
    set(v) { srcObject = v; if (v) { el.videoWidth = 0; el.videoHeight = 0; el.readyState = 0; } }
  });
  return el;
}

function makeTrack() {
  return {
    kind: 'video', readyState: 'live', stopped: false, muted: false,
    settings: { width: 1280, height: 720, deviceId: 'SECRET-DEVICE-ID' },
    listeners: {},
    getSettings() { return this.settings; },
    stop() { this.stopped = true; this.readyState = 'ended'; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    listenerCount(ev) { return (this.listeners[ev] || []).length; },
    fire(ev) { (this.listeners[ev] || []).slice().forEach((f) => f()); },
    simulateEnd() { this.readyState = 'ended'; this.stopped = true; this.fire('ended'); }
  };
}
const makeStream = (t) => ({ getTracks() { return [t]; }, getVideoTracks() { return [t]; } });

function harness() {
  const elements = {};
  const viewfinder = makeElement('div', 'viewfinder');
  const video = makeElement('video', 'cameraMainVideo');
  viewfinder.appendChild(video);
  elements.cameraMainVideo = video;
  elements.cameraMainPreviewImg = makeElement('img', 'cameraMainPreviewImg');
  elements.cameraShutterInstruction = makeElement('p', 'cameraShutterInstruction');
  elements.cameraDualCaptureHUD = makeElement('div', 'cameraDualCaptureHUD');
  elements.cameraStudioModal = makeElement('div', 'cameraStudioModal');

  function findById(root, id) {
    if (!root) return null;
    if (root.id === id) return root;
    for (const child of root.children) { const hit = findById(child, id); if (hit) return hit; }
    return null;
  }

  const doc = {
    visibilityState: 'visible',
    listeners: {},
    body: makeElement('body'),
    getElementById(id) { return elements[id] || findById(viewfinder, id) || null; },
    createElement(tag) { return makeElement(tag); },
    querySelector() { return null; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev) { (this.listeners[ev] || []).slice().forEach((f) => f({ type: ev })); }
  };
  const win = {
    listeners: {},
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    removeEventListener(ev, fn) { this.listeners[ev] = (this.listeners[ev] || []).filter((f) => f !== fn); },
    dispatch(ev) { (this.listeners[ev] || []).slice().forEach((f) => f({ type: ev })); }
  };

  const logs = [];
  const sandbox = {
    console: {
      log: (...a) => logs.push(a.join(' ')),
      warn: (...a) => logs.push(a.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(' ')),
      error: (...a) => logs.push(a.join(' '))
    },
    document: doc, window: win,
    state: { cameraFacingMode: '', mainMediaStream: null },
    cameraModalHideTimer: null,
    navigator: { mediaDevices: { getUserMedia: async () => { throw new DOMException('x', 'NotFoundError'); }, enumerateDevices: async () => [] } },
    DOMException: global.DOMException,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Promise, Date, Object, String, Number, Boolean, Math, JSON, Array, Error, isNaN,
    captureCurrentGeoLocation() {}, showToast() {}, playTactileFeedback() {}
  };
  vm.createContext(sandbox);
  vm.runInContext(engineSource + '\nthis.KandidCameraEngine = KandidCameraEngine;', sandbox);
  const engine = sandbox.KandidCameraEngine;
  engine.setState = function (s) { this.state = s; };
  engine.readinessTimeoutMs = 800;

  const api = {
    engine, doc, win, video, elements, logs, sandbox,
    calls: 0, tracks: [], lastTrack: null, frameDelayMs: 250, pending: [],
    ready() { video.videoWidth = 1280; video.videoHeight = 720; video.readyState = 4; },
    installGUM() {
      sandbox.navigator.mediaDevices.getUserMedia = async () => {
        api.calls++;
        const t = makeTrack();
        api.tracks.push(t);
        api.lastTrack = t;
        setTimeout(() => { if (api.lastTrack === t) api.ready(); }, api.frameDelayMs);
        return makeStream(t);
      };
    },
    /** getUserMedia that stays pending until resolvePending() is called. */
    deferGUM() {
      sandbox.navigator.mediaDevices.getUserMedia = () => {
        api.calls++;
        return new Promise((resolve) => {
          api.pending.push(() => {
            const t = makeTrack();
            api.tracks.push(t);
            api.lastTrack = t;
            api.ready();
            resolve(makeStream(t));
          });
        });
      };
    },
    resolvePending() {
      const q = api.pending.splice(0);
      q.forEach((fn) => fn());
    },
    deferEnumerate() {
      api.enumPending = [];
      sandbox.navigator.mediaDevices.enumerateDevices = () => new Promise((res) => {
        api.enumPending.push(() => res([]));
      });
    },
    resolveEnumerate() { (api.enumPending || []).splice(0).forEach((fn) => fn()); },
    failGUM(name) {
      sandbox.navigator.mediaDevices.getUserMedia = async () => {
        api.calls++;
        throw new DOMException('test failure', name || 'NotAllowedError');
      };
    },
    hide() { doc.visibilityState = 'hidden'; doc.dispatch('visibilitychange'); },
    show() { doc.visibilityState = 'visible'; doc.dispatch('visibilitychange'); },
    pagehide() { doc.visibilityState = 'hidden'; win.dispatch('pagehide'); },
    pageshow() { doc.visibilityState = 'visible'; win.dispatch('pageshow'); }
  };
  return api;
}

async function open(h) {
  h.installGUM();
  await h.engine.initialize();
  return h;
}

async function run() {
  section('1. pagehide while getUserMedia is pending');
  {
    const h = harness();
    h.deferGUM();
    const p = h.engine.initialize();
    await tick(300);                      // cooldown finished, gUM still pending
    check('acquisition is pending at pagehide', h.calls === 1, 'calls=' + h.calls);
    h.pagehide();
    h.resolvePending();                   // stream resolves AFTER pagehide
    await p;
    await tick(150);
    const t = h.tracks[0];
    check('late stream was stopped', !!t && t.stopped === true);
    check('late stream was never attached', h.video.srcObject === null);
    check('no stream retained', h.engine.mainStream === null);
    check('stale init did not reach READY', h.engine.state !== 'READY', h.engine.state);
    check('stale init left the engine IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('no interruption handlers attached', !t || t.listenerCount('ended') === 0);
  }

  section('2. Late stream resolution after a manual close');
  {
    const h = harness();
    h.deferGUM();
    const p = h.engine.initialize();
    await tick(300);
    h.engine.stop();
    h.resolvePending();
    await p;
    await tick(150);
    check('late stream stopped', h.tracks[0] && h.tracks[0].stopped === true);
    check('never attached', h.video.srcObject === null);
    check('state IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('no stream retained', h.engine.mainStream === null);
  }

  section('3. Foreground after pagehide with a stale initialization');
  {
    const h = harness();
    h.deferGUM();
    const p = h.engine.initialize();
    await tick(300);
    h.pagehide();
    h.installGUM();                       // foreground reacquisition path ready
    h.resolvePending();
    await p;
    const staleTrack = h.tracks[0];
    h.pageshow();
    await tick(900);
    check('stale track stopped', staleTrack.stopped === true);
    check('resumed once', h.calls === 2, 'calls=' + h.calls);
    check('recovered to READY', h.engine.state === 'READY', h.engine.state);
    check('live stream is the new one', h.engine.mainStream === h.engine.mainStream && h.lastTrack.stopped === false);
  }

  section('4. Old initialization resolving after a newer session started');
  {
    const h = harness();
    h.deferGUM();
    const oldInit = h.engine.initialize();
    await tick(300);
    h.pagehide();
    h.engine.stop();
    h.installGUM();
    await h.engine.initialize();          // newer session
    const newTrack = h.lastTrack;
    check('new session READY', h.engine.state === 'READY', h.engine.state);
    h.resolvePending();                   // old acquisition resolves late
    await oldInit;
    await tick(200);
    const staleTrack = h.tracks[h.tracks.length - 1];
    check('old track stopped', staleTrack.stopped === true);
    check('new session still READY', h.engine.state === 'READY', h.engine.state);
    check('new stream still owned', h.engine.mainStream !== null && newTrack.stopped === false);
    check('new stream still attached', h.video.srcObject !== null);
  }

  section('5. Failed automatic recovery counts toward the cap');
  {
    const h = harness();
    await open(h);
    h.failGUM('NotReadableError');
    h.lastTrack.simulateEnd();
    await tick(800);
    check('attempt 1 consumed', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    check('state ERROR', h.engine.state === 'ERROR', h.engine.state);
    h.installGUM();
    await h.engine.initialize();          // manual retry
    check('manual retry READY', h.engine.state === 'READY', h.engine.state);
    check('manual retry did not reset the cap', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    h.lastTrack.simulateEnd();
    await tick(800);
    check('attempt 2 consumed', h.engine._autoRecoveryCount === 2, 'count=' + h.engine._autoRecoveryCount);
    check('READY after second recovery', h.engine.state === 'READY', h.engine.state);
  }

  section('6. Duplicate lifecycle events cannot bypass the cap');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd();
    h.doc.dispatch('visibilitychange');
    h.win.dispatch('pageshow');
    h.doc.dispatch('visibilitychange');
    await tick(900);
    check('only one automatic attempt', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    check('one reacquisition', h.calls === 2, 'calls=' + h.calls);
  }

  section('7. Repeated background/foreground cycles respect the two-attempt cap');
  {
    const h = harness();
    await open(h);
    h.hide(); h.lastTrack.simulateEnd(); h.show();
    await tick(800);
    check('cycle 1 recovered', h.engine.state === 'READY' && h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    h.hide(); h.lastTrack.simulateEnd(); h.show();
    await tick(800);
    check('cycle 2 recovered', h.engine.state === 'READY' && h.engine._autoRecoveryCount === 2, 'count=' + h.engine._autoRecoveryCount);
    const callsAfterTwo = h.calls;
    h.hide(); h.lastTrack.simulateEnd(); h.show();
    await tick(800);
    check('cycle 3 makes no further acquisition', h.calls === callsAfterTwo, 'calls=' + h.calls);
    check('cycle 3 surfaces the retry UI', h.engine.state === 'ERROR', h.engine.state);
    const overlay = h.doc.getElementById('cameraErrorOverlay');
    check('TRY AGAIN card is visible', !!overlay && overlay.style.display === 'flex');
  }

  section('8. Manual close and reopen resets the recovery budget');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd(); await tick(800);
    h.lastTrack.simulateEnd(); await tick(800);
    check('cap reached', h.engine._autoRecoveryCount === 2, 'count=' + h.engine._autoRecoveryCount);
    h.engine.stop();
    check('close resets the counter', h.engine._autoRecoveryCount === 0, 'count=' + h.engine._autoRecoveryCount);
    h.installGUM();
    await h.engine.initialize();
    check('reopen READY', h.engine.state === 'READY', h.engine.state);
    const callsBefore = h.calls;
    h.lastTrack.simulateEnd();
    await tick(800);
    check('automatic recovery works again', h.calls === callsBefore + 1, 'calls=' + h.calls);
    check('counter is 1 in the new session', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
  }

  section('9. pagehide with a live stream releases it without leaking');
  {
    const h = harness();
    await open(h);
    const track = h.lastTrack;
    h.pagehide();
    check('track stopped on pagehide', track.stopped === true);
    check('srcObject cleared', h.video.srcObject === null);
    check('interruption handlers detached', track.listenerCount('ended') === 0);
    check('no stream retained', h.engine.mainStream === null);
    h.pageshow();
    await tick(900);
    check('foreground recovery after pagehide', h.engine.state === 'READY', h.engine.state);
    check('exactly one new acquisition', h.calls === 2, 'calls=' + h.calls);
    check('new track live', h.lastTrack.stopped === false);
  }

  section('10. pagehide with the studio already closed is inert');
  {
    const h = harness();
    await open(h);
    h.engine.stop();
    const callsBefore = h.calls;
    h.pagehide();
    await tick(200);
    check('no acquisition', h.calls === callsBefore, 'calls=' + h.calls);
    check('still IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('not scheduled for resume', h.engine._pageHideInvalidated === false);
  }

  section('11. Duplicate events after a completed recovery');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd();
    await tick(800);
    const callsAfter = h.calls;
    h.doc.dispatch('visibilitychange');
    h.win.dispatch('pageshow');
    h.doc.dispatch('visibilitychange');
    await tick(400);
    check('no second acquisition for the same interruption', h.calls === callsAfter, 'calls=' + h.calls);
    check('count stays at one', h.engine._autoRecoveryCount === 1, 'count=' + h.engine._autoRecoveryCount);
    check('still READY', h.engine.state === 'READY', h.engine.state);
  }

  section('12. Lifecycle event-order matrix');
  {
    // (a) hidden -> pagehide -> visible
    const a = harness();
    await open(a);
    a.hide(); a.pagehide(); a.show();
    await tick(900);
    check('hidden->pagehide->visible recovers once', a.calls === 2 && a.engine.state === 'READY', 'calls=' + a.calls + ' state=' + a.engine.state);

    // (b) pagehide -> pageshow -> visibilitychange(visible)
    const b = harness();
    await open(b);
    b.pagehide(); b.pageshow(); b.doc.dispatch('visibilitychange');
    await tick(900);
    check('pagehide->pageshow->visibilitychange recovers once', b.calls === 2 && b.engine.state === 'READY', 'calls=' + b.calls + ' state=' + b.engine.state);

    // (c) duplicate hidden events do not stack
    const c = harness();
    await open(c);
    c.hide(); c.hide(); c.pagehide(); c.show();
    await tick(900);
    check('duplicate hide events recover once', c.calls === 2, 'calls=' + c.calls);
  }

  section('13. Cap exhaustion while the document is hidden');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd(); await tick(800);
    h.lastTrack.simulateEnd(); await tick(800);
    check('cap reached', h.engine._autoRecoveryCount === 2, 'count=' + h.engine._autoRecoveryCount);
    const stateBefore = h.engine.state;
    h.hide();
    h.lastTrack.simulateEnd();               // third interruption, still hidden
    await tick(300);
    check('no state mutation while hidden', h.engine.state === stateBefore, h.engine.state);
    const overlay = h.doc.getElementById('cameraErrorOverlay');
    check('no error card raised while hidden', !overlay || overlay.style.display !== 'flex');
    check('no acquisition while hidden', h.calls === 3, 'calls=' + h.calls);
  }

  section('14. Cap exhaustion leaves no misleading state or leak');
  {
    const h = harness();
    await open(h);
    h.lastTrack.simulateEnd(); await tick(800);
    h.lastTrack.simulateEnd(); await tick(800);
    const before = h.calls;
    h.lastTrack.simulateEnd();               // visible, cap spent
    await tick(400);
    check('no further acquisition', h.calls === before, 'calls=' + h.calls);
    check('state is ERROR (not READY)', h.engine.state === 'ERROR', h.engine.state);
    check('streams released', h.engine.mainStream === null && h.video.srcObject === null);
    check('track stopped', h.lastTrack.stopped === true || h.tracks[h.tracks.length - 1].stopped === true);
    const overlay = h.doc.getElementById('cameraErrorOverlay');
    check('retry UI shown', !!overlay && overlay.style.display === 'flex');
  }

  section('15. Missing modal element is handled safely');
  {
    const h = harness();
    await open(h);
    delete h.elements.cameraStudioModal;
    let threw = null;
    try {
      h.lastTrack.simulateEnd();
      await tick(700);
    } catch (e) { threw = e && e.message; }
    check('no exception without the modal', threw === null, threw);
    check('engine reached a defined state', ['READY', 'ERROR', 'IDLE'].indexOf(h.engine.state) !== -1, h.engine.state);
    check('no stream leak', h.engine.mainStream === null || h.engine.mainStream.getTracks()[0].stopped === false);
  }

  section('16. pagehide during the readiness wait');
  {
    const h = harness();
    h.engine.readinessTimeoutMs = 800;
    h.installGUM();
    h.frameDelayMs = 5000;                   // frames never arrive in time
    const p = h.engine.initialize();
    await tick(350);                         // stream acquired, waiting for frames
    const track = h.lastTrack;
    check('stream is attached but not ready', !!track && h.video.readyState === 0);
    h.pagehide();
    await p;
    await tick(900);                         // let the readiness deadline expire
    check('stream stopped on pagehide', track.stopped === true);
    check('no READY', h.engine.state !== 'READY', h.engine.state);
    check('nothing attached', h.video.srcObject === null);
    check('no interruption handlers', track.listenerCount('ended') === 0);
  }

  section('17. pagehide during hardware-device discovery');
  {
    const h = harness();
    h.deferEnumerate();
    h.installGUM();
    const p = h.engine.initialize();
    await tick(700);                         // preview ready, awaiting enumerateDevices
    check('preview acquired', h.video.readyState === 4);
    h.pagehide();
    const track = h.lastTrack;
    h.resolveEnumerate();
    await p;
    await tick(200);
    check('no READY after pagehide during discovery', h.engine.state !== 'READY', h.engine.state);
    check('state normalized to IDLE', h.engine.state === 'IDLE', h.engine.state);
    check('stream released', track.stopped === true && h.engine.mainStream === null);
  }

  section('18. Track-ended during a capture does not trigger recovery');
  {
    const h = harness();
    await open(h);
    h.engine.state = 'CAPTURING_REAR';
    const callsBefore = h.calls;
    h.lastTrack.simulateEnd();
    await tick(400);
    check('no acquisition during capture', h.calls === callsBefore, 'calls=' + h.calls);
    check('capture state untouched', h.engine.state === 'CAPTURING_REAR', h.engine.state);
    // and capture() refuses to run while a recovery is in flight
    h.engine.state = 'READY';
    h.engine._recoveryInFlight = true;
    let threw = null;
    try { await h.engine.capture(); } catch (e) { threw = e && e.message; }
    check('capture() is inert during recovery', threw === null, threw);
    h.engine._recoveryInFlight = false;
  }

  console.log('\n=========================================');
  console.log(pass + ' passed, ' + fail + ' failed');
  if (fail > 0) { console.log('LIFECYCLE RACE TESTS FAILED'); process.exit(1); }
  console.log('ALL LIFECYCLE RACE TESTS PASSED');
}

run().catch((e) => { console.error('HARNESS ERROR:', e && e.stack ? e.stack : e); process.exit(1); });
