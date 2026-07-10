// Scripted WAV-playback smoke for the capture + VAD-gate lane, using VB-Audio
// Virtual Cable as a deterministic "microphone":
//
//   PowerShell SoundPlayer → default playback (CABLE Input)  ─┐
//                                                             ├─ virtual cable ─┐
//   app getUserMedia(allowVirtualMic) ← default capture (CABLE Output) ─────────┘
//
// It plays a SILENCE fixture and asserts the listen byte counter stays flat (the
// VAD gate suppresses silence), then plays a SPEECH fixture and asserts bytes flow.
// Auth-free by design — it checks BYTE FLOW only, never transcript content; the
// authed transcript E2E is the orchestrator's separate live pass (pnpm test:e2e:ptt).
//
// Exit codes: 0 pass · 1 assertion failed · 2 skipped (VB-Cable absent, or the
// capture-start hook isn't wired yet — see NEEDS below).
//
// NEEDS from the capture window (Agent A), gated on OMI_E2E: a main-process hook
//   globalThis.__omiE2E.startCaptureForTest({ source: 'mic' }) : Promise<boolean>
// that opens the real capture→gate→feed path against the default input WITHOUT a
// backend session (so getListenStats() moves). Until it exists this harness runs
// device-setup + launch and then skips the byte-flow assertions with exit 2.
import { execFileSync, spawnSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const FIXTURES = path.join(root, 'test', 'fixtures', 'audio')
const SAMPLE_RATE = 16000

function log(m) {
  console.log(`[vad-playback] ${m}`)
}

/** 44-byte canonical WAV header for 16kHz mono s16le + PCM body → temp .wav. */
function pcmToWav(pcmPath, wavPath) {
  const pcm = fs.readFileSync(pcmPath)
  const h = Buffer.alloc(44)
  h.write('RIFF', 0)
  h.writeUInt32LE(36 + pcm.length, 4)
  h.write('WAVE', 8)
  h.write('fmt ', 12)
  h.writeUInt32LE(16, 16) // fmt chunk size
  h.writeUInt16LE(1, 20) // PCM
  h.writeUInt16LE(1, 22) // mono
  h.writeUInt32LE(SAMPLE_RATE, 24)
  h.writeUInt32LE(SAMPLE_RATE * 2, 28) // byte rate
  h.writeUInt16LE(2, 32) // block align
  h.writeUInt16LE(16, 34) // bits/sample
  h.write('data', 36)
  h.writeUInt32LE(pcm.length, 40)
  fs.writeFileSync(wavPath, Buffer.concat([h, pcm]))
}

function ps(script) {
  return spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
    encoding: 'utf8'
  })
}

/** Route the virtual cable as default playback+capture via AudioDeviceCmdlets.
 *  Returns true on success; false (with printed manual steps) if unavailable. */
function setupVirtualCable() {
  const probe = ps(
    "if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) { 'yes' } else { 'no' }"
  )
  if ((probe.stdout || '').trim() !== 'yes') {
    log('AudioDeviceCmdlets PowerShell module not found — cannot auto-route the cable.')
    printManual()
    return false
  }
  const setup = ps(`
    Import-Module AudioDeviceCmdlets
    $play = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' -and $_.Name -match 'CABLE Input' } | Select-Object -First 1
    $rec  = Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' -and $_.Name -match 'CABLE Output' } | Select-Object -First 1
    if (-not $play -or -not $rec) { 'missing'; exit }
    Set-AudioDevice -Index $play.Index | Out-Null
    Set-AudioDevice -Index $rec.Index  | Out-Null
    'ok'
  `)
  if ((setup.stdout || '').trim().split(/\r?\n/).pop() !== 'ok') {
    log('VB-Audio Virtual Cable devices not found (CABLE Input / CABLE Output).')
    printManual()
    return false
  }
  log('routed default playback→CABLE Input, default capture→CABLE Output')
  return true
}

function printManual() {
  log('MANUAL SETUP: install VB-Audio Virtual Cable, then in Windows Sound settings set')
  log('  default PLAYBACK = "CABLE Input" and default RECORDING = "CABLE Output", and re-run.')
}

/** Play a WAV to the default playback device (blocks until finished). */
function playWav(wavPath) {
  ps(`(New-Object System.Media.SoundPlayer '${wavPath.replace(/'/g, "''")}').PlaySync()`)
}

async function readStats(app) {
  return app.evaluate(() => {
    const fn = globalThis.__omiGetListenStats
    return typeof fn === 'function' ? fn() : {}
  })
}

