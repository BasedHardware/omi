// Live amplitude-chain probe: real audio → real mic (VB-Cable) → real capture
// window → real bar orb, recording the [orb-amp] numeric trace (raw linear peak
// → mapped/enveloped display level → gate/ceiling trackers) plus a bar
// screenshot per segment. This is the live half of the amplitude-mapping fix's
// verification (the deterministic half is amplitudeMapper.test.ts).
//
// What it does:
//   1. Routes default playback→CABLE Input, capture→CABLE Output (restored after).
//   2. Launches the BUILT app (out/main/index.js) with OMI_E2E=1 and
//      OMI_ALLOW_VIRTUAL_MIC=1, throwaway --user-data-dir; seeds Firebase auth
//      from .env (OMI_E2E_REFRESH_TOKEN — same lane as the voice gauntlet).
//   3. Enables the bar orb's opt-in trace (localStorage omi.orbAmpDiag='1'),
//      shows the bar, and starts ONE long PTT hold via the __omiPtt E2E seam.
//   4. Plays SAPI speech fixtures into the cable at four gains (silence / quiet
//      -26dB / normal -10dB / loud 0dB) plus a quiet→loud sweep, screenshotting
//      the bar mid-clip.
//   5. Collects the [orb-amp] console lines per segment and prints level stats.
//   6. Closes the app WITHOUT ending the hold — the turn never finalizes, so no
//      transcription request and no chat message is ever created (zero backend
//      side effects; the mic-warm-up hold is silent and gate-discarded).
//
// Run: node scripts/amp-live-probe.mjs [--no-build]
// Outputs: .orb-out/amp-probe/{trace.json, <segment>.png} (gitignored).
import { execFileSync, spawnSync, spawn } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')
const outDir = path.join(root, '.orb-out', 'amp-probe')

const log = (m) => console.log(`[amp-probe] ${m}`)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── Audio routing (from agent-voice-gauntlet) ────────────────────────────────
function ps(script) {
  return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
    encoding: 'utf8',
    timeout: 60_000
  })
}
// Only the default CAPTURE device is switched (the app's getUserMedia reads the
// default mic). Playback goes DIRECTLY to the "CABLE Input" endpoint via python
// sounddevice — the user's default playback is untouched, and (crucially) any
// audio the machine happens to be playing does NOT leak into the probe mic.
// (The first probe run rerouted default playback and every segment — including
// "silence" — was contaminated by a constant ~-19dB system-audio bed.)
let savedAudioDefaults = null
function setupVirtualCable() {
  const current = ps(`
    Import-Module AudioDeviceCmdlets -ErrorAction Stop
    $r = Get-AudioDevice -Recording
    "$($r.Index)"
  `)
  const cm = ((current.stdout || '').trim().split(/\r?\n/).pop() || '').match(/^(\d+)$/)
  savedAudioDefaults = cm ? { recIndex: Number(cm[1]) } : null
  const setup = ps(`
    Import-Module AudioDeviceCmdlets -ErrorAction Stop
    $rec = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' -and $_.Name -match 'CABLE Output' } | Select-Object -First 1
    if (-not $rec) { 'missing'; exit }
    Set-AudioDevice -Index $rec.Index | Out-Null
    "ok $($rec.Index)"
  `)
  const last = ((setup.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = last.match(/^ok (\d+)$/)
  if (!m) {
    savedAudioDefaults = null
    log('SKIP: VB-Cable CABLE Output recording device not found')
    return false
  }
  if (savedAudioDefaults && savedAudioDefaults.recIndex === Number(m[1])) savedAudioDefaults = null
  log('routed default capture→CABLE Output (playback untouched)')
  return true
}
function restoreAudioDefaults() {
  if (!savedAudioDefaults) return
  ps(`
    Import-Module AudioDeviceCmdlets
    Set-AudioDevice -Index ${savedAudioDefaults.recIndex} | Out-Null
  `)
  log(`restored default capture (#${savedAudioDefaults.recIndex})`)
  savedAudioDefaults = null
}

// ── Fixtures: SAPI speech at several gains + a sweep ─────────────────────────
function sapiSpeakToWav(text, wavPath) {
  const ps1 = path.join(os.tmpdir(), `omi-amp-tts-${Date.now()}.ps1`)
  const script = [
    'Add-Type -AssemblyName System.Speech',
    '$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer',
    '$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(',
    '  16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,',
    '  [System.Speech.AudioFormat.AudioChannel]::Mono)',
    `$synth.SetOutputToWaveFile('${wavPath.replace(/'/g, "''")}', $fmt)`,
    '$synth.Rate = 0',
    `$synth.Speak('${text.replace(/'/g, "''")}')`,
    '$synth.Dispose()'
  ].join('\n')
  fs.writeFileSync(ps1, script, 'utf8')
  try {
    execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1], {
      stdio: 'pipe',
      timeout: 120_000
    })
  } finally {
    fs.rmSync(ps1, { force: true })
  }
}
function deriveWav(src, dst, filter) {
  execFileSync(
    'ffmpeg',
    ['-hide_banner', '-loglevel', 'error', '-i', src, '-af', filter, '-y', dst],
    {
      stdio: 'pipe',
      timeout: 60_000
    }
  )
}
/** Non-blocking playback straight to the "CABLE Input" render endpoint (python
 *  sounddevice) — never the default device, so user audio stays untouched and
 *  system audio can't bleed into the probe. */
