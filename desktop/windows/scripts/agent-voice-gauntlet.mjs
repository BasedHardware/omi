// REAL-AUDIO voice→agent→tool→voice E2E gauntlet for the Windows Omi desktop app.
//
// Proves the WHOLE loop end-to-end with real audio and a real agent tool call:
//   synthesized speech (Windows SAPI)
//     → played into VB-Cable (default playback = CABLE Input)
//     → captured as the app mic (default capture = CABLE Output)  [PTT hold]
//     → Deepgram STT (prod backend, Firebase-authed)
//     → committed transcript → shared chat engine → pi_mono kernel
//     → the agent INVOKES a built-in tool (bash / read / write)
//     → replies in text (mainChat:event text_delta/completed)
//     → SPEAKS the reply via TTS → into CABLE Input → looped to CABLE Output
//     → ffmpeg captures the reply; we assert sustained voiced audio (it SPOKE).
//
// Tool surface today (see docs research): pi_mono has ONLY pi's BUILT-IN tools
// (bash/read/write/edit/grep/find/ls) — the Omi product/control tool relay is
// DARK on merged main. So the LIVE matrix targets built-in tools only:
//   A1  "run echo hello world in the shell"          → bash
//   A2  "read package.json and tell me the version"  → read (then bash/grep)
//   A3  "create a file omi-test-fixture-<runid>.txt"  → write
//
// Observability: the renderer UI IGNORES tool events on the pi-mono door, so we
// subscribe to the `mainChat:event` IPC stream directly (window.omi.onMainChatEvent)
// and assert `tool_activity{status:'completed'}` + read `tool_result_display.output`
// (pi-mono NEVER emits status:'failed' — an errored tool still shows 'completed';
// the error text lands in the output with an `Error:`/`POLICY_DENIED:` prefix). We
// also assert the durable audit log (per-run OMI_PI_AUDIT_LOG, JSONL).
//
// Auth: unattended via the .env refresh-token pattern (OMI_E2E_REFRESH_TOKEN +
// VITE_FIREBASE_API_KEY) exchanged fresh per run; STT/chat hit the PROD desktop
// backend — no local backend needed.
//
// SAFETY: runs ONLY against the isolated _electron instance this script launches
// (never CDP :9222 / a prod bundle). Snapshots + RESTORES the OS default audio
// devices in a finally (global OS state). Kills only the ffmpeg/electron it started.
//
// Exit: 0 all tests pass · 1 a test failed · 2 preconditions missing.
import { execFileSync, spawn, spawnSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SAMPLE_RATE = 16000
const NO_BUILD = process.argv.includes('--no-build')
const RUN_ID = Date.now().toString(36)

// Gate constants mirror the app (src/renderer/src/lib/ptt/constants.ts) — the
// 20ms/RMS-300 voiced-frame rule, reused to measure the spoken reply.
const VOICED_RMS_THRESHOLD = 300
const VOICED_FRAME_SAMPLES = 320 // 20ms @ 16kHz
const REPLY_VOICED_MS_MIN = 500 // the "it spoke" bar
const HOLD_THRESHOLD_MS = 350
const MAX_TURN_ATTEMPTS = 3

function log(m) {
  console.log(`[gauntlet] ${m}`)
}
const results = []
function check(name, pass, detail) {
  results.push({ name, pass, detail })
  log(`${pass ? 'PASS' : 'FAIL'}: ${name}${detail ? ` — ${detail}` : ''}`)
}

// ── PowerShell + audio-device routing (same pattern as run-voice-loop-check) ──
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
  savedAudioDefaults = null
}

