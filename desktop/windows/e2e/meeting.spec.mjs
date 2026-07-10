/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Meeting-detection E2E: drives the REAL built app via Playwright's _electron.
// Hermetic — no auth, no network, no real Zoom: fake Tier1/Tier2 signals are
// injected through the OMI_E2E-gated __omiE2E.meeting hook, and assertions
// cover the FULL pipeline: pure machine transitions → toast window DOM →
// meeting-capture command round trip into the capture window (which fails its
// unauthenticated /v4/listen start and reports 'error' status back to main —
// proving the whole main → capture-window → main loop without credentials).
//
// The YAMNet test runs REAL model inference (self-hosted /vad/ assets) on
// fixture PCM via the capture window's classify hook — no audio devices needed,
// so it is NOT blocked by the soak owning the sound card. It exits SKIP-style
// (t.skip) if the speech fixtures haven't been generated.
//
// Build first, then run: `pnpm test:e2e:meeting` (scripts/run-meeting-e2e.mjs).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const zoomAgreed = {
  candidate: true,
  agreed: { id: 'zoom', name: 'Zoom', exe: 'zoom.exe', via: 'process', tier2Key: 'zoom.exe' },
  tier2Ids: ['zoom.exe']
}
const quiet = { candidate: false, agreed: null, tier2Ids: [] }

async function launch(userDataDir) {
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: baseEnv
  })
  await app.firstWindow()
  // The monitor starts on ready-to-show — injecting earlier is dropped.
  await pollUntil(
    () => app.evaluate(() => !!globalThis.__omiE2E?.meeting?.running()),
    'meeting monitor running'
  )
  return app
}

const meeting = {
  inject: (app, sig) => app.evaluate((_e, s) => globalThis.__omiE2E.meeting.inject(s), sig),
  override: (app, cfg) => app.evaluate((_e, c) => globalThis.__omiE2E.meeting.override(c), cfg),
  phase: (app) => app.evaluate(() => globalThis.__omiE2E.meeting.phase()),
  capturing: (app) => app.evaluate(() => globalThis.__omiE2E.meeting.capturing()),
  statusLog: (app) => app.evaluate(() => globalThis.__omiE2E.meeting.statusLog())
}

async function pollUntil(fn, what, timeoutMs = 15000, everyMs = 150) {
  const start = Date.now()
  for (;;) {
    const v = await fn()
    if (v) return v
    if (Date.now() - start > timeoutMs) throw new Error(`timed out waiting for ${what}`)
    await new Promise((r) => setTimeout(r, everyMs))
  }
}

/** The toast + capture windows load lazily; find a page by URL fragment. */
async function findPage(app, fragment) {
  return pollUntil(
    async () => app.windows().find((w) => w.url().includes(fragment)),
    `window ${fragment}`
  )
}