function playWavAsync(wavPath) {
  const py = [
    'import sys, sounddevice as sd, soundfile as sf',
    "data, sr = sf.read(sys.argv[1], dtype='float32')",
    "dev = next(i for i, d in enumerate(sd.query_devices()) if 'CABLE Input' in d['name'] and d['max_output_channels'] > 0)",
    'sd.play(data, sr, device=dev)',
    'sd.wait()'
  ].join('\n')
  const child = spawn('python', ['-c', py, wavPath], { stdio: 'ignore' })
  return new Promise((resolve) => child.on('close', resolve))
}

// ── Playwright helpers (gauntlet pattern) ────────────────────────────────────
async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app
      .windows()
      .find(
        (w) =>
          !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(w.url()) &&
          w.url() !== 'about:blank'
      )
    if (page) return page
    await sleep(500)
  }
  return null
}
async function findBarWindow(app) {
  for (let i = 0; i < 60; i++) {
    const page = app.windows().find((w) => /#\/bar/.test(w.url()))
    if (page) return page
    await sleep(500)
  }
  return null
}
async function waitFor(page, fnBody, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const v = await page.evaluate(fnBody)
    if (v) return v
    if (Date.now() > deadline) throw new Error(`timeout waiting for ${label}`)
    await sleep(400)
  }
}
async function injectAuth(page, { apiKey, idToken, refreshToken }) {
  const claims = decodeJwt(idToken)
  if (!claims?.user_id) throw new Error('could not decode injected ID token')
  const user = {
    uid: claims.user_id,
    email: claims.email ?? null,
    emailVerified: !!claims.email_verified,
    displayName: claims.name ?? null,
    isAnonymous: false,
    photoURL: claims.picture ?? null,
    providerData: [],
    stsTokenManager: { refreshToken, accessToken: idToken, expirationTime: claims.exp * 1000 },
    createdAt: String(Date.now()),
    lastLoginAt: String(Date.now()),
    apiKey,
    appName: '[DEFAULT]'
  }
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), {
    key: `firebase:authUser:${apiKey}:[DEFAULT]`,
    value: user
  })
}

const q = (xs, p) => {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s[Math.min(s.length - 1, Math.floor(p * s.length))]
}

