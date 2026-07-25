/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Sidebar shell E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and asserts the collapse-rail layout contract — the
// orb and the collapse toggle must NEVER overlap (regression for C1, where the
// fixed-width orb canvas overflowed under the collapse button in the 64px rail,
// measured 14.67px of overlap). Hermetic: OMI_E2E_FAKE_AUTH injects an offline
// fake user so the authed shell mounts on the production build without any
// network. Each launch gets its own throwaway --user-data-dir.
//
// Build first, then run: `pnpm test:e2e:sidebar` (scripts/run-sidebar-e2e.mjs).
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.orb-out', 'shell-shots')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-sidebar-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`, ...extraArgs],
    env: baseEnv
  })
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
  return { app, cleanup }
}

// Keep in sync with SECONDARY_HASHES in src/renderer/src/lib/windowRole.ts — the
// source of truth for "which window am I?". (A bare import isn't free here: this
// spec runs under plain `node --test` with no TS loader, so we mirror the list
// and name the origin so the drift is obvious.)
const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

/** Resolve the MAIN window (not the bar/capture/toast surfaces) and wait for the
 *  authed shell's sidebar <nav> to mount. */
async function mainPageWithSidebar(app) {
  await app.firstWindow()
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      const hasNav = await page
        .evaluate(() => !!document.querySelector('nav button[aria-label$="sidebar"]'))
        .catch(() => false)
      if (hasNav) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window sidebar never mounted')
}

/** Bounding boxes of the sidebar <nav>, its orb <canvas>, and the collapse
 *  toggle button, plus whether the sidebar is currently collapsed (rail width). */
function measure(page) {
  return page.evaluate(() => {
    const nav = document.querySelector('nav')
    const orb = nav?.querySelector('canvas')
    const btn = nav?.querySelector('button[aria-label$="sidebar"]')
    if (!nav || !orb || !btn) return null
    const box = (el) => {
      const b = el.getBoundingClientRect()
      return {
        left: b.left,
        right: b.right,
        top: b.top,
        bottom: b.bottom,
        width: b.width,
        height: b.height
      }
    }
    return { nav: box(nav), orb: box(orb), btn: box(btn) }
  })
}

const overlaps = (a, b) =>
  a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top

/** Assert the load-bearing layout contract for a given state label. */
function assertNoCollision(m, label) {
  assert.ok(m, `${label}: sidebar geometry not found`)
  // (1) The orb and the collapse button must not overlap — the C1 regression.
  assert.ok(
    !overlaps(m.orb, m.btn),
    `${label}: orb ${JSON.stringify(m.orb)} overlaps collapse button ${JSON.stringify(m.btn)}`
  )
  // (2) Neither element may overflow the rail horizontally (the orb canvas is a
  // FIXED 22px width — pre-fix it spilled past the right edge under the button).
  for (const [name, el] of [
    ['orb', m.orb],
    ['btn', m.btn]
  ]) {
    assert.ok(
      el.left >= m.nav.left - 0.5 && el.right <= m.nav.right + 0.5,
      `${label}: ${name} ${JSON.stringify(el)} overflows the rail ${JSON.stringify(m.nav)}`
    )
  }
}

async function toggleCollapsed(page, wantCollapsed) {
  await page.click('nav button[aria-label$="sidebar"]')
  // The rail animates width (w-60 ↔ w-16); wait for it to settle to the target.
  await page.waitForFunction(
    (collapsed) => {
      const nav = document.querySelector('nav')
      if (!nav) return false
      const w = nav.getBoundingClientRect().width
      return collapsed ? w < 90 : w > 200
    },
    wantCollapsed,
    { timeout: 5000 }
  )
  // A tick past the 200ms transition so the rects are final.
  await new Promise((r) => setTimeout(r, 350))
}

// The two DPI variants are independent (own Electron + user-data-dir), so run
// them concurrently for a wall-clock win.
describe('sidebar collapse-rail layout', { concurrency: true }, () => {
  for (const [label, args] of [
    ['100', []],
    ['150', ['--force-device-scale-factor=1.5']]
  ]) {
    test(`sidebar: orb never collides with the collapse toggle (dpi ${label})`, async (t) => {
      const { app, cleanup } = await launch(args)
      t.after(cleanup)
      const page = await mainPageWithSidebar(app)

      // Fresh profile → sidebar starts EXPANDED. Assert the expanded contract, then
      // collapse and assert the rail contract (the state where C1 failed).
      const expanded = await measure(page)
      assert.ok(expanded && expanded.nav.width > 200, `dpi ${label}: sidebar should start expanded`)
      assertNoCollision(expanded, `dpi ${label} expanded`)

      await toggleCollapsed(page, true)
      const collapsed = await measure(page)
      assert.ok(collapsed && collapsed.nav.width < 90, `dpi ${label}: sidebar should be collapsed`)
      assertNoCollision(collapsed, `dpi ${label} collapsed`)

      // Re-expand and confirm the layout returns to a clean expanded state (the
      // collapse transition animates through both layouts without leaving debris).
      await toggleCollapsed(page, false)
      assertNoCollision(await measure(page), `dpi ${label} re-expanded`)
    })
  }
})

test('sidebar screenshots (collapsed / expanded) for the skeptical review', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const { app, cleanup } = await launch()
  t.after(cleanup)
  const page = await mainPageWithSidebar(app)
  await new Promise((r) => setTimeout(r, 500)) // let the shell settle

  await page.screenshot({ path: path.join(shotsDir, 'sidebar-expanded.png') })
  await toggleCollapsed(page, true)
  await page.screenshot({ path: path.join(shotsDir, 'sidebar-collapsed.png') })
  await toggleCollapsed(page, false)
  await page.screenshot({ path: path.join(shotsDir, 'sidebar-reexpanded.png') })
})
