/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Font Size E2E (Track 6): drives the REAL built app (out/main/index.js) via
// Playwright's _electron and exercises Settings → General → Font Size against real
// preference persistence + the root-rem font-scale application. Hermetic:
// OMI_E2E_FAKE_AUTH boots an offline authed shell (no network). Each launch gets
// its own throwaway --user-data-dir. Screenshots land in .playwright-mcp/ for the
// skeptical reviewer.
//
// Run after a build: node --test e2e/font-size.spec.mjs
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-fontsize-e2e-'))
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`, ...extraArgs], env: baseEnv })
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

async function mainPage(app) {
  await app.firstWindow()
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

async function openGeneral(page) {
  await page.evaluate(() => {
    window.location.hash = '#/settings'
  })
  const rail = page.getByRole('button', { name: 'General', exact: true })
  await rail.waitFor({ state: 'visible', timeout: 8000 })
  await rail.click()
  await page.getByRole('heading', { level: 1, name: 'General' }).waitFor({ state: 'visible', timeout: 8000 })
  await new Promise((r) => setTimeout(r, 300))
  return page.locator('section:not(.hidden)').filter({ has: page.getByRole('heading', { level: 1, name: 'General' }) })
}

// Read the applied root font-size (px) — the whole point of the feature.
const rootFontPx = (page) => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))

describe('Font Size — General settings', () => {
  test('slider scales the root rem, persists, resets', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    const panel = await openGeneral(page)

    // Card is present with the default scale label.
    const card = panel.getByText('Font Size', { exact: true })
    await card.waitFor({ state: 'visible', timeout: 8000 })
    await assert.doesNotReject(panel.getByText(/^Scale: \d+%$/).first().waitFor({ state: 'visible', timeout: 4000 }))
    await page.screenshot({ path: path.join(shotsDir, 'general-fontsize-default.png') })

    const baseline = await rootFontPx(page)
    assert.ok(Math.abs(baseline - 16) < 0.6, `default root font-size ~16px (got ${baseline})`)

    // Drive the slider via keyboard (deterministic): focus the slider thumb and
    // press ArrowRight a few times → scale increases → root px grows.
    const thumb = panel.getByRole('slider', { name: 'Font size' })
    await thumb.focus()
    for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowRight') // +0.05 * 6 = +0.30
    await new Promise((r) => setTimeout(r, 150))
    const grown = await rootFontPx(page)
    assert.ok(grown > baseline + 3, `root font grew after slider (base ${baseline} → ${grown})`)
    // "Reset" affordance appears once scale ≠ 100%.
    await panel.getByRole('button', { name: 'Reset', exact: true }).waitFor({ state: 'visible', timeout: 3000 })
    await page.screenshot({ path: path.join(shotsDir, 'general-fontsize-scaled.png') })

    // Full-card capture at the larger scale so a reviewer can confirm nothing
    // clips/overflows/wraps at ~130%: the "Scale: 1NN%" subtitle, the slider, the
    // preview line, the three Ctrl shortcut hint rows, and the "Reset Window Size"
    // button. Scroll the whole card into view, then capture the full page.
    await panel.getByText('Font Size', { exact: true }).scrollIntoViewIfNeeded()
    await new Promise((r) => setTimeout(r, 150))
    await page.screenshot({
      path: path.join(shotsDir, 'general-fontsize-scaled-full.png'),
      fullPage: true
    })

    // Persist across reload (localStorage-backed).
    await page.reload()
    await mainPage(app)
    const afterReload = await rootFontPx(page)
    assert.ok(Math.abs(afterReload - grown) < 0.6, `scale persisted across reload (${grown} → ${afterReload})`)

    // Reset returns to 100% / 16px and hides the Reset button.
    const panel2 = await openGeneral(page)
    await panel2.getByRole('button', { name: 'Reset', exact: true }).click()
    await new Promise((r) => setTimeout(r, 150))
    const reset = await rootFontPx(page)
    assert.ok(Math.abs(reset - 16) < 0.6, `reset to ~16px (got ${reset})`)
    await page.screenshot({ path: path.join(shotsDir, 'general-fontsize-reset.png') })
  })
})