async function main() {
  const env = readDotEnv(path.join(root, '.env'))
  const refreshToken = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const apiKey = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!refreshToken || !apiKey) {
    log('SKIP: OMI_E2E_REFRESH_TOKEN / VITE_FIREBASE_API_KEY missing from .env')
    process.exit(2)
  }
  if (spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' }).status !== 0) {
    log('SKIP: ffmpeg not on PATH')
    process.exit(2)
  }
  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log('SKIP: built main not found — run without --no-build')
    process.exit(2)
  }
  if (!setupVirtualCable()) process.exit(2)

  let idToken
  try {
    idToken = await exchangeRefreshToken(refreshToken, apiKey)
  } catch (e) {
    log(`SKIP: refresh-token exchange failed (${e.message})`)
    restoreAudioDefaults()
    process.exit(2)
  }

  fs.mkdirSync(outDir, { recursive: true })
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-amp-probe-'))
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-amp-probe-ud-'))

  // Fixtures. The base SAPI clip peaks near full scale; ffmpeg volume shifts
  // derive the level tiers. The sweep ramps -30dB→0dB across the clip.
  log('generating fixtures…')
  const base = path.join(tmp, 'base.wav')
  sapiSpeakToWav(
    'Omi test fixture. The quick brown fox jumps over the lazy dog while we watch the wave form follow this voice.',
    base
  )
  const wavs = {
    quiet: path.join(tmp, 'quiet.wav'),
    normal: path.join(tmp, 'normal.wav'),
    loud: path.join(tmp, 'loud.wav'),
    sweep: path.join(tmp, 'sweep.wav')
  }
  deriveWav(base, wavs.quiet, 'volume=-26dB')
  deriveWav(base, wavs.normal, 'volume=-10dB')
  deriveWav(base, wavs.loud, 'volume=0dB')
  deriveWav(base, wavs.sweep, "volume='pow(10,(-30+30*t/7)/20)':eval=frame")

  let app = null
  let exitCode = 0
  try {
    app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: { ...process.env, OMI_E2E: '1', OMI_ALLOW_VIRTUAL_MIC: '1', OMI_AUTOMATION: '0' }
    })
    let page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await injectAuth(page, { apiKey, idToken, refreshToken })
    await page.evaluate(() => {
      const KEY = 'omi-windows-prefs-v1'
      const prefs = JSON.parse(localStorage.getItem(KEY) ?? '{}')
      prefs.onboardingCompletedAt = prefs.onboardingCompletedAt ?? Date.now()
      // Force the LOCAL PTT route: a hub-owned turn's lifecycle can terminate on
      // sustained silence (ending the trace mid-probe), while a local hold is
      // user-bounded — and the local route exercises the capture window's new
      // time-domain-peak orbLevel lane end-to-end. The hub route ships the same
      // canonical unit (pcmPeakLevel), covered by amplitudeMapper unit tests.
      prefs.pttHubEnabled = false
      localStorage.setItem(KEY, JSON.stringify(prefs))
      location.reload()
    })
    await sleep(3000)
    page = await findMainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    log('main window signed in')

    // Bar window: enable, arm the [orb-amp] trace, reload so the orb animator
    // (which reads the flag at construction) picks it up, show the bar.
    await app.evaluate(() => {
      const h = globalThis.__omiE2E
      if (h?.barEnable) h.barEnable()
    })
    let barPage = await findBarWindow(app)
    if (!barPage) throw new Error('bar window never appeared')
    await barPage.waitForLoadState('domcontentloaded')
    await barPage.evaluate(() => {
      localStorage.setItem('omi.orbAmpDiag', '1')
      location.reload()
    })
    await sleep(2000)
    barPage = await findBarWindow(app)
    await barPage.waitForLoadState('domcontentloaded')
    await waitFor(
      barPage,
      () => typeof globalThis.__omiPtt?.beginHold === 'function',
      30_000,
      '__omiPtt'
    )
    await app.evaluate(() => globalThis.__omiE2E.barShow('ptt'))
    log('bar ready ([orb-amp] armed)')

    // Collect the trace with wall-clock timestamps for segment bucketing.
    const trace = []
    barPage.on('console', (msg) => {
      const t = msg.text()
      if (t.startsWith('[orb-amp]')) trace.push({ at: Date.now(), line: t })
    })
    // Surface capture-window [audio] diagnostics (e.g. the orb tap falling back).
    for (const w of app.windows()) {
      if (/#\/capture/.test(w.url())) {
        w.on('console', (msg) => {
          if (msg.text().includes('[audio]')) log(`capture: ${msg.text()}`)
        })
      }
    }

    // Warm-up hold (silent, gate-discarded — no backend call).
    await barPage.evaluate(() => globalThis.__omiPtt.beginHold())
    await sleep(1200)
    await barPage.evaluate(() => globalThis.__omiPtt.endHold())
    await sleep(1500)
    log('mic warm-up done')

    // ONE long hold across all segments (never ended → no transcription).
    await barPage.evaluate(() => globalThis.__omiPtt.beginHold())
    await sleep(700) // hold threshold + capture spin-up

    const segments = []
    const runSegment = async (name, wav, ms) => {
      const start = Date.now()
      log(`segment ${name}…`)
      const done = wav ? playWavAsync(wav) : sleep(ms)
      // Several shots per segment — speech has inter-phrase pauses, so any single
      // frame can catch resting dots; a spread makes the tall-bar frames certain.
      for (const [i, at] of [0.18, 0.4, 0.62].entries()) {
        const target = start + Math.floor(ms * at)
        const wait = target - Date.now()
        if (wait > 0) await sleep(wait)
        try {
          await barPage.screenshot({ path: path.join(outDir, `${name}-${i + 1}.png`) })
        } catch (e) {
          log(`screenshot ${name}-${i + 1} failed: ${e.message}`)
        }
      }
      await done
      segments.push({ name, start, end: Date.now() })
      await sleep(400)
    }

    await runSegment('silence', null, 3000)
    await runSegment('quiet-26dB', wavs.quiet, 8000)
    await runSegment('normal-10dB', wavs.normal, 8000)
    await runSegment('loud-0dB', wavs.loud, 8000)
    await runSegment('sweep', wavs.sweep, 8000)
    await sleep(500)

    // Bucket the trace per segment and report.
    const parse = (line) => {
      const m = line.match(/raw=([\d.]+) env=([\d.]+) gate=(-?[\d.]+)dB ceil=(-?[\d.]+)dB/)
      return m
        ? { raw: Number(m[1]), env: Number(m[2]), gate: Number(m[3]), ceil: Number(m[4]) }
        : null
    }
    log('──────── results ────────')
    const results = {}
    for (const s of segments) {
      const rows = trace
        .filter((e) => e.at >= s.start && e.at <= s.end)
        .map((e) => parse(e.line))
        .filter(Boolean)
      const envs = rows.map((r) => r.env)
      const raws = rows.map((r) => r.raw)
      results[s.name] = {
        samples: rows.length,
        rawP50: q(raws, 0.5),
        rawMax: q(raws, 1),
        envP50: q(envs, 0.5),
        envP95: q(envs, 0.95),
        envMax: q(envs, 1),
        gate: rows.at(-1)?.gate,
        ceil: rows.at(-1)?.ceil
      }
      const r = results[s.name]
      log(
        `${s.name.padEnd(12)} n=${String(r.samples).padStart(3)} raw p50=${r.rawP50.toFixed(4)} ` +
          `env p50=${r.envP50.toFixed(3)} p95=${r.envP95.toFixed(3)} max=${r.envMax.toFixed(3)} ` +
          `gate=${r.gate}dB ceil=${r.ceil}dB`
      )
    }
    fs.writeFileSync(
      path.join(outDir, 'trace.json'),
      JSON.stringify({ segments, trace, results }, null, 2)
    )
    log(`trace + screenshots → ${outDir}`)

    // Acceptance checks (numeric feel spec).
    const ck = (name, ok, detail) => {
      log(`${ok ? 'PASS' : 'FAIL'} ${name} — ${detail}`)
      if (!ok) exitCode = 1
    }
    const sil = results['silence']
    const qt = results['quiet-26dB']
    const nm = results['normal-10dB']
    const ld = results['loud-0dB']
    ck('silence rests', sil.envMax <= 0.05, `envMax=${sil.envMax.toFixed(3)}`)
    ck(
      'quiet visible, below max',
      qt.envP50 > 0.08 && qt.envP95 < 0.75,
      `p50=${qt.envP50.toFixed(3)} p95=${qt.envP95.toFixed(3)}`
    )
    ck(
      'normal mid-to-high with dynamics',
      nm.envP50 > qt.envP50 + 0.1 && nm.envP95 <= 0.92,
      `p50=${nm.envP50.toFixed(3)} p95=${nm.envP95.toFixed(3)}`
    )
    ck(
      'loud near max, never pinned',
      ld.envP95 > nm.envP50 && ld.envMax <= 0.92 + 1e-6,
      `p95=${ld.envP95.toFixed(3)} max=${ld.envMax.toFixed(3)}`
    )
    ck(
      'trace flowing (capture live)',
      sil.samples + qt.samples + nm.samples > 100,
      `total=${trace.length}`
    )
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`)
    exitCode = 1
  } finally {
    // Close WITHOUT ending the hold: the turn never finalizes → no POST.
    try {
      if (app) await app.close()
    } catch {
      /* already closed */
    }
    restoreAudioDefaults()
    try {
      fs.rmSync(tmp, { recursive: true, force: true })
      fs.rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best effort */
    }
    process.exit(exitCode)
  }
}

main()