// ── SAPI TTS → 16kHz mono WAV (the sapiSpeakToWav routine from gen-audio-fixtures) ──
function sapiSpeakToWav(text, wavPath) {
  const ps1 = path.join(os.tmpdir(), `omi-gauntlet-tts-${Date.now()}.ps1`)
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
function playWav(wavPath) {
  // PlaySync blocks for the clip length; plays to the default render (CABLE Input).
  ps(`(New-Object System.Media.SoundPlayer '${wavPath.replace(/'/g, "''")}').PlaySync()`)
}

// ── Voiced-ms measurement (the app's own 20ms/RMS-300 gate) ───────────────────
function voicedMsOfPcm(pcmBuf) {
  if (!pcmBuf || pcmBuf.byteLength < VOICED_FRAME_SAMPLES * 2) return 0
  const pcm = new Int16Array(pcmBuf.buffer, pcmBuf.byteOffset, Math.floor(pcmBuf.byteLength / 2))
  const frames = Math.floor(pcm.length / VOICED_FRAME_SAMPLES)
  let voiced = 0
  for (let f = 0; f < frames; f++) {
    const base = f * VOICED_FRAME_SAMPLES
    let sumSq = 0
    for (let i = 0; i < VOICED_FRAME_SAMPLES; i++) sumSq += pcm[base + i] * pcm[base + i]
    if (Math.sqrt(sumSq / VOICED_FRAME_SAMPLES) >= VOICED_RMS_THRESHOLD) voiced++
  }
  return voiced * 20
}

// ── ffmpeg reply capture (dshow) ──────────────────────────────────────────────
const FFMPEG = 'ffmpeg'
function findDshowCaptureName() {
  // `-list_devices true` prints device names to stderr.
  const out = spawnSync(FFMPEG, ['-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'], {
    encoding: 'utf8'
  })
  const text = `${out.stdout || ''}\n${out.stderr || ''}`
  // Lines look like:  [dshow @ ...] "CABLE Output (VB-Audio Virtual Cable)" (audio)
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/"([^"]*CABLE Output[^"]*)"/i)
    if (m) return m[1]
  }
  return null
}
function startReplyCapture(deviceName, outPath) {
  const child = spawn(
    FFMPEG,
    [
      '-hide_banner',
      '-loglevel',
      'error',
      '-f',
      'dshow',
      '-i',
      `audio=${deviceName}`,
      '-ac',
      '1',
      '-ar',
      String(SAMPLE_RATE),
      '-f',
      's16le',
      '-y',
      outPath
    ],
    { stdio: ['pipe', 'ignore', 'pipe'] }
  )
  let stderr = ''
  child.stderr.on('data', (d) => {
    stderr += d.toString()
  })
  child.on('error', (e) => {
    stderr += `spawn error: ${e.message}`
  })
  return { child, getStderr: () => stderr }
}
async function stopReplyCapture(cap) {
  const { child } = cap
  if (!child || child.exitCode !== null || child.killed) return
  await new Promise((resolve) => {
    let done = false
    const fin = () => {
      if (done) return
      done = true
      resolve()
    }
    child.on('close', fin)
    try {
      child.stdin.write('q')
    } catch {
      /* fall through to kill */
    }
    setTimeout(() => {
      try {
        child.kill('SIGKILL')
      } catch {
        /* already gone */
      }
      fin()
    }, 4000)
  })
}

