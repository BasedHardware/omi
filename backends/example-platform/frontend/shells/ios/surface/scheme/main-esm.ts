// Custom-scheme (candidate B) probe suite. Same shape and rigor as the
// loopback suite (surface/loop/main-esm.ts): runs top-to-bottom with top-level
// await and prints one PROBE line per fact. The shell scrapes these lines from
// the console relay and appends them to Documents/probe-log.txt.
import { tag, log } from './util-esm.js';
import { bridge, BRIDGE_CONTRACT_VERSION, type TranscriptEvent } from './bridge.g.js';

const j = (v: unknown) => { try { return JSON.stringify(v); } catch { return String(v); } };

// Exposed for the shell's post-resume probe (bridge RTT after suspension).
(window as unknown as Record<string, unknown>).__probeBridge = bridge;

log(`esm-static ok (${tag})`, 'ok');

try {
  const dyn = await import('./dyn-esm.js');
  log(`esm-dynamic ok (${dyn.dynTag})`, 'ok');
} catch (e) { log(`esm-dynamic FAIL ${e}`, 'fail'); }

log(`origin ${location.origin} href=${location.href} secureContext=${window.isSecureContext}`);

// --- bundle identity (manifest fetch doubles as a same-origin JSON probe) ----
try {
  const m = await (await fetch('./manifest.json', { cache: 'no-store' })).json();
  document.getElementById('bundle-tag')!.textContent =
    `bundle: ${m.bundleId} (contract ${m.bridgeContractVersion})`;
  log(`manifest bundleId=${m.bundleId} bridgeContractVersion=${m.bridgeContractVersion}`, 'ok');
} catch (e) { log(`manifest FAIL ${e}`, 'fail'); }

// --- subresources: css applied? svg img loaded? ------------------------------
{
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  log(accent ? `css subresource applied, accent=${accent}` : 'css subresource FAIL (no --accent)',
      accent ? 'ok' : 'fail');
  const img = document.getElementById('probe-img') as HTMLImageElement;
  await new Promise((r) => (img.complete ? r(0) : (img.onload = img.onerror = r)));
  log(`svg subresource ${img.naturalWidth > 0 ? `ok ${img.naturalWidth}x${img.naturalHeight}` : 'FAIL'}`,
      img.naturalWidth > 0 ? 'ok' : 'fail');
}

// --- storage scoping/persistence --------------------------------------------
try {
  const n = Number(localStorage.getItem('bootCount') ?? '0') + 1;
  localStorage.setItem('bootCount', String(n));
  log(`localStorage bootCount=${n} (origin ${location.origin})`, 'ok');
} catch (e) { log(`localStorage FAIL ${e}`, 'fail'); }

