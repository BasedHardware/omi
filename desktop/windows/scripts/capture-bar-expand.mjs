// Frame-strip capture for the bar's pill⇄panel expand/collapse (task #39).
// Launches the REAL built app (out/main/index.js) via Playwright _electron,
// signed-in (fake auth) so the expanded surface renders real rows, holds the
// peek pill open, then drives peek→expanded→peek and list→conversation while
// screenshotting the bar page in a tight loop.
//
// To decouple capture framerate from the (fast, ~200-260ms) real animation, a
// SLOWMO style multiplies every transition/animation duration so ~20 frames
// land across the morph — this is inspection-only and does NOT touch shipped
// timings. Run against the CURRENT build; set OUT to baseline/ or after/.
//
//   OUT=<dir> [SLOWMO=6] node scripts/capture-bar-expand.mjs
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const OUT = process.env.OUT || path.join(root, '.orb-out', 'bar-expand')
const SLOWMO = Number(process.env.SLOWMO || 6)
mkdirSync(OUT, { recursive: true })

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function findBarPage(app) {
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
    if (page) return page
    await sleep(100)
  }
  throw new Error('bar page (#/bar) not found')
}

async function barShow(app, mode) {
  await app.evaluate((_e, m) => globalThis.__omiE2E.barShow(m), mode)
  for (let i = 0; i < 100; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) return s
    await sleep(50)
  }
  throw new Error(`bar never visible in mode ${mode}`)
}

// Multiply all CSS transition/animation durations so the morph plays slow enough
// to sample cleanly. Inspection-only; not part of the product.
async function installSlowmo(page, factor) {
  await page.evaluate((f) => {
    const style = document.createElement('style')
    style.id = '__slowmo'
    // Scale every transition/animation duration on the bar surfaces so the morph
    // plays slow enough to sample cleanly (inspection-only).
    style.textContent = `
      .bar-surface, .bar-surface.bar-surface-expanded,
      .bar-content, .bar-content.bar-content-active {
        transition-duration: ${300 * f}ms !important;
      }
      .bar-view-enter { animation-duration: ${200 * f}ms !important; }
    `
    document.head.appendChild(style)
  }, factor)
}

async function captureStrip(app, page, label, trigger, frames = 22, stepMs = 55) {
  const dir = path.join(OUT, label)
  mkdirSync(dir, { recursive: true })
  const shots = []
  let done = false
  const loop = (async () => {
    for (let i = 0; i < frames && !done; i++) {
      const p = path.join(dir, `f${String(i).padStart(2, '0')}.png`)
      try {
        await page.screenshot({ path: p, omitBackground: true })
        shots.push(path.basename(p))
      } catch {
        /* window may be mid-teardown */
      }
      await sleep(stepMs)
    }
  })()
  await trigger()
  await loop
  done = true
  writeFileSync(path.join(dir, 'frames.txt'), shots.join('\n') + '\n')
  console.log(`  ${label}: ${shots.length} frames -> ${dir}`)
}

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-bar-cap-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: baseEnv
  })
  try {
    await app.firstWindow()
    await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
    const page = await findBarPage(app)
    await barShow(app, 'peek')
    await sleep(700) // slide-in + genesis settle
    await installSlowmo(page, SLOWMO)

    // 1) EXPAND: peek pill -> expanded panel.
    await captureStrip(app, page, 'expand', async () => {
      await app.evaluate(() => globalThis.__omiE2E.barShow('expanded'))
    })
    await sleep(600 * SLOWMO) // let it fully settle

    // 2) LIST -> CONVERSATION (click the Omi Chat row).
    await captureStrip(app, page, 'list-to-convo', async () => {
      await page.locator('.bar-content-active button', { hasText: 'Omi Chat' }).first().click()
    })
    await sleep(400 * SLOWMO)

    // 3) COLLAPSE: expanded -> peek pill.
    await captureStrip(app, page, 'collapse', async () => {
      await app.evaluate(() => globalThis.__omiE2E.barShow('peek'))
    })
    await sleep(400 * SLOWMO)
    console.log('capture done ->', OUT)
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