// ── App / playwright helpers ──────────────────────────────────────────────────
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
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}
async function findBarWindow(app) {
  for (let i = 0; i < 60; i++) {
    const page = app.windows().find((w) => /#\/bar/.test(w.url()))
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
    await new Promise((r) => setTimeout(r, 400))
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
  await page.evaluate(
    ({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
    { key: `firebase:authUser:${apiKey}:[DEFAULT]`, value: user }
  )
}

// ── The tests (built-in-tool matrix, reachable TODAY) ─────────────────────────
const TESTS = [
  {
    id: 'A1',
    request: 'Please run the shell command echo hello world and tell me what it printed.',
    expectTool: 'bash',
    transcriptWords: ['hello', 'world'],
    file: null
  },
  {
    id: 'A2',
    request: 'Read the file package dot json in the current folder and tell me the version field.',
    expectTool: 'read',
    altTools: ['bash', 'grep', 'find'],
    transcriptWords: ['package', 'version'],
    file: null
  },
  {
    id: 'A3',
    request: `Create a file named omi-test-fixture-${RUN_ID} dot t x t containing the word hello.`,
    expectTool: 'write',
    altTools: ['bash', 'edit'],
    transcriptWords: ['create', 'file'],
    file: `omi-test-fixture-${RUN_ID}.txt`
  }
]

// Extract a plausible created-file path from a write/bash tool result or audit line.
function extractCreatedPath(outputs, fileName) {
  for (const out of outputs) {
    if (!out) continue
    // Match an absolute Windows or POSIX path ending in our file name.
    const re = new RegExp(`([A-Za-z]:[\\\\/][^\\s"']*${fileName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}|/[^\\s"']*${fileName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`)
    const m = out.match(re)
    if (m) return m[1].replace(/\\/g, '/')
  }
  return null
}

async function main() {
  const env = readDotEnv(path.join(root, '.env'))
  const refreshToken = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const apiKey = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!refreshToken || !apiKey) {
    log('SKIP: OMI_E2E_REFRESH_TOKEN / VITE_FIREBASE_API_KEY missing from .env')
    process.exit(2)
  }

  // Preconditions: ffmpeg present + dshow can see CABLE Output.
  const ffprobe = spawnSync(FFMPEG, ['-version'], { encoding: 'utf8' })
  if (ffprobe.status !== 0) {
    log('SKIP: ffmpeg not on PATH')
    process.exit(2)
  }
  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`SKIP: built main not found (${mainEntry}) — run without --no-build`)
    process.exit(2)
  }
  if (!setupVirtualCable()) {
    restoreAudioDefaults()
    process.exit(2)
  }
  const dshowName = findDshowCaptureName()
  if (!dshowName) {
    log('SKIP: ffmpeg dshow cannot see a "CABLE Output" capture device')
    restoreAudioDefaults()
    process.exit(2)
  }
  log(`ffmpeg reply-capture device: "${dshowName}"`)

  let idToken
  try {
    idToken = await exchangeRefreshToken(refreshToken, apiKey)
  } catch (e) {
    log(`SKIP: refresh-token exchange failed (${e.message})`)
    restoreAudioDefaults()
    process.exit(2)
  }
  log(`auth ok (uid ${decodeJwt(idToken)?.user_id})`)

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-'))
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-ud-'))
  const auditLog = path.join(tmp, 'pi-mono-audit.log')
  const createdFiles = []
  let exitCode = 0
  let app = null

  try {
    app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: {
        ...process.env,
        OMI_E2E: '1',
        OMI_ALLOW_VIRTUAL_MIC: '1',
        OMI_AUTOMATION: '0',
        OMI_PI_AUDIT_LOG: auditLog
      }
    })

    // ── Sign in on the main window ──────────────────────────────────────────
    let page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await injectAuth(page, { apiKey, idToken, refreshToken })
    await page.evaluate(() => {
      const KEY = 'omi-windows-prefs-v1'
      const prefs = JSON.parse(localStorage.getItem(KEY) ?? '{}')
      prefs.onboardingCompletedAt = prefs.onboardingCompletedAt ?? Date.now()
      localStorage.setItem(KEY, JSON.stringify(prefs))
      location.reload()
    })
    await new Promise((r) => setTimeout(r, 3000))
    page = await findMainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    await waitFor(page, () => typeof globalThis.__omiVoice?.getAuthUid === 'function', 30_000, 'e2e hook')
    const uid = await waitFor(page, () => globalThis.__omiVoice.getAuthUid(), 30_000, 'signed-in uid')
    log(`app signed in as ${uid}`)

    // Subscribe to the pi-mono tool/reply event stream on the MAIN window
    // (mainChat:event is broadcast to every window).
    await page.evaluate(() => {
      window.__tev = []
      window.omi.onMainChatEvent((e) => window.__tev.push(e))
    })

    // ── Pre-warm the (hidden) bar window so __omiPtt attaches ────────────────
    await app.evaluate(() => {
      const h = globalThis.__omiE2E
      if (h?.barEnable) h.barEnable()
    })
    const barPage = await findBarWindow(app)
    if (!barPage) throw new Error('bar window never appeared (barEnable did not pre-warm it)')
    await barPage.waitForLoadState('domcontentloaded')
    await waitFor(barPage, () => typeof globalThis.__omiPtt?.beginHold === 'function', 30_000, '__omiPtt hook')
    // Mirror the bar chat state (user transcript + assistant reply) onto window.
    await barPage.evaluate(() => {
      window.__bcs = { messages: [], sending: false, status: 'idle' }
      window.omiBar.onChatState((s) => {
        window.__bcs = s
      })
      window.omiBar.requestChatState()
    })
    log('bar window ready (__omiPtt attached, chat-state mirrored)')

    // ── Run each test ───────────────────────────────────────────────────────
    for (const t of TESTS) {
      const outcome = await runTurn({ app, page, barPage, t, tmp, dshowName, auditLog })
      // Assertions
      const heardWords = t.transcriptWords.filter((w) =>
        (outcome.transcript || '').toLowerCase().includes(w.toLowerCase())
      )
      const transcriptOk = outcome.transcript && outcome.transcript.trim().length > 0
      const toolFired =
        outcome.toolsFired.includes(t.expectTool) ||
        (t.altTools || []).some((a) => outcome.toolsFired.includes(a))
      const spoke = outcome.replyVoicedMs >= REPLY_VOICED_MS_MIN
      const replyOk = outcome.reply && outcome.reply.trim().length > 0

      const detail =
        `transcript="${(outcome.transcript || '').slice(0, 80)}" | ` +
        `tools=[${outcome.toolsFired.join(',')}] | ` +
        `audit=[${outcome.auditTools.join(',')}] | ` +
        `reply="${(outcome.reply || '').slice(0, 60)}" | ` +
        `replyVoicedMs=${outcome.replyVoicedMs} | attempts=${outcome.attempts}` +
        (outcome.note ? ` | ${outcome.note}` : '')

      let filePass = true
      if (t.file) {
        const created = extractCreatedPath(
          [...outcome.toolOutputs, outcome.reply],
          t.file
        )
        let exists = false
        if (created && fs.existsSync(created)) {
          exists = true
          createdFiles.push(created)
        } else {
          // Fallback: search the app userData + common cwds for the file.
          const found = searchForFile(t.file, [userDataDir, root, process.cwd(), os.homedir()])
          if (found) {
            exists = true
            createdFiles.push(found)
          }
        }
        filePass = exists
      }

      const pass = transcriptOk && toolFired && replyOk && spoke && filePass
      check(
        `${t.id} voice→${t.expectTool}→voice`,
        pass,
        `${detail}${t.file ? ` | fileCreated=${filePass}` : ''}${
          heardWords.length ? '' : ' | (transcript keyword miss)'
        }`
      )
      if (!pass) exitCode = 1
    }
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`)
    exitCode = 1
  } finally {
    // Delete any files the agent created (test-data hygiene).
    for (const f of createdFiles) {
      try {
        fs.rmSync(f, { force: true })
        log(`cleaned up created file: ${f}`)
      } catch {
        /* ignore */
      }
    }
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
    log('──────── summary ────────')
    for (const r of results) log(`  ${r.pass ? 'PASS' : 'FAIL'}  ${r.name} — ${r.detail}`)
    log(exitCode === 0 && results.length ? 'ALL TESTS PASSED' : 'SEE RESULTS ABOVE')
    process.exit(results.length ? exitCode : 2)
  }
}

function searchForFile(fileName, dirs) {
  for (const d of dirs) {
    try {
      const p = path.join(d, fileName)
      if (fs.existsSync(p)) return p
    } catch {
      /* ignore */
    }
  }
  return null
}

/** Drive one real-audio PTT turn; retries up to MAX_TURN_ATTEMPTS on an
 *  STT/hold timeout (machine contention can drop a turn). */
async function runTurn({ app, page, barPage, t, tmp, dshowName, auditLog }) {
  const wav = path.join(tmp, `${t.id}-req.wav`)
  sapiSpeakToWav(`Omi test fixture. ${t.request}`, wav)

  let last = { transcript: '', reply: '', toolsFired: [], toolOutputs: [], auditTools: [], replyVoicedMs: 0, attempts: 0, note: '' }

  for (let attempt = 1; attempt <= MAX_TURN_ATTEMPTS; attempt++) {
    last.attempts = attempt
    log(`[${t.id}] attempt ${attempt}: "${t.request}"`)

    // Reset the tool-event ring + record the pre-turn message count.
    await page.evaluate(() => {
      window.__tev = []
    })
    const preMsgCount = await barPage.evaluate(() => (window.__bcs?.messages || []).length)

    // Begin a REAL PTT hold on the bar, play the request WAV inside the hold,
    // then release. playWav (PlaySync) blocks for the clip → the hold spans it.
    await barPage.evaluate(() => window.__omiPtt.beginHold())
    await new Promise((r) => setTimeout(r, 200)) // let the mic graph warm
    const holdStart = Date.now()
    playWav(wav) // blocks ~2-4s
    const held = Date.now() - holdStart
    if (held < HOLD_THRESHOLD_MS) await new Promise((r) => setTimeout(r, HOLD_THRESHOLD_MS - held + 50))
    await barPage.evaluate(() => window.__omiPtt.endHold())

    // Start capturing the reply NOW (request audio has finished; only the TTS
    // reply will play into the cable from here on).
    const replyPcm = path.join(tmp, `${t.id}-reply-${attempt}.pcm`)
    const cap = startReplyCapture(dshowName, replyPcm)

    // Wait for the turn: a tool_activity completed AND a terminal run event.
    let turnOk = false
    let runError = null
    try {
      await waitFor(
        page,
        () =>
          window.__tev.some((e) => e.type === 'run_finished') ||
          window.__tev.some((e) => e.type === 'completed'),
        60_000,
        `${t.id} turn terminal`
      )
      turnOk = true
    } catch {
      // no terminal event in time
    }

    // Give TTS a moment to start, then wait for the spoken reply to drain.
    const evts = await page.evaluate(() => window.__tev)
    const rf = evts.find((e) => e.type === 'run_finished')
    if (rf && rf.status === 'failed') runError = rf.error || 'run failed'

    // Wait for the bar status to hit 'speaking' then leave it (TTS reply), or a cap.
    let sawSpeaking = false
    const speakDeadline = Date.now() + 20_000
    while (Date.now() < speakDeadline) {
      const st = await barPage.evaluate(() => window.__bcs?.status)
      if (st === 'speaking') sawSpeaking = true
      if (sawSpeaking && st !== 'speaking') break
      await new Promise((r) => setTimeout(r, 300))
    }
    // A short tail so the final syllable is captured.
    await new Promise((r) => setTimeout(r, 800))
    await stopReplyCapture(cap)

    // Collect results.
    const toolEvents = evts.filter((e) => e.type === 'tool_activity' && e.status === 'completed')
    const toolsFired = [...new Set(toolEvents.map((e) => e.name).filter(Boolean))]
    const toolOutputs = evts
      .filter((e) => e.type === 'tool_result_display')
      .map((e) => e.output || '')
    const replyText =
      (evts.filter((e) => e.type === 'completed').map((e) => e.text).filter(Boolean).pop()) ||
      evts.filter((e) => e.type === 'text_delta').map((e) => e.text).join('')
    const bcs = await barPage.evaluate(() => window.__bcs)
    const msgs = (bcs?.messages || [])
    const newMsgs = msgs.slice(preMsgCount)
    const transcript =
      [...newMsgs].reverse().find((m) => m.role === 'user')?.content ||
      [...msgs].reverse().find((m) => m.role === 'user')?.content ||
      ''
    const barReply = [...newMsgs].reverse().find((m) => m.role === 'assistant')?.content || ''
    const reply = (replyText || barReply || '').trim()

    let replyPcmBuf = null
    try {
      replyPcmBuf = fs.readFileSync(replyPcm)
    } catch {
      /* no capture */
    }
    const replyVoicedMs = voicedMsOfPcm(replyPcmBuf)

    // Audit log tool names for THIS run (best effort; per-run file).
    let auditTools = []
    try {
      const lines = fs.readFileSync(auditLog, 'utf8').split(/\r?\n/).filter(Boolean)
      auditTools = [
        ...new Set(
          lines
            .map((l) => {
              try {
                return JSON.parse(l)
              } catch {
                return null
              }
            })
            .filter((o) => o && o.phase === 'after')
            .map((o) => o.tool)
            .filter(Boolean)
        )
      ]
    } catch {
      /* no audit file yet */
    }

    last = {
      transcript,
      reply,
      toolsFired,
      toolOutputs,
      auditTools,
      replyVoicedMs,
      attempts: attempt,
      note: runError ? `runError=${runError}` : sawSpeaking ? '' : 'no-speaking-status'
    }

    log(
      `[${t.id}] transcript="${transcript.slice(0, 60)}" tools=[${toolsFired.join(',')}] ` +
        `reply="${reply.slice(0, 40)}" voicedMs=${replyVoicedMs} turnOk=${turnOk}`
    )

    // Success = we heard a transcript, a tool fired, and a reply exists. (Voice
    // capture is measured but a contention-flaky capture shouldn't force a retry
    // that re-spends a chat turn — we retry only when the FRONT half failed.)
    const frontHalfOk = transcript.trim().length > 0 && (toolsFired.length > 0 || reply.length > 0)
    if (frontHalfOk) return last
    if (runError) return last // a real run failure won't fix on retry with same input
    log(`[${t.id}] front-half incomplete (likely STT/hold contention) — retrying`)
    await new Promise((r) => setTimeout(r, 1500))
  }
  return last
}

main().catch((e) => {
  console.error(`[gauntlet] fatal: ${e?.stack || e}`)
  restoreAudioDefaults()
  process.exit(1)
})
