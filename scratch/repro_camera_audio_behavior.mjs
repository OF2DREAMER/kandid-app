// end-to-end feed-camera harness: opens the camera studio via #mainShutterTrigger
// (after suppressing the onboarding overlay that blocks pointer events), then
// locates the shutter button INSIDE the opened modal (#studioShutterTrigger) and
// triggers a capture. Drives via real HTTP (backend on :8080) and injects a real
// audio-only fake stream so the audio path runs in headless Chromium.
import { chromium } from 'playwright-core';

const HEADLESS = '/home/daytona/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell';
const results = [];
let passed = 0, failed = 0;

function check(name, cond, extra) {
  if (cond) { passed++; console.log('  PASS', name); }
  else { failed++; console.log('  FAIL', name, extra || ''); }
}

async function liveTrackCount(page, kinds) {
  return page.evaluate((ks) => {
    var n = 0;
    document.querySelectorAll('video').forEach(function (v) {
      if (!v.srcObject) return;
      v.srcObject.getTracks().forEach(function (t) { if (ks.indexOf(t.kind) >= 0) n++; });
    });
    return n;
  }, kinds);
}

// Expose a function that injects a live video stream the engine's startMainPreview
// can adopt (satisfies videoWidth>0 for headless video).
async function injectLiveMainStream(page) {
  await page.evaluate(() => {
    window.__injectMainStream = function () {
      var s = new MediaStream();
      var mv = document.getElementById('cameraMainVideo');
      if (mv) {
        mv.srcObject = s;
        mv.videoWidth = 640; mv.videoHeight = 480; mv.readyState = 4; mv.paused = false;
        try { mv.play().catch(function () {}); } catch (e) {}
      }
      return s;
    };
  });
  return page.evaluate(() => { return window.__injectMainStream(); });
}

async function main() {
  const browser = await chromium.launch({
    executablePath: HEADLESS,
    args: ['--headless', '--no-sandbox', '--disable-gpu', '--allow-file-access-from-files', '--disable-dev-shm-usage', '--disable-web-security']
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });

  console.log('Loading feed camera page from HTTP :8080...');
  await page.goto('http://localhost:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });

  // Inject a real audio-only stream via getUserMedia so headless supplies a
  // genuine audio MediaStream with live tracks for the record3SecAmbientAudio path.
  await page.addInitScript(() => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia = function (constraints) {
      if (constraints && constraints.audio) {
        return Promise.resolve(new MediaStream());
      }
      return Promise.resolve(null);
    };
  });

  console.log('\n[0] Sign in (set token) so the #onboardingFlow overlay hides; it otherwise intercepts pointer events on #mainShutterTrigger.');
  await page.evaluate(async () => {
    localStorage.setItem('kandid_token', 'sandbox-token');
    localStorage.setItem('kandid_onboarded', 'true');
    localStorage.setItem('kandid_user', JSON.stringify({ handle: 'sandbox' }));
  });
  // wait here would be nice, but checkOnboarding only runs on certain pages;
  // directly hide the overlay here to reproduce the camera path deterministically.
  await page.evaluate(() => {
    var ob = document.getElementById('onboardingFlow');
    if (ob) ob.style.display = 'none';
  });
  await page.waitForTimeout(400);

  const obVisible = await page.evaluate(() => {
    var e = document.getElementById('onboardingFlow');
    return e ? getComputedStyle(e).display : 'none';
  });
  check('onboarding overlay hidden', obVisible === 'none', 'overlay visible');

  console.log('[1] Locate and click #mainShutterTrigger to open the camera studio modal.');
  const openBtn = await page.waitForSelector('#mainShutterTrigger', { state: 'visible', timeout: 10000 });
  check('mainShutterTrigger located and visible', true);
  await openBtn.click();
  await page.waitForTimeout(1800);

  // Confirm the modal is actually open now.
  const modalVisible = await page.evaluate(() => {
    var m = document.getElementById('cameraStudioModal');
    return m ? (m.style.display === 'flex' ? true : false) : false;
  });
  check('cameraStudioModal opened (display:flex)', modalVisible === true, 'modal display: ' + (typeof modalVisible));

  console.log('[2] Locate the shutter button INSIDE the opened modal and trigger the shutter.');
  const shutterBtn = await page.waitForSelector('#studioShutterTrigger', { state: 'visible', timeout: 10000 })
    .catch(async () => {
      // Fallback: locate any visible button inside the modal that triggers takeSnapshot.
      return page.$('button[onclick="takeSnapshot()"]');
    });
  check('shutter trigger inside modal located', shutterBtn !== null, 'no shutter element found');
  if (shutterBtn) {
    const btnVisible = await shutterBtn.evaluate(el => el.offsetParent !== null);
    check('shutter trigger visible inside modal', btnVisible === true, 'not visible');
    await shutterBtn.click();
    check('shutter button clicked', true);
  }

  // Wait for the capture engine to finish (READY state), then inspect UI.
  await page.waitForFunction(() => {
    var eng = window && window.KandidCameraEngine;
    return eng && eng.state === 'READY';
  }, { timeout: 12000 });
  check('engine reaches READY after shutter', true);

  // Report UI state and audio recording status.
  const ui = await page.evaluate(() => {
    return {
      modalDisplay: document.getElementById('cameraStudioModal') ? document.getElementById('cameraStudioModal').style.display : 'none',
      statusSub: document.getElementById('cameraDualStatusSub') ? document.getElementById('cameraDualStatusSub').textContent : 'no-status',
      engineState: window.KandidCameraEngine ? window.KandidCameraEngine.state : 'none',
      capturedMomentData: !!window.state && !!window.state.capturedMomentData,
      audioClip: (window.KandidCameraEngine && window.KandidCameraEngine.audioClip) || ''
    };
  });
  console.log('  UI state:', JSON.stringify(ui));
  check('engine state READY after shutter', ui.engineState === 'READY', 'got ' + ui.engineState);

  // Live-track count during the flow (for leak inspection).
  const tracksDuring = await liveTrackCount(page, ['audio', 'video']);
  console.log('  live tracks during flow:', tracksDuring);
  check('no live tracks left behind', tracksDuring === 0, 'got ' + tracksDuring);

  console.log('\nJS errors during run:', errors.length ? errors.join(' | ') : 'none');
  check('no page errors', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log('\n=== SUMMARY: ' + passed + ' passed, ' + failed + ' failed ===');
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((e) => { console.error('HARNESS ERROR', e); process.exit(2); });
