/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Settings-parity E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and exercises the three new Settings tabs against real
// IPC (getAppVersion, getSummonHotkey, checkForUpdates, preference persistence).
// Hermetic: OMI_E2E_FAKE_AUTH boots an offline authed shell (no network). Each
// launch gets its own throwaway --user-data-dir. Screenshots land in
// .playwright-mcp/ for the skeptical reviewer.
//
// Run after a build: node --test e2e/settings-parity.spec.mjs
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

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-settings-e2e-'))
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

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

async function mainPage(app) {
  await app.firstWindow()
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      // Shell mounted = the React root has content. Don't require the sidebar: it's
      // hidden on the /settings route (App.tsx hideSidebar), so a reload landing
      // back on Settings would otherwise never satisfy a sidebar-based wait.
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

/** Open Settings (hash route) and select a tab by its rail label; wait for the
 *  tab's <h1> title to be the visible active panel. */
async function openTab(page, label) {
  await page.evaluate(() => {
    window.location.hash = '#/settings'
  })
  // The rail lists every tab; click the one whose text matches exactly.
  const railButton = page.getByRole('button', { name: label, exact: true })
  await railButton.waitFor({ state: 'visible', timeout: 8000 })
  await railButton.click()
  // Active panel's <h1> is the tab label; wait for it to be visible (not a hidden
  // still-mounted sibling panel).
  await page
    .getByRole('heading', { level: 1, name: label })
    .waitFor({ state: 'visible', timeout: 8000 })
  await new Promise((r) => setTimeout(r, 300)) // enter transition settle
  // Every tab panel stays mounted (hidden when inactive) so Settings search can
  // see all rows — scope interactions to the one visible panel section.
  return page
    .locator('section:not(.hidden)')
    .filter({ has: page.getByRole('heading', { level: 1, name: label }) })
}

describe('settings parity — Transcription / Shortcuts / About', () => {
  test('screenshots + real-IPC interactions for the skeptical review', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    // ---- Transcription -----------------------------------------------------
    let panel = await openTab(page, 'Transcription')
    await page.screenshot({ path: path.join(shotsDir, 'transcription.png') })

    // Single-language mode is the default → the language <select> is visible.
    const langSelect = panel.locator('select')
    assert.equal(await langSelect.count(), 1, 'exactly one language select in the panel')
    await langSelect.selectOption('es')
    // VAD gate switch defaults ON.
    const vad = panel.getByRole('switch', { name: 'Local VAD gate' })
    assert.equal(await vad.getAttribute('aria-checked'), 'true', 'VAD gate on by default')
    await vad.click()
    // Let the switch's 200ms knob slide settle before capturing (the dot snaps
    // instantly; the knob animates — capturing mid-slide misreads the state).
    await vad.waitFor({ state: 'visible' })
    await new Promise((r) => setTimeout(r, 350))
    assert.equal(await vad.getAttribute('aria-checked'), 'false', 'VAD gate flipped off')
    await page.screenshot({ path: path.join(shotsDir, 'transcription-changed.png') })

    // Persistence across reload: the language choice must survive a renderer reload
    // (localStorage-backed, and it feeds the listen socket next session).
    await page.reload()
    await mainPage(app)
    panel = await openTab(page, 'Transcription')
    const persisted = await panel.locator('select').inputValue()
    assert.equal(persisted, 'es', 'language persisted across reload')
    const vadAfter = await panel
      .getByRole('switch', { name: 'Local VAD gate' })
      .getAttribute('aria-checked')
    assert.equal(vadAfter, 'false', 'VAD gate off persisted across reload')

    // ---- Shortcuts ---------------------------------------------------------
    panel = await openTab(page, 'Shortcuts')
    // A card per chord; each has a Default preset chip + a Custom recorder chip.
    const customs = panel.getByRole('button', { name: 'Custom…' })
    assert.equal(await customs.count(), 2, 'summon + record custom chips')
    await page.screenshot({ path: path.join(shotsDir, 'shortcuts.png') })
    // Enter capture mode on the summon (1st) card → recording affordance shows.
    await customs.nth(0).click()
    await panel
      .getByText('Press keys… (Esc to cancel)')
      .first()
      .waitFor({ state: 'visible', timeout: 4000 })
    await page.screenshot({ path: path.join(shotsDir, 'shortcuts-recording.png') })
    await page.keyboard.press('Escape') // cancel capture

    // ---- About -------------------------------------------------------------
    panel = await openTab(page, 'About')
    // Real app version renders (dev build = package.json version).
    await panel
      .getByText(/^Version \d+\.\d+\.\d+/)
      .first()
      .waitFor({ state: 'visible', timeout: 8000 })
    await page.screenshot({ path: path.join(shotsDir, 'about.png') })
    // Check-for-updates does something sane (unpackaged dev → "installs automatically").
    await panel.getByRole('button', { name: 'Check for updates' }).click()
    await panel
      .getByText(/Updates install automatically|latest version|Update available|Couldn't check/)
      .first()
      .waitFor({ state: 'visible', timeout: 8000 })
    await page.screenshot({ path: path.join(shotsDir, 'about-checked.png') })
  })
})
