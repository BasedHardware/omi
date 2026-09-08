/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// PTT summon-gesture E2E: reproduces the 2026-07 field bug against the REAL
// built main process (out/main/index.js). In the field, GetAsyncKeyState read a
// physically-held chord as UP (blind — e.g. an elevated foreground window
// blocks key state for a non-elevated caller) while RegisterHotKey kept firing
// auto-repeats; the old classifier ended the hold as `kind=tap` on the first
// blind sample and every subsequent repeat fire opened a new tap gesture —
// bursts of down/up tap pairs in [ptt-diag], deliberate holds silently
// discarded.
//
// This harness recreates the exact condition deterministically: firing
// __omiE2E.barSummonFire() in a ~30ms burst IS a blind-sampler hold (the
// physical key is genuinely not down, so the sampler reads UP throughout,
// while the fires stand in for the WM_HOTKEY auto-repeats). One fire with no
// follow-ups is a blind tap. Assertions read the app's own [ptt-diag] stdout
// trace — the same lines used to diagnose the field reports.
//
// Build first, then run: `pnpm test:e2e:ptt-gesture` (scripts/run-ptt-gesture-e2e.mjs).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
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

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-ptt-gesture-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: baseEnv
  })
  // Capture the main process's [ptt-diag] trace — the always-on field log.
  const lines = []
  const onData = (chunk) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.includes('[ptt-diag]')) lines.push(line)
    }
  }
  app.process().stdout?.on('data', onData)
  app.process().stderr?.on('data', onData)
  const cleanup = async () => {
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
  }
  return { app, lines, cleanup }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const count = (lines, needle) => lines.filter((l) => l.includes(needle)).length

/** Mount the bar renderer and leave the PILL presented, with the cursor retract
 *  watchdog suspended: this E2E runs on a live desktop, so the real cursor
 *  would otherwise make the pill's lifetime (and these assertions) flaky. With
 *  the watchdog out of the way, only the gesture's own toggle semantics can
 *  hide the bar — exactly what the tests assert. A cold renderer would also
 *  queue the ptt 'down' ("NOT sent (bar not ready)") and skip the trace lines
 *  this spec matches on. */
async function presentPill(app) {
  await app.evaluate(() => {
    globalThis.__omiE2E.barEnable()
    globalThis.__omiE2E.barShow('peek')
  })
  for (let i = 0; i < 100; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) {
      await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
      return
    }
    await sleep(100)
  }
  throw new Error('bar never became visible while priming')
}

test('a blind-sampler hold (repeat-fire burst) is ONE gesture classified HOLD, not a tap storm', async (t) => {
  const { app, lines, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()
  await presentPill(app)
  lines.length = 0 // only the burst's trace matters

  // ~700ms of WM_HOTKEY auto-repeats with the sampler blind the whole time.
  const burstStart = Date.now()
  while (Date.now() - burstStart < 700) {
    await app.evaluate(() => globalThis.__omiE2E.barSummonFire())
    await sleep(30)
  }
  // The repeat-gap (1200ms) must elapse after the last fire for the gesture to end.
  await sleep(1600)

  // Exactly ONE gesture, ended as HOLD via the repeat-gap authority. The old
  // classifier produced one START/END-tap pair per fire (~20 of them).
  assert.equal(count(lines, 'gesture START (sampler)'), 1, `tap-storm regressed: ${lines.join('\n')}`)
  assert.equal(count(lines, 'gesture END kind=hold'), 1, `hold not classified: ${lines.join('\n')}`)
  assert.equal(count(lines, 'kind=tap'), 0, `blind hold discarded as tap: ${lines.join('\n')}`)
  assert.equal(count(lines, 'ended BLIND'), 1, 'blind-classification trace missing')

  // The hold's down/up pair reached the renderer exactly once (primed above).
  assert.equal(count(lines, 'ptt down -> renderer'), 1, 'renderer never received the down')
  assert.equal(count(lines, 'ptt up -> renderer'), 1, 'renderer never received the up')

  // A hold never toggles an OPEN bar shut — the old tap-storm hid it (each
  // misclassified tap on the presented pill fired hideBar).
  const s = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.ok(s.visible, 'the pill must survive a hold (only a tap on an open bar hides it)')
})

test('a blind single fire is ONE gesture classified TAP after the repeat gap', async (t) => {
  const { app, lines, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()
  await presentPill(app)
  lines.length = 0

  await app.evaluate(() => globalThis.__omiE2E.barSummonFire())
  await sleep(1600)

  assert.equal(count(lines, 'gesture START (sampler)'), 1)
  assert.equal(count(lines, 'gesture END kind=tap'), 1, `single fire not a tap: ${lines.join('\n')}`)
  // Tap semantics intact (no-regressions): a tap on an OPEN bar toggles it shut.
  const s = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.ok(!s.visible, 'a tap on an open bar must hide it')
})
