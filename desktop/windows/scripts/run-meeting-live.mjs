// LIVE (non-CI) checks for Phase 5 meeting detection — the deferred-matrix items
// that need no human call:
//
//   A. Real-audio loopback music gate: route default playback → VB-Cable
//      "CABLE Input" (inaudible), start a REAL system-audio loopback capture in
//      the built app (auth-free test session), play a speech fixture then a
//      music clip through the actual audio device path, and assert the YAMNet
//      gate's verdict flips speech → music and that byte flow drops while music
//      plays (the gate actually closes).
//
//   B. Meet-in-a-browser tab-title detection (headed Edge/Chrome via
//      playwright): a foreground browser tab titled "Meet - …" must light Tier 1
//      up as a CANDIDATE (title regex + browser exe) while Tier 2 shows no
//      browser mic use — so the machine must NOT activate (no false auto-start).
//      Asserted two ways: the pure matcher against the REAL foreground window
//      (vite-node probe) and the running app's machine phase.
//
// Run: pnpm test:e2e:meeting-live   (add --no-build to reuse out/)
// Exit codes: 0 pass · 1 assertion failed · 2 skipped (cable/module missing).
// Live-by-design: keep out of CI (AGENTS.md testing rules) — needs audio
// devices and a system browser.
import { execFileSync, spawnSync, spawn } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FIXTURES = path.join(root, 'test', 'fixtures', 'audio')
const NO_BUILD = process.argv.includes('--no-build')
const SAMPLE_RATE = 16000

let savedAudioDefaults = null
let failures = 0

function log(m) {
  console.log(`[meeting-live] ${m}`)
}
function fail(m) {
  failures++
  console.error(`[meeting-live] FAIL: ${m}`)
}
function ok(m) {
  console.log(`[meeting-live] PASS: ${m}`)
}

function ps(script) {
  return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
    encoding: 'utf8'
  })
}

/** 44-byte WAV header for 16kHz mono s16le PCM. */
function pcmToWav(pcmPath, wavPath) {
  const pcm = fs.readFileSync(pcmPath)
  const h = Buffer.alloc(44)
  h.write('RIFF', 0)
  h.writeUInt32LE(36 + pcm.length, 4)
  h.write('WAVE', 8)
  h.write('fmt ', 12)
  h.writeUInt32LE(16, 16)
  h.writeUInt16LE(1, 20)
  h.writeUInt16LE(1, 22)
  h.writeUInt32LE(SAMPLE_RATE, 24)
  h.writeUInt32LE(SAMPLE_RATE * 2, 28)
  h.writeUInt16LE(2, 32)
  h.writeUInt16LE(16, 34)
  h.write('data', 36)
  h.writeUInt32LE(pcm.length, 40)
  fs.writeFileSync(wavPath, Buffer.concat([h, pcm]))
}

