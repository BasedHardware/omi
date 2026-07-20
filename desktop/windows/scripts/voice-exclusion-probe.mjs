// STATE-LEVEL live proof for the single-audible-owner fix (fix/win-voice-exclusive).
//
// Launches the REAL built app (out/main) with the e2e voice hook enabled and,
// through the SHIPPED renderer bundle (audibleOutputArbiter + voiceController),
// proves the "two voices at once" regression is now impossible at the state level:
//   1. no realtime lane audible → speakTts SPEAKS (records `tts-start`)
//   2. a realtime lane audible  → speakTts is DENIED (records
//      `tts-suppressed-realtime-active`, never `tts-start`) while
//      `isRealtimeAudible()` is true
//   3. realtime lane ends       → speakTts SPEAKS again
//
// No auth, mic, or audio device needed: the deny decision is made in speakText
// BEFORE any synth/network, and we assert on the recorded voice-event trail.
//
// Exit: 0 all pass · 1 a check failed · 2 preconditions missing.
import { execFileSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')
const results = []
const log = (m) => console.log(`[voice-exclusion] ${m}`)
const check = (name, pass, detail) => {
  results.push({ name, pass })
  log(`${pass ? 'PASS' : 'FAIL'}: ${name}${detail ? ` — ${detail}` : ''}`)
}

async function findMainWindow(app) {
  for (let i = 0; i < 60; i++) {
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
async function waitFor(page, fnBody, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const v = await page.evaluate(fnBody)
    if (v) return v
    if (Date.now() > deadline) throw new Error(`timeout waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 400))
  }
}
/** Types of the events recorded since a marker index. */
const eventsSince = (page, from) =>
  page.evaluate(
    (n) =>
      globalThis.__omiVoice
        .getEvents()
        .slice(n)
        .map((e) => e.type),
    from
  )
const eventCount = (page) => page.evaluate(() => globalThis.__omiVoice.getEvents().length)

async function main() {
  if (!NO_BUILD) {
    log('building app (electron-vite build)…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`SKIP: built main not found (${mainEntry}) — run without --no-build`)
    process.exit(2)
  }
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-voiceexcl-ud-'))
  let app = null
  let exitCode = 0
  try {
    app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0' }
    })
    const page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await waitFor(
      page,
      () => typeof globalThis.__omiVoice?.speakTts === 'function',
      30_000,
      'e2e hook'
    )
    await waitFor(
      page,
      () => typeof globalThis.__omiVoice?.beginRealtimeAudible === 'function',
      10_000,
      'arbiter probes'
    )
    log('app up, e2e voice hook + arbiter probes present')

    // Baseline: nothing realtime is audible.
    const idle = await page.evaluate(() => globalThis.__omiVoice.isRealtimeAudible())
    check('no realtime lane audible at rest', idle === false, `isRealtimeAudible=${idle}`)

    // (1) cascade speaks when no realtime lane owns the speaker.
    let mark = await eventCount(page)
    await page.evaluate(() => globalThis.__omiVoice.speakTts('cascade reply one'))
    await new Promise((r) => setTimeout(r, 400))
    let types = await eventsSince(page, mark)
    check(
      'cascade SPEAKS when idle (records tts-start)',
      types.includes('tts-start'),
      types.join(',')
    )

    // (2) a realtime lane is audible → the cascade is DENIED, never spoken.
    await page.evaluate(() => globalThis.__omiVoice.beginRealtimeAudible())
    const audible = await page.evaluate(() => globalThis.__omiVoice.isRealtimeAudible())
    check('realtime lane marked audible', audible === true, `isRealtimeAudible=${audible}`)
    mark = await eventCount(page)
    await page.evaluate(() =>
      globalThis.__omiVoice.speakTts('duplicate reply that must NOT be spoken')
    )
    await new Promise((r) => setTimeout(r, 400))
    types = await eventsSince(page, mark)
    check(
      'cascade DENIED while realtime audible (tts-suppressed-realtime-active)',
      types.includes('tts-suppressed-realtime-active'),
      types.join(',')
    )
    check(
      'cascade produced NO audible output while realtime audible (no tts-start)',
      !types.includes('tts-start'),
      types.join(',')
    )

    // (3) realtime lane ends → the cascade may speak again.
    await page.evaluate(() => globalThis.__omiVoice.endRealtimeAudible())
    const released = await page.evaluate(() => globalThis.__omiVoice.isRealtimeAudible())
    check('realtime lane released', released === false, `isRealtimeAudible=${released}`)
    mark = await eventCount(page)
    await page.evaluate(() => globalThis.__omiVoice.speakTts('cascade reply three'))
    await new Promise((r) => setTimeout(r, 400))
    types = await eventsSince(page, mark)
    check('cascade SPEAKS again after realtime ends', types.includes('tts-start'), types.join(','))
  } catch (e) {
    check('harness ran without throwing', false, e?.message ?? String(e))
  } finally {
    try {
      await app?.close()
    } catch {
      /* ignore */
    }
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* ignore */
    }
  }
  const failed = results.filter((r) => !r.pass)
  log(`\n${results.length - failed.length}/${results.length} checks passed`)
  exitCode = failed.length === 0 ? 0 : 1
  process.exit(exitCode)
}

main()
