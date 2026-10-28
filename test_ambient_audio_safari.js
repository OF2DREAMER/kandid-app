#!/usr/bin/env node
/*
 * Behavioral coverage for the 3.0s ambient-audio recorder.
 *
 * The real audioBufferToWav() and record3SecAmbientAudio() are sliced out of
 * app_core.js and executed against controllable fakes for MediaRecorder,
 * getUserMedia, FileReader, AudioContext and timers. Completion order, empty
 * captures, negotiated containers and the watchdog are therefore exercised as
 * real code paths, not as source-text assertions.
 *
 * This is a Node DOM-sandbox test: it proves the JavaScript logic and the bytes
 * the app hands to the media pipeline. It does NOT prove real Safari playback;
 * that still needs a device.
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = fs.readFileSync(path.join(__dirname, "app_core.js"), "utf8");

let checks = 0;
let failures = 0;

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

const WAV_SRC = sliceBetween(
  "function audioBufferToWav(buffer) {",
  "// Robust Dual-Engine 3.0s Ambient Audio Recorder"
);
const REC_SRC = sliceBetween(
  "function record3SecAmbientAudio() {",
  "// KINDID CAMERA - ASYNC FRAME SERIALIZATION"
);

// ── Fakes ───────────────────────────────────────────────────────────────
class FakeFileReader {
  readAsDataURL(blob) {
    const self = this;
    blob.arrayBuffer().then(function(buf) {
      self.result =
        "data:" + (blob.type || "application/octet-stream") + ";base64," +
        Buffer.from(buf).toString("base64");
      if (self.onloadend) self.onloadend();
    }).catch(function() {
      if (self.onerror) self.onerror(new Error("read failed"));
    });
  }
}

function makeRecorder(cfg) {
  cfg = cfg || {};
  return class FakeMediaRecorder {
    static isTypeSupported(type) {
      if (cfg.noIsTypeSupported) return undefined;
      return (cfg.supported || []).indexOf(type) >= 0;
    }
    constructor(stream, options) {
      this.stream = stream;
      this.state = "inactive";
      this.ondataavailable = null;
      this.onstop = null;
      this.mimeType = cfg.negotiated !== undefined
        ? cfg.negotiated
        : ((options && options.mimeType) || "");
    }
    start() {
      this.state = "recording";
      if (cfg.onStart) cfg.onStart(this);
    }
    stop() {
      if (cfg.hang) return; // simulate WebKit never emitting onstop
      if (this.state === "inactive") return;
      this.state = "inactive";
      const size = cfg.chunkSize === 0 ? 0 : (cfg.chunkSize || 64);
      if (this.ondataavailable && size > 0) {
        this.ondataavailable({
          data: new Blob([new Uint8Array(size).fill(7)], { type: this.mimeType || "" })
        });
      }
      if (this.onstop) this.onstop();
    }
  };
}

function makeStream() {
  const tracks = [{ stops: 0, stop() { this.stops++; } }];
  return {
    tracks: tracks,
    stream: {
      getAudioTracks() { return tracks; },
      getTracks() { return tracks; }
    }
  };
}

function makeAudioContext(sampleSets, cfg) {
  cfg = cfg || {};
  return class FakeAudioContext {
    constructor() {
      this.sampleRate = 48000;
      this.state = cfg.suspended ? "suspended" : "running";
      this.destination = { name: "destination" };
      this.closeCalls = 0;
      this.sourceCreated = 0;
      if (cfg.registry) cfg.registry.push(this);
    }
    resume() {
      if (cfg.deferResume) {
        const self = this;
        return new Promise(function(resolve) {
          cfg.resolveResume = function() { self.state = "running"; resolve(); };
        });
      }
      this.state = "running";
      return Promise.resolve();
    }
    close() { this.closed = true; this.closeCalls++; return Promise.resolve(); }
    createMediaStreamSource() {
      if (cfg.failSource) throw new Error("AudioContext source unavailable");
      this.sourceCreated++;
      return {
        connect(node) {
          (sampleSets || []).forEach(function(set) {
            if (node && node.onaudioprocess) {
              node.onaudioprocess({ inputBuffer: { getChannelData() { return Float32Array.from(set); } } });
            }
          });
        },
        disconnect() {}
      };
    }
    createScriptProcessor() {
      return { onaudioprocess: null, connect() {}, disconnect() {} };
    }
    createBuffer(channels, length, rate) {
      if (cfg.failBuffer) throw new Error("createBuffer unavailable");
      const data = new Float32Array(length);
      return { sampleRate: rate, length: length, getChannelData() { return data; } };
    }
  };
}

function makeContext(opts) {
  opts = opts || {};
  const state = { timers: [], nextId: 1, getUserMediaCalls: 0 };

  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    Blob: Blob,
    ArrayBuffer: ArrayBuffer,
    DataView: DataView,
    Float32Array: Float32Array,
    Uint8Array: Uint8Array,
    Promise: Promise,
    Math: Math,
    JSON: JSON,
    setTimeout(fn, ms) {
      const id = state.nextId++;
      state.timers.push({ id: id, fn: fn, ms: ms });
      return id;
    },
    clearTimeout(id) {
      state.timers = state.timers.filter(function(t) { return t.id !== id; });
    },
    navigator: {
      mediaDevices: {
        getUserMedia(constraints) {
          state.getUserMediaCalls++;
          if (opts.deferredMic) {
            // Permission prompt stays open until the test resolves it.
            return new Promise(function(resolve, reject) {
              state.resolveMic = resolve;
              state.rejectMic = reject;
            });
          }
          if (opts.denyMic) return Promise.reject(new Error("NotAllowedError"));
          return Promise.resolve(opts.stream);
        }
      }
    },
    FileReader: FakeFileReader,
    window: opts.window || {},
    MediaRecorder: opts.MediaRecorder
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    WAV_SRC + "\n" + REC_SRC +
    "\nglobalThis.__record = record3SecAmbientAudio;\nglobalThis.__wav = audioBufferToWav;\n",
    sandbox
  );

  return {
    sandbox: sandbox,
    state: state,
    fireNextTimer() {
      if (!state.timers.length) return false;
      state.timers.sort(function(a, b) { return a.ms - b.ms; });
      const timer = state.timers.shift();
      timer.fn();
      return true;
    },
    fireTimer(ms) {
      const idx = state.timers.findIndex(function(t) { return t.ms === ms; });
      if (idx < 0) return false;
      const timer = state.timers.splice(idx, 1)[0];
      timer.fn();
      return true;
    },
    pendingTimers() { return state.timers.length; }
  };
}

function tick() {
  return new Promise(function(resolve) { setImmediate(resolve); });
}

async function startRecording(ctx) {
  const promise = ctx.sandbox.__record();
  await tick(); // let getUserMedia settle, but do NOT await the recording itself
  return { promise: promise };
}

function decodeDataUrl(url) {
  const idx = String(url || "").indexOf(",");
  return Buffer.from(idx >= 0 ? url.slice(idx + 1) : "", "base64");
}

async function main() {
  // ── 1. Safari negotiates audio/mp4 ──────────────────────────────────
  console.log("=== 1. Container negotiation ===");
  {
    const s = makeStream();
    const ctx = makeContext({ stream: s.stream, MediaRecorder: makeRecorder({ supported: ["audio/mp4"], chunkSize: 48 }) });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer(); // the 3.0s stop
    const url = await p;
    check("Safari-negotiated audio/mp4 is used in the data URL", url.indexOf("data:audio/mp4;base64,") === 0, String(url).slice(0, 40));
    check("recorded payload is non-empty", decodeDataUrl(url).length === 48);
    check("microphone track is stopped after a successful capture", s.tracks[0].stops >= 1);
    check("watchdog timer is cleared on success", ctx.pendingTimers() === 0);
  }

  // ── 2. recorder.mimeType overrides the requested type ───────────────
  console.log("=== 2. Negotiated container wins over requested ===");
  {
    const s = makeStream();
    const ctx = makeContext({
      stream: s.stream,
      // audio/webm is "supported", but the recorder hands back audio/mp4.
      MediaRecorder: makeRecorder({ supported: ["audio/webm"], negotiated: "audio/mp4", chunkSize: 32 })
    });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer();
    const url = await p;
    check("data URL declares the recorder's real container", url.indexOf("data:audio/mp4;base64,") === 0, String(url).slice(0, 40));
    check("data URL does not mislabel bytes as webm", url.indexOf("audio/webm") === -1);
  }

  // ── 3. isTypeSupported missing (older WebKit) ───────────────────────
  console.log("=== 3. Missing isTypeSupported ===");
  {
    const s = makeStream();
    const ctx = makeContext({ stream: s.stream, MediaRecorder: makeRecorder({ noIsTypeSupported: true, negotiated: "audio/mp4", chunkSize: 16 }) });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer();
    const url = await p;
    check("falls back to recorder.mimeType, not a guessed audio/webm", url.indexOf("data:audio/mp4;base64,") === 0, String(url).slice(0, 40));
  }

  // ── 4. Empty capture is rejected ────────────────────────────────────
  console.log("=== 4. Empty capture ===");
  {
    const s = makeStream();
    const ctx = makeContext({ stream: s.stream, MediaRecorder: makeRecorder({ supported: ["audio/mp4"], chunkSize: 0 }) });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer();
    const url = await p;
    check("empty recording resolves to an empty string", url === "", JSON.stringify(url));
    check("empty recording still releases the microphone", s.tracks[0].stops >= 1);
  }

  // ── 5. Hung recorder is bounded by the watchdog ─────────────────────
  console.log("=== 5. Hung MediaRecorder ===");
  {
    const s = makeStream();
    const ctx = makeContext({ stream: s.stream, MediaRecorder: makeRecorder({ supported: ["audio/mp4"], hang: true }) });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    let settled = false;
    p.then(function() { settled = true; });
    ctx.fireNextTimer(); // 3.0s stop -> recorder never fires onstop
    await tick();
    check("recording does not resolve while onstop is pending", settled === false);
    ctx.fireNextTimer(); // the 6.0s watchdog
    const url = await p;
    check("watchdog resolves with no audio instead of hanging publish", url === "", JSON.stringify(url));
    check("watchdog releases the microphone", s.tracks[0].stops >= 1);
  }

  // ── 6. Microphone denial ────────────────────────────────────────────
  console.log("=== 6. Microphone permission denied ===");
  {
    const ctx = makeContext({ denyMic: true, MediaRecorder: makeRecorder({ supported: ["audio/mp4"] }) });
    const url = await ctx.sandbox.__record();
    check("denied microphone resolves to an empty string", url === "", JSON.stringify(url));
    check("retries once with plain audio:true", ctx.state.getUserMediaCalls === 2, String(ctx.state.getUserMediaCalls));
    check("no watchdog is left running", ctx.pendingTimers() === 0);
  }

  // ── 7. WAV fallback ─────────────────────────────────────────────────
  console.log("=== 7. WebAudio WAV fallback ===");
  {
    const s = makeStream();
    const ctx = makeContext({
      stream: s.stream,
      MediaRecorder: undefined,
      window: { AudioContext: makeAudioContext([[0, 0.5, -0.5], [1, -1]]) }
    });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer();
    const url = await p;
    check("fallback returns a WAV data URL", url.indexOf("data:audio/wav;base64,") === 0, String(url).slice(0, 40));
    const bytes = decodeDataUrl(url);
    check("WAV length is 44-byte header + 5 PCM samples", bytes.length === 44 + 5 * 2, String(bytes.length));
    check("WAV has RIFF/WAVE markers", bytes.slice(0, 4).toString() === "RIFF" && bytes.slice(8, 12).toString() === "WAVE");
    check("WAV is PCM mono 16-bit", bytes.readUInt16LE(20) === 1 && bytes.readUInt16LE(22) === 1 && bytes.readUInt16LE(34) === 16);
    check("WAV preserves the AudioContext sample rate", bytes.readUInt32LE(24) === 48000, String(bytes.readUInt32LE(24)));
    check("WAV data chunk size matches the payload", bytes.readUInt32LE(40) === bytes.length - 44);
    check("WAV PCM samples are encoded correctly",
      bytes.readInt16LE(44) === 0 && bytes.readInt16LE(46) === 16383 &&
      bytes.readInt16LE(48) === -16384 && bytes.readInt16LE(50) === 32767 &&
      bytes.readInt16LE(52) === -32768,
      [bytes.readInt16LE(44), bytes.readInt16LE(46), bytes.readInt16LE(48), bytes.readInt16LE(50), bytes.readInt16LE(52)].join(","));
    check("fallback releases the microphone", s.tracks[0].stops >= 1);
  }

  // ── 8. WAV fallback with no samples ─────────────────────────────────
  console.log("=== 8. WAV fallback without samples ===");
  {
    const s = makeStream();
    const ctx = makeContext({
      stream: s.stream,
      MediaRecorder: undefined,
      window: { AudioContext: makeAudioContext([]) }
    });
    const rec = await startRecording(ctx);
    const p = rec.promise;
    ctx.fireNextTimer();
    const url = await p;
    check("a silent fallback capture is rejected instead of shipped", url === "", JSON.stringify(url));
    check("rejected fallback still releases the microphone", s.tracks[0].stops >= 1);
  }

  // ── 9. audioBufferToWav contract ────────────────────────────────────
  console.log("=== 9. audioBufferToWav ===");
  {
    const ctx = makeContext({ MediaRecorder: undefined });
    const blob = ctx.sandbox.__wav({
      sampleRate: 44100,
      getChannelData() { return Float32Array.from([0, 1, -1, 0.25]); }
    });
    check("encoder returns an audio/wav Blob", blob && blob.type === "audio/wav", blob && blob.type);
    const bytes = Buffer.from(await blob.arrayBuffer());
    check("mono 16-bit, 44-byte header", bytes.length === 44 + 4 * 2 && bytes.readUInt16LE(34) === 16);
    check("byte rate and block align match mono 16-bit",
      bytes.readUInt32LE(28) === 44100 * 2 && bytes.readUInt16LE(32) === 2);
    check("clipping is bounded to int16 range",
      bytes.readInt16LE(44) === 0 && bytes.readInt16LE(46) === 32767 &&
      bytes.readInt16LE(48) === -32768 && bytes.readInt16LE(50) === 8191,
      [bytes.readInt16LE(44), bytes.readInt16LE(46), bytes.readInt16LE(48), bytes.readInt16LE(50)].join(","));
  }

  // ── 10. Permission resolves after the watchdog ──────────────────────
  console.log("=== 10. Late getUserMedia resolution after the watchdog ===");
  {
    const s = makeStream();
    let starts = 0;
    const ctx = makeContext({
      deferredMic: true,
      MediaRecorder: makeRecorder({ supported: ["audio/mp4"], onStart() { starts++; } })
    });
    const p = ctx.sandbox.__record();
    await tick();
    ctx.fireNextTimer(); // 6s watchdog fires while permission is still pending
    await tick();
    ctx.state.resolveMic(s.stream); // permission finally granted
    await tick();
    const url = await p;
    check("late permission resolves to an empty string", url === "", JSON.stringify(url));
    check("no recorder is constructed or started after settlement", starts === 0, String(starts));
    check("every track on the late stream is stopped", s.tracks[0].stops >= 1, String(s.tracks[0].stops));
    check("no watchdog is left running after the race", ctx.pendingTimers() === 0, String(ctx.pendingTimers()));
  }

  // ── 11. AudioContext cleanup on fallback failures ───────────────────
  console.log("=== 11. AudioContext cleanup on fallback failure ===");
  {
    const s = makeStream();
    const registry = [];
    const ctx = makeContext({
      stream: s.stream,
      MediaRecorder: undefined,
      window: { AudioContext: makeAudioContext([], { failSource: true, registry: registry }) }
    });
    const url = await ctx.sandbox.__record();
    check("failed WebAudio setup resolves to an empty string", url === "", JSON.stringify(url));
    check("AudioContext is closed after a setup failure",
      registry.length === 1 && registry[0].closeCalls >= 1,
      registry.length ? String(registry[0].closeCalls) : "no context created");
    check("microphone is stopped after a fallback setup failure", s.tracks[0].stops >= 1, String(s.tracks[0].stops));
  }
  {
    const s = makeStream();
    const registry = [];
    const ctx = makeContext({
      stream: s.stream,
      MediaRecorder: undefined,
      window: { AudioContext: makeAudioContext([[0, 1]], { failBuffer: true, registry: registry }) }
    });
    const rec = await startRecording(ctx);
    ctx.fireNextTimer();
    const url = await rec.promise;
    check("WAV encoding failure resolves to an empty string", url === "", JSON.stringify(url));
    check("AudioContext is closed when WAV encoding fails",
      registry.length === 1 && registry[0].closeCalls >= 1,
      registry.length ? String(registry[0].closeCalls) : "no context created");
  }

  // ── 12. Watchdog during asynchronous AudioContext resume ────────────
  console.log("=== 12. Watchdog during AudioContext resume ===");
  {
    const s = makeStream();
    const registry = [];
    const audioCfg = { suspended: true, deferResume: true, registry: registry };
    const ctx = makeContext({
      stream: s.stream,
      MediaRecorder: undefined,
      window: { AudioContext: makeAudioContext([[0, 1]], audioCfg) }
    });
    const p = ctx.sandbox.__record();
    await tick();
    check("AudioContext is created and suspended", registry.length === 1 && registry[0].state === "suspended");
    ctx.fireTimer(6000); // watchdog fires while resume() is still pending
    await tick();
    audioCfg.resolveResume(); // audio hardware finishes starting afterwards
    await tick();
    await tick();
    const url = await p;
    check("watchdog during resume resolves to an empty string", url === "", JSON.stringify(url));
    check("no capture pipeline is created after settlement",
      registry.length === 1 && registry[0].sourceCreated === 0,
      registry.length ? String(registry[0].sourceCreated) : "no context");
    check("microphone tracks are stopped after the resume race", s.tracks[0].stops >= 1, String(s.tracks[0].stops));
    check("AudioContext is closed after the resume race",
      registry.length === 1 && registry[0].closeCalls >= 1,
      registry.length ? String(registry[0].closeCalls) : "no context");
    check("no timers remain after the resume race", ctx.pendingTimers() === 0, String(ctx.pendingTimers()));
  }

  console.log("\n" + (checks - failures) + "/" + checks + " checks passed");
  if (failures) {
    console.log(failures + " check(s) FAILED");
    process.exitCode = 1;
  }
}

main().catch(function(err) {
  console.error("Harness error:", err);
  process.exitCode = 1;
});