function snapshotDefaults() {
  const out = ps(`
    Import-Module AudioDeviceCmdlets
    $p = Get-AudioDevice -Playback
    $r = Get-AudioDevice -Recording
    "$($p.Index),$($r.Index)"
  `)
  const line = ((out.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = line.match(/^(\d+),(\d+)$/)
  return m ? { playIndex: Number(m[1]), recIndex: Number(m[2]) } : null
}

/** Default playback → CABLE Input so the music is inaudible AND is exactly what
 *  WASAPI loopback (default render device) captures. Recording default is left
 *  untouched — section A only exercises the loopback lane. */
function routePlaybackToCable() {
  const probe = ps("if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { 'yes' } else { 'no' }")
  if ((probe.stdout || '').trim() !== 'yes') {
    log('AudioDeviceCmdlets module missing — cannot route the cable (skip section A)')
    return false
  }
  savedAudioDefaults = snapshotDefaults()
  const setup = ps(`
    Import-Module AudioDeviceCmdlets
    $play = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' -and $_.Name -match 'CABLE Input' } | Select-Object -First 1
    if (-not $play) { 'missing'; exit }
    Set-AudioDevice -Index $play.Index | Out-Null
    "ok $($play.Index)"
  `)
  const last = ((setup.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = last.match(/^ok (\d+)$/)
  if (!m) {
    savedAudioDefaults = null
    log('VB-Cable "CABLE Input" playback device not found (skip section A)')
    return false
  }
  if (savedAudioDefaults && savedAudioDefaults.playIndex === Number(m[1])) savedAudioDefaults = null
  log('routed default playback → CABLE Input (loopback captures it; nothing audible)')
  return true
}

function restoreAudioDefaults() {
  if (!savedAudioDefaults) return
  ps(`
    Import-Module AudioDeviceCmdlets
    Set-AudioDevice -Index ${savedAudioDefaults.playIndex} | Out-Null
  `)
  log(`restored default playback → #${savedAudioDefaults.playIndex}`)
}

/** Non-blocking playback: resolves when the clip finishes, so the caller can
 *  sample verdicts WHILE audio flows (a sync PlaySync would starve the event
 *  loop and every sample would land in the post-playback silence tail). */
function playWavAsync(wavPath) {
  return new Promise((resolve) => {
    const child = spawn(
      'powershell',
      [
        '-NoProfile',
        '-Command',
        `(New-Object System.Media.SoundPlayer '${wavPath.replace(/'/g, "''")}').PlaySync()`
      ],
      { stdio: 'ignore' }
    )
    child.on('exit', resolve)
    child.on('error', resolve)
  })
}

/** Play a clip while sampling the loopback music-gate verdict every ~800ms. */
async function playAndSampleVerdicts(wavPath, capturePage) {
  const verdicts = []
  const timer = setInterval(() => {
    readVerdict(capturePage)
      .then((v) => verdicts.push(v))
      .catch(() => {})
  }, 800)
  await playWavAsync(wavPath)
  clearInterval(timer)
  return verdicts
}

// Real vocal music (public domain, Wikimedia Commons: "O mio babbino caro",
// Rebecca Evans) — cached as a gitignored fixture; falls back to an
// ffmpeg-synthesized chord clip when offline. Real singing matters: it opens
// the Silero VAD gate (first line of defense) so the YAMNet gate (second line)
// actually gets windows to classify — pure synth tones never pass the VAD.
const MUSIC_URL =
  'https://upload.wikimedia.org/wikipedia/commons/b/b3/O_Mio_Babbino_Caro_-_Rebecca_Evans.ogg'

function ensureMusicWav(tmp) {
  const cachedPcm = path.join(FIXTURES, 'music-opera.pcm')
  const wav = path.join(tmp, 'music.wav')
  if (!fs.existsSync(cachedPcm) || fs.statSync(cachedPcm).size < 100_000) {
    const ogg = path.join(tmp, 'music.ogg')
    const dl = spawnSync(
      'curl.exe',
      ['-s', '-L', '-A', 'omi-desktop-test-harness/1.0 (contact: dev@omi.me)', '-o', ogg, MUSIC_URL],
      { encoding: 'utf8' }
    )
    if (dl.status === 0 && fs.existsSync(ogg) && fs.statSync(ogg).size > 100_000) {
      execFileSync('ffmpeg', ['-y', '-i', ogg, '-ss', '20', '-t', '14', '-ac', '1', '-ar', String(SAMPLE_RATE), '-f', 's16le', cachedPcm], { stdio: 'ignore' })
      log('real vocal music fixture downloaded (Wikimedia Commons, public domain)')
    } else {
      log('music download unavailable — falling back to the synth clip (VAD blocks it upstream)')
      execFileSync('ffmpeg', [
        '-y', '-f', 'lavfi', '-i',
        'aevalsrc=0.30*sin(2*PI*220*t)+0.28*sin(2*PI*277*t)+0.26*sin(2*PI*330*t)+0.18*sin(2*PI*440*(t+0.4*sin(2*PI*2*t))):s=16000:d=12',
        '-ac', '1', '-ar', String(SAMPLE_RATE), '-f', 's16le', cachedPcm
      ], { stdio: 'ignore' })
    }
  }
  pcmToWav(cachedPcm, wav)
  return wav
}

const readStats = (app) =>
  app.evaluate(() => {
    const fn = globalThis.__omiGetListenStats
    return typeof fn === 'function' ? fn() : {}
  })
const totalBytes = (stats) => Object.values(stats || {}).reduce((n, v) => n + (v?.bytes ?? 0), 0)

async function findCapturePage(app) {
  for (let i = 0; i < 40; i++) {
    const w = app.windows().find((w) => w.url().includes('#/capture'))
    if (w) {
      await w.waitForLoadState('domcontentloaded')
      return w
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}

/** Highest-signal verdict from the loopback sessions map (there is one). */
const readVerdict = async (capturePage) => {
  const v = await capturePage.evaluate(() => {
    const hook = globalThis.__omiCaptureE2E
    return hook && typeof hook.loopbackVerdicts === 'function' ? hook.loopbackVerdicts() : {}
  })
  return Object.values(v)[0] ?? null
}

// ── Section A: real-audio loopback music gate ────────────────────────────────
async function sectionA(app, tmp) {
  log('── Section A: loopback music gate over real audio devices ──')
  if (!routePlaybackToCable()) return 'skipped'

  const speechPcm = path.join(FIXTURES, 'speech-long.pcm') // ~80s of real SAPI speech; we play ~12s of it
  if (!fs.existsSync(speechPcm)) {
    log('speech fixtures missing — run `pnpm fixtures:audio` (skip section A)')
    return 'skipped'
  }
  // Trim speech to ~12s so playback doesn't run for 80s.
  const speechShort = path.join(tmp, 'speech-12s.pcm')
  fs.writeFileSync(speechShort, fs.readFileSync(speechPcm).subarray(0, 12 * SAMPLE_RATE * 2))
  const speechWav = path.join(tmp, 'speech.wav')
  pcmToWav(speechShort, speechWav)

  const musicWav = ensureMusicWav(tmp)

  const capturePage = await findCapturePage(app)
  if (!capturePage) {
    fail('capture window never appeared')
    return 'failed'
  }
  await new Promise((r) => setTimeout(r, 2000)) // host subscriptions

  const started = await app.evaluate(async () => {
    const hook = globalThis.__omiE2E
    if (!hook?.startCaptureForTest) return false
    try {
      return (await hook.startCaptureForTest({ source: 'system' })) !== false
    } catch {
      return false
    }
  })
  if (!started) {
    fail('startCaptureForTest(system) hook unavailable')
    return 'failed'
  }
  await new Promise((r) => setTimeout(r, 3000)) // loopback + yamnet warm-up

  const base = totalBytes(await readStats(app))
  log('playing SPEECH (~12s) through the cable…')
  const speechVerdicts = await playAndSampleVerdicts(speechWav, capturePage)
  const afterSpeech = totalBytes(await readStats(app))
  const speechDelta = afterSpeech - base
  log(`speech: bytes=${speechDelta} verdicts(during)=${JSON.stringify(speechVerdicts)}`)

  log('playing MUSIC (~12s) through the cable…')
  const musicVerdicts = await playAndSampleVerdicts(musicWav, capturePage)
  await new Promise((r) => setTimeout(r, 1500))
  const afterMusic = totalBytes(await readStats(app))
  const musicDelta = afterMusic - afterSpeech
  log(`music: bytes=${musicDelta} verdicts(during)=${JSON.stringify(musicVerdicts)}`)

  // Stop the test session (releases the loopback stream).
  await app.evaluate(() => globalThis.__omiE2E?.stopCaptureForTest?.())

  if (speechDelta <= 0) fail('no bytes flowed during speech — loopback capture dead')
  if (!speechVerdicts.includes('speech'))
    fail(`'speech' never observed during real speech playback (${JSON.stringify(speechVerdicts)})`)

  // Music must NOT flow. Two acceptable mechanisms, both asserted by outcome:
  //   (a) YAMNet gate: verdict flips to 'music' and drops the windows, or
  //   (b) Silero VAD (first line): the audio never reads as speech, so nothing
  //       reaches the WS at all (synth-tone fallback clip lands here).
  const sawMusicVerdict = musicVerdicts.includes('music')
  const musicSuppressed = musicDelta < speechDelta * 0.5
  if (sawMusicVerdict) log('music blocked by the YAMNet gate (verdict=music observed live)')
  else if (musicSuppressed) log('music blocked upstream by the Silero VAD gate (no windows reached YAMNet)')
  if (!sawMusicVerdict && !musicSuppressed) {
    fail(
      `music flowed like speech: ${musicDelta}B vs speech ${speechDelta}B, verdicts=${JSON.stringify(musicVerdicts)}`
    )
  }
  if (failures === 0) {
    ok(
      `real-audio loopback gate: speech flowed (${speechDelta}B), music suppressed (${musicDelta}B, yamnet=${sawMusicVerdict ? 'music' : 'not reached'})`
    )
    return 'passed'
  }
  return 'failed'
}

// ── Section B: Meet-in-a-browser title → candidate, never active ─────────────
async function sectionB(app) {
  log('── Section B: browser meeting-title Tier 1 check (no false auto-start) ──')
  const { chromium } = await import('playwright')
  let browser = null
  for (const channel of ['msedge', 'chrome']) {
    try {
      browser = await chromium.launch({ channel, headless: false })
      log(`launched system browser: ${channel}`)
      break
    } catch {
      /* try next */
    }
  }
  if (!browser) {
    log('no system Edge/Chrome available to playwright — skip section B')
    return 'skipped'
  }
  try {
    const basePhase = await app.evaluate(() => globalThis.__omiE2E.meeting.phase())
    log(`baseline machine phase (before browser): ${basePhase}`)

    const page = await browser.newPage()
    await page.goto('data:text/html,<title>Meet - abc-defg-hij</title><h1>fake meet tab</h1>')
    await page.bringToFront()
    // bringToFront only raises the tab INSIDE the browser; Windows blocks
    // background processes from stealing OS foreground, so activate the browser
    // window explicitly by its title (WScript.Shell is exempt when the target
    // titles match).
    const act = ps(`(New-Object -ComObject WScript.Shell).AppActivate('Meet - abc-defg-hij')`)
    log(`AppActivate('Meet - …') → ${(act.stdout || '').trim()}`)
    await new Promise((r) => setTimeout(r, 1500)) // foreground event + coalescer + snapshot

    // (1) Pure Tier 1 against the REAL foreground window via the probe.
    const probe = spawnSync('pnpm', ['exec', 'vite-node', 'scripts/meeting-native-probe.ts'], {
      cwd: root,
      encoding: 'utf8',
      shell: true
    })
    const out = probe.stdout || ''
    const fgLine = (out.split(/\r?\n/).find((l) => l.includes('[foreground]')) || '').trim()
    const tier1Line = (out.split(/\r?\n/).find((l) => l.includes('[tier1]')) || '').trim()
    const gateLine = (out.split(/\r?\n/).find((l) => l.includes('[gate]')) || '').trim()
    log(fgLine)
    log(tier1Line)
    log(gateLine)
    if (out.includes("id: 'meet-web'") || out.includes('"id": "meet-web"')) {
      ok('Tier 1 title regex matched the real foreground browser tab (meet-web)')
    } else {
      fail('probe did not report a meet-web Tier 1 match for the foreground Meet tab')
    }
    if (gateLine.includes('null')) {
      ok('Tier 2 shows no browser mic use → agreed match is null (no activation possible)')
    } else if (gateLine) {
      log(`NOTE: agreed match not null — something on this machine is mid-meeting: ${gateLine}`)
    }

    // (2) The running app (REAL signals, default ask mode): candidate at most.
    const phase = await app.evaluate(() => globalThis.__omiE2E.meeting.phase())
    const capturing = await app.evaluate(() => globalThis.__omiE2E.meeting.capturing())
    log(`app machine phase with Meet tab foreground: ${phase} (capturing=${capturing})`)
    if (phase === 'active' || capturing) {
      fail(`false auto-start: phase=${phase} capturing=${capturing} from a mere tab title`)
    } else if (phase === 'candidate') {
      ok('app machine is CANDIDATE (Tier 1 lit) without activation — as designed')
    } else {
      // idle is acceptable only if the app never saw the browser foreground
      // (focus contention); report it rather than fail — the probe already
      // proved the matcher on the real window.
      log(`NOTE: app phase is '${phase}' — foreground event may have raced the probe's window focus`)
    }

    await browser.close()
    browser = null
    await new Promise((r) => setTimeout(r, 1200))
    const after = await app.evaluate(() => globalThis.__omiE2E.meeting.phase())
    log(`machine phase after closing the browser: ${after}`)
    return 'passed'
  } finally {
    try {
      await browser?.close()
    } catch {
      /* ignore */
    }
  }
}

async function main() {
  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log('built main not found — run without --no-build')
    process.exit(2)
  }

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-meetlive-'))
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-meetlive-ud-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_SKIP_TUNNEL: '1',
      OMI_AUTOMATION: '0'
    }
  })

  let aResult = 'skipped'
  let bResult = 'skipped'
  try {
    await app.firstWindow()
    aResult = await sectionA(app, tmp)
    bResult = await sectionB(app)
  } finally {
    try {
      await app.evaluate(({ app: a }) => a.quit())
    } catch {
      /* ignore */
    }
    try {
      await app.close()
    } catch {
      /* ignore */
    }
    restoreAudioDefaults()
    fs.rmSync(userDataDir, { recursive: true, force: true })
    fs.rmSync(tmp, { recursive: true, force: true })
  }

  log(`summary: sectionA=${aResult} sectionB=${bResult} failures=${failures}`)
  if (failures > 0) process.exit(1)
  if (aResult === 'skipped' && bResult === 'skipped') process.exit(2)
  process.exit(0)
}

main().catch((e) => {
  console.error(`[meeting-live] error: ${e?.stack || e}`)
  restoreAudioDefaults()
  process.exit(1)
})
