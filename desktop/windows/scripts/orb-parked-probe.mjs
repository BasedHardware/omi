// Live proof of perf/win-orb-parked-idle: the bar orb's rAF/WebGL loop must run
// while the bar is ON-SCREEN and STOP while it is parked off-screen — in both
// directions, across repeated summon/park cycles. Measures raw requestAnimationFrame
// callbacks in the bar renderer (the orb reschedules rAF every frame while visible;
// setVisible(false) cancels it), and screenshots each reveal so a reviewer can
// confirm no black/stale flash.
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const OUT = process.env.OUT || path.join(root, '.orb-out', 'orb-parked')
mkdirSync(OUT, { recursive: true })
const env = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function findBar(app) {
  for (let i = 0; i < 100; i++) {
    const p = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
    if (p) return p
    await sleep(100)
  }
  throw new Error('no bar page')
}

// rAF callbacks counted over `ms` in the bar page (no self-perpetuating loop —
// we only WRAP the existing rAF, we never schedule our own).
async function rafOver(page, ms) {
  await page.evaluate(() => {
    const w = window
    if (!w.__rafWrapped) {
      w.__rafCount = 0
      const orig = w.requestAnimationFrame.bind(w)
      w.requestAnimationFrame = (cb) =>
        orig((t) => {
          w.__rafCount++
          return cb(t)
        })
      w.__rafWrapped = true
    }
  })
  const before = await page.evaluate(() => window.__rafCount)
  await sleep(ms)
  const after = await page.evaluate(() => window.__rafCount)
  return after - before
}

async function summonVisible(app) {
  await app.evaluate(() => globalThis.__omiE2E.barSummonFire())
  for (let i = 0; i < 60; i++) {
    if ((await app.evaluate(() => globalThis.__omiE2E.barState())).visible) return true
    await sleep(50)
  }
  return false
}

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-orbparked-'))
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env })
  const results = []
  try {
    await app.firstWindow()
    // Keep the pill from auto-retracting while we sample the on-screen window.
    await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
    const page = await findBar(app)
    const client = await page.context().newCDPSession(page)

    // Baseline: before any summon the bar is parked (mode=null) — orb must be idle.
    const baseline = await rafOver(page, 1000)
    console.log(`baseline (never summoned, parked): ${baseline} rAF/s`)

    for (let cycle = 1; cycle <= 3; cycle++) {
      const shown = await summonVisible(app)
      await sleep(300) // settle the genesis entrance
      // Screenshot the revealed frame (reviewer checks for black/stale flash).
      const shot = await client.send('Page.captureScreenshot', { format: 'png' })
      writeFileSync(path.join(OUT, `cycle${cycle}-reveal.png`), Buffer.from(shot.data, 'base64'))
      const onScreen = await rafOver(page, 1000)

      await app.evaluate(() => globalThis.__omiE2E.barHide())
      // Graceful hide: willHide (renderer slide-out ~200ms) → requestHide → park.
      await sleep(900)
      const parkedState = await app.evaluate(() => globalThis.__omiE2E.barState())
      const parked = await rafOver(page, 1000)

      console.log(
        `cycle ${cycle}: shown=${shown} | on-screen ${onScreen} rAF/s → parked ${parked} rAF/s ` +
          `(barState.visible=${parkedState.visible})`
      )
      results.push({ cycle, onScreen, parked, visibleAfterHide: parkedState.visible })
    }

    // Verdict.
    const ok =
      baseline < 15 &&
      results.every((r) => r.onScreen > 40 && r.parked < 15 && r.visibleAfterHide === false)
    console.log(`\nVERDICT: ${ok ? 'PASS' : 'FAIL'}`)
    console.log('  expect: on-screen high (>40/s), parked ~0 (<15/s), every cycle')
    console.log(`  screenshots -> ${OUT}`)
    if (!ok) process.exitCode = 2
  } finally {
    try {
      await app.close()
    } catch {
      /* ignore */
    }
    rmSync(dir, { recursive: true, force: true })
  }
}
main().catch((e) => {
  console.error(e)
  process.exit(1)
})