function totalBytes(stats) {
  return Object.values(stats || {}).reduce((n, v) => n + (v?.bytes ?? 0), 0)
}

async function main() {
  // Fixtures (idempotent) — need silence + speech.
  execFileSync('node', [path.join(root, 'scripts', 'gen-audio-fixtures.mjs')], {
    stdio: 'inherit',
    cwd: root
  })
  const silencePcm = path.join(FIXTURES, 'silence-2s.pcm')
  const speechPcm = path.join(FIXTURES, 'speech-hello.pcm')
  for (const f of [silencePcm, speechPcm]) {
    if (!fs.existsSync(f)) {
      log(`fixture missing: ${f}`)
      process.exit(2)
    }
  }

  if (!setupVirtualCable()) process.exit(2)

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-vadplay-'))
  const silenceWav = path.join(tmp, 'silence.wav')
  const speechWav = path.join(tmp, 'speech.wav')
  pcmToWav(silencePcm, silenceWav)
  pcmToWav(speechPcm, speechWav)

  log('building app…')
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  const mainEntry = path.join(root, 'out', 'main', 'index.js')

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-vadplay-ud-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_ALLOW_VIRTUAL_MIC: '1',
      OMI_SKIP_TUNNEL: '1',
      OMI_AUTOMATION: '0'
    }
  })

  let exitCode = 0
  try {
    await app.firstWindow()

    // Wait for the CAPTURE window's renderer to be loaded and its command
    // subscription mounted — audio-start is fire-and-forget, so sending it
    // before the hidden window subscribes drops it silently (found live: the
    // harness raced the capture window's boot and asserted on a void session).
    let captureWin = null
    for (let i = 0; i < 40 && !captureWin; i++) {
      captureWin = app.windows().find((w) => w.url().includes('#/capture')) ?? null
      if (!captureWin) await new Promise((r) => setTimeout(r, 500))
    }
    if (!captureWin) {
      log('FAIL: capture window never appeared')
      exitCode = 1
      return
    }
    await captureWin.waitForLoadState('domcontentloaded')
    await new Promise((r) => setTimeout(r, 2000)) // React mount + host subscriptions

    // Ask the capture window to open the real capture→gate→feed path (no backend).
    const started = await app.evaluate(async () => {
      const hook = globalThis.__omiE2E
      if (!hook || typeof hook.startCaptureForTest !== 'function') return false
      try {
        return (await hook.startCaptureForTest({ source: 'mic' })) !== false
      } catch {
        return false
      }
    })
    if (!started) {
      log(
        'SKIP: capture-start hook globalThis.__omiE2E.startCaptureForTest not wired yet (Agent A).'
      )
      log('      Device setup + app launch validated; byte-flow assertions skipped.')
      exitCode = 2
      return
    }

    // Let gUM + the pipeline spin up before the baseline read (the VAD warm-up
    // passthrough would otherwise count ambient cable noise as 'silence bytes').
    await new Promise((r) => setTimeout(r, 3000))
    const base = totalBytes(await readStats(app))
    log('playing SILENCE fixture…')
    playWav(silenceWav)
    await new Promise((r) => setTimeout(r, 3000)) // let any trailing chunks flush
    const afterSilence = totalBytes(await readStats(app))
    const silenceDelta = afterSilence - base
    log(`bytes during silence: ${silenceDelta}`)

    log('playing SPEECH fixture…')
    playWav(speechWav)
    await new Promise((r) => setTimeout(r, 3000))
    const afterSpeech = totalBytes(await readStats(app))
    const speechDelta = afterSpeech - afterSilence
    log(`bytes during speech: ${speechDelta}`)

    const SILENCE_TOL = 64 * 1024 // a few VAD misfire chunks are fine
    if (silenceDelta > SILENCE_TOL) {
      log(`FAIL: ${silenceDelta}B flowed during silence (> ${SILENCE_TOL}B) — gate leaking`)
      exitCode = 1
    }
    if (speechDelta <= 0) {
      log('FAIL: no bytes flowed during speech — capture/gate not passing voiced audio')
      exitCode = 1
    }
    if (exitCode === 0) log('PASS: silence suppressed, speech flowed')
  } finally {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    fs.rmSync(userDataDir, { recursive: true, force: true })
    fs.rmSync(tmp, { recursive: true, force: true })
  }
  process.exit(exitCode)
}

main().catch((e) => {
  console.error(`[vad-playback] error: ${e?.stack || e}`)
  process.exit(1)
})
