// LIVE echo-loop verification for Phase 6 realtime voice — the post-soak
// deliverable. DO NOT run while anything else owns the audio devices (it plays
// audio and temporarily changes the default playback/recording devices).
//
// Topology (worst-case echo on purpose — VB-Cable loops the app's own voice
// straight back into its microphone):
//
//   app voice output → default playback (CABLE Input) ─┐
//                                                      ├─ virtual cable ─┐
//   app mic (continuous + realtime) ← default capture (CABLE Output) ────┘
//
// Checks (each reported PASS/FAIL, overall exit 1 if any FAIL):
//   1. ECHO GATE — Omi speaks a marker phrase over the realtime session; the
//      marker words must appear ONLY as injected 'Omi' lines in the continuous
//      live transcript, NEVER as transcribed (non-Omi) speech.
//   2. BARGE-IN — while Omi speaks a long passage, "user speech" (a fixture WAV)
//      plays into the cable; Omi must stop speaking (speaking-end well before
//      the passage could have finished).
//   3. DEVICE SWITCH — setOutputDevice to another output mid-conversation; the
//      session must stay live.
//   4. TTS GATED PATH — a TTS reply plays through the same gate; its words must
//      not leak into the transcription feed either.
//   Plus an AEC-convergence NOTE: whether anything leaked in the first 10s.
//
// Auth: unattended via the .env refresh-token pattern (OMI_E2E_REFRESH_TOKEN +
// VITE_FIREBASE_API_KEY) — the token is exchanged for a fresh ID token and a
// persisted Firebase session is injected into the app's IndexedDB, then the
// windows reload signed-in.
//
// Exit codes: 0 all checks pass · 1 a check failed · 2 preconditions missing
// (VB-Cable/AudioDeviceCmdlets absent, no refresh token, build missing).
import { execFileSync, spawnSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FIXTURES = path.join(root, 'test', 'fixtures', 'audio')
const SAMPLE_RATE = 16000
const NO_BUILD = process.argv.includes('--no-build')
const PROVIDER = process.argv.includes('--gemini') ? 'gemini' : 'openai'
// --auth-only: verify ONLY the unattended sign-in path (refresh-token exchange +
// injected Firebase session). Touches no audio device, opens no mic, plays no
// sound — safe to run while a soak owns the audio environment.
const AUTH_ONLY = process.argv.includes('--auth-only')

// Distinctive marker tokens Omi is asked to speak — if ANY appears in a
// non-Omi transcript line, the echo gate leaked.
const MARKER_WORDS = ['clockwork', 'zeppelin', 'marmalade']
const MARKER_PHRASE = MARKER_WORDS.join(' ')

function log(m) {
  console.log(`[voice-loop] ${m}`)
}
const results = []
function check(name, pass, detail) {
  results.push({ name, pass, detail })
  log(`${pass ? 'PASS' : 'FAIL'}: ${name}${detail ? ` — ${detail}` : ''}`)
}
function note(name, detail) {
  log(`NOTE: ${name} — ${detail}`)
}

// ── Audio-device routing (same pattern as run-vad-playback.mjs) ───────────────
let savedAudioDefaults = null

function ps(script) {
  return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
    encoding: 'utf8'
  })
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

