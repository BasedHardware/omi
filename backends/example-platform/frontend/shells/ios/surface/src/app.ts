import { bridge, BRIDGE_CONTRACT_VERSION, type TranscriptEvent } from './bridge.g.js';

const $ = (id: string) => document.getElementById(id) as HTMLElement;
const out = $('out');
const benchOut = $('bench');

// Build stamp is rewritten by tools/build-surface.mjs so we can see, on device,
// which surface build we are looking at (the OTA-update question in miniature).
const BUILD_STAMP = '__BUILD_STAMP__';

$('mode').textContent =
  `contract ${BRIDGE_CONTRACT_VERSION} · build ${BUILD_STAMP} · ` +
  `origin ${location.protocol}//${location.host || 'assets'} · ` +
  `bridge ${bridge.available ? 'attached' : 'MISSING'}`;

$('btn-device').addEventListener('click', async () => {
  const t0 = performance.now();
  try {
    const s = await bridge.getDeviceState();
    out.textContent = `getDeviceState -> ${JSON.stringify(s, null, 2)}\n(${(performance.now() - t0).toFixed(1)} ms)`;
  } catch (e) {
    out.textContent = `error: ${(e as Error).message}`;
  }
});

$('btn-listen').addEventListener('click', async () => {
  try {
    const s = await bridge.startListening({ sampleRateHz: 16000, language: 'en' });
    out.textContent = `startListening -> ${JSON.stringify(s)}`;
  } catch (e) {
    out.textContent = `error: ${(e as Error).message}`;
  }
});

$('btn-bench').addEventListener('click', async () => {
  benchOut.textContent = 'running…';
  const N = 100;
  const samples: number[] = [];
  for (let i = 0; i < 10; i++) await bridge.getDeviceState(); // warm up
  // WKWebView clamps performance.now() to ~1ms, so per-call percentiles are
  // coarse; the wall-clock total over N calls is the trustworthy number.
  const wall0 = performance.now();
  for (let i = 0; i < N; i++) {
    const t0 = performance.now();
    await bridge.getDeviceState();
    samples.push(performance.now() - t0);
  }
  const wall = performance.now() - wall0;
  samples.sort((a, b) => a - b);
  const q = (p: number) => samples[Math.min(samples.length - 1, Math.floor(p * samples.length))];
  benchOut.textContent =
    `n=${N} round trips (ui->shell->ui)\n` +
    `p50 ${q(0.5).toFixed(2)} ms\np95 ${q(0.95).toFixed(2)} ms\n` +
    `min ${samples[0].toFixed(2)} ms · max ${samples[N - 1].toFixed(2)} ms\n` +
    `wall ${wall.toFixed(0)} ms total · mean ${(wall / N).toFixed(2)} ms/call`;
  console.log('BENCH', benchOut.textContent.replace(/\n/g, ' | '));
});

const transcript = $('transcript');
let cleared = false;
bridge.onTranscriptEvent((e: TranscriptEvent) => {
  if (!cleared) { transcript.innerHTML = ''; cleared = true; }
  const oneWay = Date.now() - e.shellSentAtMs;
  const div = document.createElement('div');
  div.className = 'seg' + (e.isFinal ? '' : ' partial');
  div.textContent = `${e.text}  (+${oneWay} ms shell→ui)`;
  transcript.appendChild(div);
  while (transcript.childElementCount > 8) transcript.removeChild(transcript.firstChild!);
  console.log(`PUSH v2 oneway_ms=${oneWay}`);
});

// Dev-mode live reload: poll the server's build stamp and reload on change.
// Only active when served over http (dev mode), never in the shipped asset build.
if (location.protocol.startsWith('http')) {
  let seen: string | null = null;
  setInterval(async () => {
    try {
      const s = await (await fetch('/stamp', { cache: 'no-store' })).text();
      if (seen === null) seen = s;
      else if (s !== seen) { console.log('LIVERELOAD'); location.reload(); }
    } catch { /* server down; keep the page */ }
  }, 500);
}


// One-shot probe: can the surface reach the network from its current origin?
// In asset (file://) mode WKWebView has an opaque origin, so cross-origin fetch
// is expected to fail -- which would force all network access through the bridge.
void (async () => {
  try {
    const r = await fetch('http://localhost:8787/stamp', { cache: 'no-store' });
    console.log(`NETPROBE ok status=${r.status} origin=${location.protocol}`);
  } catch (e) {
    console.log(`NETPROBE blocked origin=${location.protocol} err=${(e as Error).message}`);
  }
})();

const filler = $('filler');
for (let i = 0; i < 40; i++) {
  const d = document.createElement('div');
  d.className = 'filler';
  d.textContent = `scroll row ${i + 1}`;
  filler.appendChild(d);
}