try {
  const db = await new Promise<IDBDatabase>((res, rej) => {
    const r = indexedDB.open('probe', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('kv');
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
  const count = await new Promise<number>((res, rej) => {
    const tx = db.transaction('kv', 'readwrite');
    const st = tx.objectStore('kv');
    st.put(Date.now(), `boot-${Date.now()}`);
    const c = st.count();
    c.onsuccess = () => res(c.result);
    tx.onerror = () => rej(tx.error);
  });
  log(`indexedDB ok, rows=${count}`, 'ok');
} catch (e) { log(`indexedDB FAIL ${e}`, 'fail'); }

// --- cookies (research says: no cookie machinery on handler schemes) ---------
try {
  document.cookie = 'probe=1; Path=/';
  log(`document.cookie after JS set: "${document.cookie}"`);
} catch (e) { log(`document.cookie FAIL ${e}`, 'fail'); }

// --- bridge push path started early so pushes land before all-done -----------
if (bridge.available) {
  bridge.onTranscriptEvent((ev: TranscriptEvent) => {
    const oneWay = Date.now() - ev.shellSentAtMs;
    console.log(`PROBE push oneway_ms=${oneWay} final=${ev.isFinal} "${ev.text}"`);
  });
  try {
    const s = await bridge.startListening({ sampleRateHz: 16000, language: 'en' });
    log(`bridge startListening ok session=${s.sessionId}`, 'ok');
  } catch (e) { log(`bridge startListening FAIL ${e}`, 'fail'); }
} else {
  log('bridge NOT available alongside scheme handler', 'fail');
}

// --- same-origin fetch to the custom scheme ---------------------------------
// /probe/echo is answered natively by the scheme handler with a JSON dump of
// the request it saw — this captures which headers (Origin? Cookie?) actually
// arrive at the handler.
try {
  const r = await fetch('/probe/echo', { headers: { 'x-probe': 'hi' } });
  log(`fetch same-scheme GET ${r.status} ${j(await r.json())}`, 'ok');
} catch (e) { log(`fetch same-scheme GET FAIL ${e}`, 'fail'); }

// POST with a body — research says interception loses request bodies.
try {
  const r = await fetch('/probe/echo', { method: 'POST', body: 'post-body-42',
    headers: { 'content-type': 'text/plain' } });
  log(`fetch same-scheme POST ${r.status} ${j(await r.json())}`, 'ok');
} catch (e) { log(`fetch same-scheme POST FAIL ${e}`, 'fail'); }

// --- external https, CORS posture (echo service reflects our Origin header) --
try {
  const r = await fetch('https://postman-echo.com/get?probe=1', { signal: AbortSignal.timeout(8000) });
  const body = await r.json();
  log(`fetch external-https-cors ${r.status} origin-header-sent=${j(body.headers?.origin ?? '(none)')}`, 'ok');
} catch (e) { log(`fetch external-https-cors FAIL ${e}`, 'fail'); }
try {
  const r = await fetch('https://httpbingo.org/headers', { signal: AbortSignal.timeout(8000) });
  const body = await r.json();
  log(`fetch external-https-cors2(httpbingo) ${r.status} origin=${j(body.headers?.Origin ?? '(none)')}`, 'ok');
} catch (e) { log(`fetch external-https-cors2(httpbingo) FAIL ${e}`, 'fail'); }
try {
  const r = await fetch('https://api.github.com/zen', { signal: AbortSignal.timeout(8000) });
  log(`fetch external-https-cors3(github) ${r.status} "${(await r.text()).slice(0, 40)}"`, 'ok');
} catch (e) { log(`fetch external-https-cors3(github) FAIL ${e}`, 'fail'); }
try {
  const r = await fetch('https://www.apple.com/library/test/success.html', { mode: 'no-cors', signal: AbortSignal.timeout(8000) });
  log(`fetch external-https-nocors ok type=${r.type}`, 'ok');
} catch (e) { log(`fetch external-https-nocors FAIL ${e}`, 'fail'); }

// --- external cleartext http (is a custom-scheme page inside or outside ATS?)
try {
  const r = await fetch('http://neverssl.com/', { mode: 'no-cors', signal: AbortSignal.timeout(8000) });
  log(`fetch external-http OK type=${r.type} — ATS does NOT apply here`, 'ok');
} catch (e) { log(`fetch external-http blocked (${e}) — ATS holds`, 'ok'); }

// --- service worker ----------------------------------------------------------
log(`serviceWorker API ${'serviceWorker' in navigator ? 'PRESENT' : 'absent'}`);

// --- bridge round-trip bench (does the scheme handler perturb the bridge?) ---
if (bridge.available) {
  try {
    const N = 100;
    for (let i = 0; i < 10; i++) await bridge.getDeviceState(); // warm up
    const wall0 = performance.now();
    for (let i = 0; i < N; i++) await bridge.getDeviceState();
    const wall = performance.now() - wall0;
    log(`bridge bench n=${N} wall=${wall.toFixed(0)}ms mean=${(wall / N).toFixed(2)}ms/call`, 'ok');
  } catch (e) { log(`bridge bench FAIL ${e}`, 'fail'); }
}

log('all-done');