function setupVirtualCable() {
  const probe = ps("if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { 'yes' } else { 'no' }")
  if ((probe.stdout || '').trim() !== 'yes') {
    log('AudioDeviceCmdlets PowerShell module not found — cannot auto-route the cable.')
    return false
  }
  savedAudioDefaults = snapshotDefaults()
  const setup = ps(`
    Import-Module AudioDeviceCmdlets
    $play = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' -and $_.Name -match 'CABLE Input' } | Select-Object -First 1
    $rec  = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' -and $_.Name -match 'CABLE Output' } | Select-Object -First 1
    if (-not $play -or -not $rec) { 'missing'; exit }
    Set-AudioDevice -Index $play.Index | Out-Null
    Set-AudioDevice -Index $rec.Index  | Out-Null
    "ok $($play.Index) $($rec.Index)"
  `)
  const last = ((setup.stdout || '').trim().split(/\r?\n/).pop() || '').trim()
  const m = last.match(/^ok (\d+) (\d+)$/)
  if (!m) {
    savedAudioDefaults = null
    log('VB-Audio Virtual Cable devices not found (CABLE Input / CABLE Output).')
    return false
  }
  const target = { playIndex: Number(m[1]), recIndex: Number(m[2]) }
  if (
    savedAudioDefaults &&
    savedAudioDefaults.playIndex === target.playIndex &&
    savedAudioDefaults.recIndex === target.recIndex
  ) {
    savedAudioDefaults = null
  }
  log('routed default playback→CABLE Input, default capture→CABLE Output')
  return true
}

function restoreAudioDefaults() {
  if (!savedAudioDefaults) return
  const { playIndex, recIndex } = savedAudioDefaults
  ps(`
    Import-Module AudioDeviceCmdlets
    Set-AudioDevice -Index ${playIndex} | Out-Null
    Set-AudioDevice -Index ${recIndex}  | Out-Null
  `)
  log(`restored default playback→#${playIndex}, capture→#${recIndex}`)
}

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

function playWav(wavPath) {
  ps(`(New-Object System.Media.SoundPlayer '${wavPath.replace(/'/g, "''")}').PlaySync()`)
}

// ── App helpers ───────────────────────────────────────────────────────────────

async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app
      .windows()
      .find((w) => !/#\/(capture|overlay|insight-toast)/.test(w.url()) && w.url() !== 'about:blank')
    if (page) return page
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}