function withApp(name, fn) {
  test(name, async (t) => {
    const dir = mkdtempSync(path.join(tmpdir(), 'omi-e2e-meeting-'))
    const app = await launch(dir)
    t.after(async () => {
      try {
        await app.evaluate(({ app: a }) => a.quit()) // real quit path (tray app)
      } catch {
        /* ignore */
      }
      try {
        await app.close()
      } catch {
        /* already closed */
      }
      try {
        rmSync(dir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })
    await fn(app, t)
  })
}

withApp('auto mode: idle → candidate → active (toast + capture cmd) → ending → idle', async (app) => {
  await meeting.override(app, { mode: 'auto', debounceMs: 300, endGraceMs: 1500 })

  assert.equal(await meeting.phase(app), 'idle')

  // Tier 1 only (Zoom running, mic idle) — candidate, never active.
  await meeting.inject(app, { candidate: true, agreed: null, tier2Ids: [] })
  assert.equal(await meeting.phase(app), 'candidate')
  await new Promise((r) => setTimeout(r, 700)) // > debounce: still not active
  assert.equal(await meeting.phase(app), 'candidate')

  // Agreement → debounced activation (deadline timer re-steps on its own).
  await meeting.inject(app, zoomAgreed)
  await pollUntil(async () => (await meeting.phase(app)) === 'active', 'phase=active')

  // The toast rendered the capturing notice (auto mode is never silent).
  const toast = await findPage(app, 'insight-toast')
  await pollUntil(
    async () => (await toast.textContent('body'))?.includes('Omi is capturing'),
    'capturing toast text'
  )

  // The capture window received meeting-capture-start, ran the session host,
  // failed its unauthenticated listen start, and reported back to main.
  const log = await pollUntil(
    async () => {
      const l = await meeting.statusLog(app)
      return l.some((s) => s.endsWith(':error')) ? l : null
    },
    'meeting-capture-status round trip'
  )
  assert.ok(log[0].startsWith('meeting-'), `status carries the meeting id: ${log[0]}`)

  // Tier 2 quiet → ending → (grace) → idle.
  await meeting.inject(app, quiet)
  assert.equal(await meeting.phase(app), 'ending')
  await pollUntil(async () => (await meeting.phase(app)) === 'idle', 'phase=idle after grace')
  assert.equal(await meeting.capturing(app), false)
})

withApp('ask mode: toast buttons drive capture start/stop', async (app) => {
  await meeting.override(app, { mode: 'ask', debounceMs: 200, endGraceMs: 60_000 })

  await meeting.inject(app, zoomAgreed)
  await pollUntil(async () => (await meeting.phase(app)) === 'active', 'phase=active')

  // Ask mode: NOT capturing until the user says so.
  assert.equal(await meeting.capturing(app), false)

  const toast = await findPage(app, 'insight-toast')
  await pollUntil(
    async () => (await toast.textContent('body'))?.includes('Capture and transcribe'),
    'ask toast text'
  )

  // Click "Start capturing" → main starts the capture session.
  await toast.click('text=Start capturing')
  await pollUntil(
    async () => (await meeting.statusLog(app)).length > 0,
    'capture round trip after Start click'
  )
  // The toast swapped to the capturing notice.
  await pollUntil(
    async () => (await toast.textContent('body'))?.includes('Omi is capturing'),
    'toast swapped to capturing'
  )
})

withApp('false positive: media playing without a Tier 1 match never activates', async (app) => {
  await meeting.override(app, { mode: 'auto', debounceMs: 200, endGraceMs: 1500 })

  // "YouTube playing": no conferencing process/title (tier1 fails); even a
  // stray mic user (voice recorder) present. Machine must stay idle.
  await meeting.inject(app, { candidate: false, agreed: null, tier2Ids: ['audacity.exe'] })
  assert.equal(await meeting.phase(app), 'idle')
  await new Promise((r) => setTimeout(r, 800))
  assert.equal(await meeting.phase(app), 'idle')
  assert.equal(await meeting.capturing(app), false)
  assert.deepEqual(await meeting.statusLog(app), [])
})

withApp('yamnet live inference: real model classifies fixture PCM', async (app, t) => {
  const fixtures = path.join(root, 'test', 'fixtures', 'audio')
  const speechPcm = path.join(fixtures, 'speech-hello.pcm')
  if (!existsSync(speechPcm)) {
    t.skip('speech fixtures missing — run `pnpm fixtures:audio` first')
    return
  }

  const capture = await findPage(app, 'capture')
  await pollUntil(
    () => capture.evaluate(() => !!globalThis.__omiCaptureE2E),
    'capture E2E hook installed'
  )

  const classify = async (buf) =>
    capture.evaluate(
      (b64) => globalThis.__omiCaptureE2E.classifyPcmBase64(b64),
      buf.toString('base64')
    )

  // Real SAPI speech (16kHz s16le, ~5.7s) → must classify as speech.
  const speech = await classify(readFileSync(speechPcm))
  console.log(`[yamnet] speech-hello.pcm → ${speech}`)
  assert.equal(speech, 'speech')

  // Silence → must NOT be speech (fail-open unknown is expected).
  const silence = await classify(readFileSync(path.join(fixtures, 'silence-2s.pcm')))
  console.log(`[yamnet] silence-2s.pcm → ${silence}`)
  assert.notEqual(silence, 'speech')

  // Synthesized music-ish clip (ffmpeg chord arpeggio). YAMNet is trained on
  // real music; synthetic tones may map to 'Sine wave'-family labels →
  // 'unknown' under our fail-open mapping. Hard assert: never 'speech'.
  // Real-music verdict is part of the deferred live matrix (VB-Cable owned by
  // the soak) — see the PR notes.
  let music = null
  try {
    const tmp = path.join(tmpdir(), `omi-e2e-music-${Date.now()}.pcm`)
    execFileSync('ffmpeg', [
      '-y',
      '-f',
      'lavfi',
      '-i',
      'aevalsrc=0.30*sin(2*PI*220*t)+0.28*sin(2*PI*277*t)+0.26*sin(2*PI*330*t)+0.18*sin(2*PI*440*(t+0.4*sin(2*PI*2*t))):s=16000:d=5',
      '-f',
      's16le',
      '-acodec',
      'pcm_s16le',
      tmp
    ])
    music = await classify(readFileSync(tmp))
    rmSync(tmp, { force: true })
  } catch (e) {
    console.log(`[yamnet] music clip skipped (ffmpeg unavailable?): ${e.message}`)
  }
  if (music !== null) {
    console.log(`[yamnet] synth music clip → ${music}`)
    assert.notEqual(music, 'speech')
  }
})
