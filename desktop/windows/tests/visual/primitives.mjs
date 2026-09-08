// Visual capture for the shared ui/* primitives gallery (PR #3, Track 5).
//
// The gallery route (#/__ui-gallery) is DEV-gated (import.meta.env.DEV) so it is
// ABSENT from a production `pnpm build` — and electron-vite's renderer `build`
// always compiles in production mode (there is no `--mode development` renderer
// build). The route therefore only exists in the running DEV SERVER, so this
// harness attaches to it over CDP rather than launching the packaged `out/`
// app.
//
// Run:
//   1. Start the dev app:   pnpm dev        (this worktree exposes CDP on the
//                                            port from `pnpm dev:instance`)
//   2. Capture:             OMI_DEV_CDP_PORT=<port> node tests/visual/primitives.mjs
//
// Screenshots (deterministic size/DPI via CDP Emulation.setDeviceMetricsOverride):
//   • primitives-1280.png    — 1280×720 desktop baseline
//   • primitives-modal.png   — 1280×720 with the Modal open (title+body+footer)
//   • primitives-narrow.png  — ~420px narrow width (chip/flow-wrap)
//   • primitives-150dpi.png  — 1280×720 at deviceScaleFactor 1.5 (150% DPI)
// PNGs land in desktop/windows/.playwright-mcp/ (gitignored).
import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const OUT = process.env.OUT || path.join(root, '.playwright-mcp')
const CDP_PORT = process.env.OMI_DEV_CDP_PORT || '9237'
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const SECONDARY = ['#/bar', '#/capture', '#/insight-toast']

async function findMainPage(browser) {
  for (let i = 0; i < 100; i++) {
    for (const ctx of browser.contexts()) {
      const page = ctx.pages().find((p) => !SECONDARY.some((h) => p.url().includes(h)))
      if (page) return page
    }
    await sleep(200)
  }
  throw new Error('main window not found over CDP')
}

async function setMetrics(session, width, height, dsf) {
  await session.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: dsf,
    mobile: false
  })
}

// Capture the WHOLE gallery, not just a viewport slice: set the emulated width
// (so content reflows at that width), measure the full document scrollHeight,
// then grow the emulated viewport to that height and screenshot. This guarantees
// every section (Toggle / Badge / Pill included) is in-frame at every condition.
async function shootFull(page, session, { width, dsf, file }) {
  await setMetrics(session, width, 900, dsf)
  await sleep(300)
  const h = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight))
  await setMetrics(session, width, h, dsf)
  await sleep(300)
  await page.screenshot({ path: path.join(OUT, file) })
  console.log('  wrote', file, `(${width}×${h} @${dsf}x)`)
}

async function main() {
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${CDP_PORT}`)
  try {
    const page = await findMainPage(browser)
    await page.evaluate(() => {
      window.location.hash = '#/__ui-gallery'
    })
    await page.waitForFunction(() => document.body.innerText.includes('UI Primitives'), {
      timeout: 20000
    })
    const session = await page.context().newCDPSession(page)

    // Full-height captures — every primitive (incl. Toggle/Badge/Pill) in-frame.
    await shootFull(page, session, { width: 1280, dsf: 1, file: 'primitives-1280.png' })
    await shootFull(page, session, { width: 420, dsf: 1, file: 'primitives-narrow.png' })
    await shootFull(page, session, { width: 1280, dsf: 1.5, file: 'primitives-150dpi.png' })

    // Modal open (title + body + footer) — a normal viewport so the centered
    // dialog reads naturally over the scrim.
    await setMetrics(session, 1280, 860, 1)
    await sleep(200)
    await page.getByRole('button', { name: 'Open modal' }).click()
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 })
    await sleep(300)
    await page.screenshot({ path: path.join(OUT, 'primitives-modal.png') })
    console.log('  wrote primitives-modal.png')
    await page.keyboard.press('Escape')
    await sleep(200)

    await session.send('Emulation.clearDeviceMetricsOverride')
    console.log('capture done ->', OUT)
  } finally {
    await browser.close()
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