async function waitFor(page, fnBody, timeoutMs, label, arg) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const v = await page.evaluate(fnBody, arg)
    if (v) return v
    if (Date.now() > deadline) throw new Error(`timeout waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 500))
  }
}

/** Inject a persisted Firebase web session so the app boots signed-in — the
 *  unattended refresh-token auth pattern. The app initializes auth with
 *  browserLocalPersistence (lib/firebase.ts), so the session record lives in
 *  localStorage under firebase:authUser:<apiKey>:[DEFAULT]. */
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
    stsTokenManager: {
      refreshToken,
      accessToken: idToken,
      expirationTime: claims.exp * 1000
    },
    createdAt: String(Date.now()),
    lastLoginAt: String(Date.now()),
    apiKey,
    appName: '[DEFAULT]'
  }
  await page.evaluate(
    ({ key, value }) => {
      localStorage.setItem(key, JSON.stringify(value))
    },
    { key: `firebase:authUser:${apiKey}:[DEFAULT]`, value: user }
  )
}

const timestamp = () => new Date().toISOString().slice(11, 19)

async function main() {
  // ── Preconditions ─────────────────────────────────────────────────────────
  const env = readDotEnv(path.join(root, '.env'))
  const refreshToken = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const apiKey = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!refreshToken || !apiKey) {
    log('SKIP: OMI_E2E_REFRESH_TOKEN / VITE_FIREBASE_API_KEY missing from .env')
    process.exit(2)
  }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-voiceloop-'))
  const speechWav = path.join(tmp, 'speech.wav')
  if (!AUTH_ONLY) {
    execFileSync('node', [path.join(root, 'scripts', 'gen-audio-fixtures.mjs')], {
      stdio: 'inherit',
      cwd: root
    })
    const speechPcm = path.join(FIXTURES, 'speech-hello.pcm')
    if (!fs.existsSync(speechPcm)) {
      log(`SKIP: fixture missing: ${speechPcm}`)
      process.exit(2)
    }
    if (!setupVirtualCable()) process.exit(2)
    pcmToWav(speechPcm, speechWav)
  }

  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`SKIP: built main not found (${mainEntry}) — run without --no-build`)
    restoreAudioDefaults()
    process.exit(2)
  }

  let idToken
  try {
    idToken = await exchangeRefreshToken(refreshToken, apiKey)
  } catch (e) {
    log(`SKIP: refresh-token exchange failed (${e.message})`)
    restoreAudioDefaults()
    process.exit(2)
  }
  log(`auth ok (uid ${decodeJwt(idToken)?.user_id})`)

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-voiceloop-ud-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_ALLOW_VIRTUAL_MIC: '1',
      OMI_AUTOMATION: '0'
    }
  })

  let exitCode = 0
  try {
    let page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')

    // ── Sign in (inject persisted session, then reload every window) ────────
    await injectAuth(page, { apiKey, idToken, refreshToken })
    // Mark onboarding complete + continuous recording ON before reload so the
    // authed shell boots straight into the always-on lane.
    await page.evaluate((continuous) => {
      const KEY = 'omi-windows-prefs-v1'
      const prefs = JSON.parse(localStorage.getItem(KEY) ?? '{}')
      prefs.onboardingCompletedAt = prefs.onboardingCompletedAt ?? Date.now()
      // Auth-only mode leaves continuousRecording OFF so no mic ever opens.
      if (continuous) prefs.continuousRecording = true
      localStorage.setItem(KEY, JSON.stringify(prefs))
      location.reload()
    }, !AUTH_ONLY)
    await new Promise((r) => setTimeout(r, 3000))
    page = await findMainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    await waitFor(
      page,
      () => typeof globalThis.__omiVoice?.getAuthUid === 'function',
      30_000,
      'e2e hook'
    )
    const uid = await waitFor(page, () => globalThis.__omiVoice.getAuthUid(), 30_000, 'signed-in uid')
    log(`app signed in as ${uid}`)
    if (AUTH_ONLY) {
      check('unattended sign-in (refresh token → injected session)', true, `uid=${uid}`)
      return
    }

    // ── Continuous transcription live (the lane the gate must protect) ──────
    await waitFor(
      page,
      () => {
        const t = globalThis.__omiVoice.getLiveTranscript()
        return t.status === 'live' || t.status === 'connecting' ? t.status === 'live' : false
      },
      60_000,
      'continuous transcription live'
    )
    log('continuous transcription is live')

    // Helper: transcript lines split into injected-Omi vs transcribed speech.
    // Ids are kept so later checks can diff by IDENTITY (a store clear/save
    // between reads shifts array offsets — count-based slicing would lie).
    const readTranscript = () =>
      page.evaluate(() => {
        const t = globalThis.__omiVoice.getLiveTranscript()
        return t.segments.map((s, i) => ({
          id: s.id ?? `noid-${i}-${s.text.slice(0, 20)}`,
          speaker: s.speaker ?? '',
          text: s.text,
          injected: (s.id ?? '').startsWith('omi-voice-')
        }))
      })
    const leakedLines = (segments) =>
      segments.filter(
        (s) => !s.injected && MARKER_WORDS.some((w) => s.text.toLowerCase().includes(w))
      )

    // ── Start the realtime session ───────────────────────────────────────────
    log(`starting realtime session (${PROVIDER})…`)
    await page.evaluate((p) => void globalThis.__omiVoice.start(p), PROVIDER)
    const state = await waitFor(
      page,
      () => {
        const s = globalThis.__omiVoice.getState()
        return s.status === 'live' || s.status === 'error' ? s : false
      },
      45_000,
      'voice session live/error'
    )
    if (state.status !== 'live') {
      check('realtime session connects', false, state.message)
      exitCode = 1
      return
    }
    check('realtime session connects', true, `provider=${state.provider}`)
    const sessionStartAt = Date.now()

    // ── CHECK 1: echo gate holds while Omi speaks the marker ─────────────────
    log(`[${timestamp()}] asking Omi to speak the marker phrase…`)
    // Timestamp baseline (NOT an index into the capped event ring — indices
    // shift once the ring rolls past 200 entries).
    const markerMark = Date.now()
    await page.evaluate(
      (phrase) =>
        globalThis.__omiVoice.say(
          `Please say exactly this phrase out loud, then stop: "${phrase}". Say nothing else.`
        ),
      MARKER_PHRASE
    )
    // Wait for Omi to finish speaking (a speaking-start AFTER our ask, then a
    // speaking-end after that start).
    try {
      await waitFor(
        page,
        (mark) => {
          const ev = globalThis.__omiVoice.getEvents().filter((e) => e.at >= mark)
          const started = ev.findIndex((e) => e.type === 'speaking-start')
          return started >= 0 && ev.slice(started).some((e) => e.type === 'speaking-end')
        },
        45_000,
        'Omi spoke (speaking-start → speaking-end)',
        markerMark
      )
    } catch (e) {
      check('echo gate: Omi audibly spoke', false, e.message)
      exitCode = 1
      return
    }
    // Give the continuous lane time to transcribe any leak, then read.
    await new Promise((r) => setTimeout(r, 12_000))
    let segments = await readTranscript()
    const leaks = leakedLines(segments)
    const injectedHasMarker = segments.some(
      (s) => s.injected && MARKER_WORDS.some((w) => s.text.toLowerCase().includes(w))
    )
    check(
      'echo gate: marker words NOT transcribed from the speaker loop',
      leaks.length === 0,
      leaks.length ? `leaked: ${JSON.stringify(leaks.slice(0, 3))}` : undefined
    )
    if (leaks.length) exitCode = 1
    note(
      'injected record',
      injectedHasMarker
        ? 'marker present as injected Omi line (source text) — record intact'
        : 'marker NOT found in injected lines (model may have paraphrased — check events)'
    )
    // AEC-convergence note: any leak whose transcription landed in the first 10s.
    const events = await page.evaluate(() => globalThis.__omiVoice.getEvents())
    const firstSpeak = events.find((e) => e.type === 'speaking-start')
    note(
      'AEC first-10s convergence',
      firstSpeak && leaks.length === 0
        ? `no leak from session start (+${Math.round((firstSpeak.at - sessionStartAt) / 1000)}s to first speech)`
        : leaks.length
          ? 'leak occurred — inspect timing above'
          : 'no speech observed in window'
    )

    // ── CHECK 2: barge-in — user speech interrupts Omi mid-passage ──────────
    log(`[${timestamp()}] barge-in: asking Omi for a long passage, then interrupting…`)
    const bargeMark = Date.now()
    await page.evaluate(() =>
      globalThis.__omiVoice.say(
        'Please count slowly and steadily out loud from one to sixty, one number at a time. Do not stop until you reach sixty.'
      )
    )
    try {
      await waitFor(
        page,
        (mark) =>
          globalThis.__omiVoice
            .getEvents()
            .some((e) => e.at >= mark && e.type === 'speaking-start'),
        30_000,
        'long passage started',
        bargeMark
      )
    } catch {
      check('barge-in: long passage started', false, 'Omi never started speaking')
      exitCode = 1
      return
    }
    // Let it get going, then play "user speech" into the cable (mixes with
    // Omi's own output on the same playback device — true talk-over).
    await new Promise((r) => setTimeout(r, 2500))
    const playStartAt = Date.now()
    playWav(speechWav) // blocks ~2s while the user speech plays
    // The stop must CORRELATE with the interruption: a speaking-end shortly
    // AFTER the user speech started (not merely "sometime during the passage" —
    // a model that ignored the counting instruction would otherwise pass).
    let endEvent = null
    try {
      await waitFor(
        page,
        (t) =>
          globalThis.__omiVoice
            .getEvents()
            .some((e) => e.type === 'speaking-end' && e.at >= t - 500),
        15_000,
        'barge-in speaking-end',
        playStartAt
      )
      const ev = await page.evaluate(() => globalThis.__omiVoice.getEvents())
      endEvent = ev.find((e) => e.type === 'speaking-end' && e.at >= playStartAt - 500) ?? null
    } catch {
      /* handled below */
    }
    const stopDelay = endEvent ? (endEvent.at - playStartAt) / 1000 : null
    check(
      'barge-in: Omi stopped when interrupted',
      stopDelay !== null && stopDelay < 10,
      stopDelay !== null
        ? `speaking-end ${stopDelay.toFixed(1)}s after user speech began (>60s passage)`
        : 'no speaking-end correlated with the interruption'
    )
    if (!(stopDelay !== null && stopDelay < 10)) exitCode = 1

    // ── CHECK 3: device switch mid-conversation ──────────────────────────────
    const outputs = await page.evaluate(() => globalThis.__omiVoice.listOutputs())
    const alt = outputs.find((d) => d.deviceId && d.deviceId !== 'default' && d.label)
    if (!alt) {
      note('device switch', 'skipped — no second output device enumerated')
    } else {
      log(`[${timestamp()}] switching output to "${alt.label}" mid-conversation…`)
      const ok = await page.evaluate(async (id) => {
        try {
          await globalThis.__omiVoice.setOutputDevice(id)
          await new Promise((r) => setTimeout(r, 2000))
          await globalThis.__omiVoice.setOutputDevice('') // back to default (cable)
          return globalThis.__omiVoice.getState().status === 'live'
        } catch (e) {
          return `error: ${e?.message ?? e}`
        }
      }, alt.deviceId)
      check('device switch mid-conversation keeps the session live', ok === true, String(ok))
      if (ok !== true) exitCode = 1
    }

    // ── CHECK 4: TTS through the same gated path ─────────────────────────────
    log(`[${timestamp()}] TTS gated-path check…`)
    const preIds = new Set((await readTranscript()).map((s) => s.id))
    const ttsOk = await page.evaluate(async () => {
      try {
        await globalThis.__omiVoice.speakTts(
          'Zeppelin marmalade clockwork — this is a spoken reply through text to speech.'
        )
        return true
      } catch (e) {
        return `error: ${e?.message ?? e}`
      }
    })
    if (ttsOk !== true) {
      check('TTS synthesize + gated playback', false, String(ttsOk))
      exitCode = 1
    } else {
      await new Promise((r) => setTimeout(r, 12_000))
      segments = await readTranscript()
      // Diff by segment IDENTITY, not array offset (the store may have
      // cleared/saved between reads).
      const ttsLeaks = leakedLines(segments.filter((s) => !preIds.has(s.id)))
      check(
        'TTS: words NOT transcribed from the speaker loop',
        ttsLeaks.length === 0,
        ttsLeaks.length ? `leaked: ${JSON.stringify(ttsLeaks.slice(0, 3))}` : undefined
      )
      if (ttsLeaks.length) exitCode = 1
    }

    // ── Wind down ────────────────────────────────────────────────────────────
    await page.evaluate(() => globalThis.__omiVoice.stop())
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`)
    exitCode = 1
  } finally {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    restoreAudioDefaults()
    fs.rmSync(tmp, { recursive: true, force: true })
    // Summary + exit INSIDE finally: early `return`s in the try (failed
    // checks) must still honor the exit-code contract — a plain return would
    // fall out of main() and exit 0 (false success).
    log('──────── summary ────────')
    for (const r of results) log(`  ${r.pass ? 'PASS' : 'FAIL'}  ${r.name}`)
    log(exitCode === 0 ? 'ALL CHECKS PASSED' : 'CHECKS FAILED — see above')
    process.exit(exitCode)
  }
}

main().catch((e) => {
  console.error(`[voice-loop] error: ${e?.stack || e}`)
  restoreAudioDefaults()
  process.exit(1)
})
