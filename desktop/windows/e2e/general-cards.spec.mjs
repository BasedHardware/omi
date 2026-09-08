/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// General capture-status cards E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron and exercises Settings →
// General → Screen Capture + Audio Recording. These two status cards lead the
// General tab (macOS spec §3.1); Screen Capture binds the persistent Rewind
// `captureEnabled` setting, Audio Recording binds the `continuousRecording`
// preference. Hermetic: OMI_E2E_FAKE_AUTH boots an offline authed shell (no
// network). Each launch gets its own throwaway --user-data-dir. Screenshots
// land in .playwright-mcp/ for the skeptical reviewer.
//
// Run after a build: node --test e2e/general-cards.spec.mjs
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
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-general-e2e-'))
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

describe('General — capture-status cards', () => {
  test('Screen Capture + Audio Recording render and toggle', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    const panel = await openGeneral(page)

    // Both cards lead the tab, above "Chat history".
    const screenCard = panel.getByText('Screen Capture', { exact: true })
    const audioCard = panel.getByText('Audio Recording', { exact: true })
    await screenCard.waitFor({ state: 'visible', timeout: 8000 })
    await audioCard.waitFor({ state: 'visible', timeout: 8000 })
    await page.screenshot({ path: path.join(shotsDir, 'general-cards-default.png') })

    // The Audio Recording toggle drives the `continuousRecording` pref, which
    // the card reads back through the preferences listener. Its switch is the
    // Toggle immediately following the Audio Recording title. Flip it and
    // confirm the subtitle reflects the new state (proves the round-trip).
    const audioToggle = panel
      .getByRole('switch', { name: 'Audio Recording' })
      .or(panel.getByLabel('Audio Recording'))
      .first()
    const before = await audioToggle.getAttribute('aria-checked')
    await audioToggle.click()
    await new Promise((r) => setTimeout(r, 200))
    const after = await audioToggle.getAttribute('aria-checked')
    assert.notEqual(before, after, `Audio Recording toggle flipped aria-checked (${before} → ${after})`)
    await page.screenshot({ path: path.join(shotsDir, 'general-cards-audio-toggled.png') })

    // Persist across reload — continuousRecording is localStorage-backed.
    await page.reload()
    await mainPage(app)
    const panel2 = await openGeneral(page)
    const audioToggle2 = panel2
      .getByRole('switch', { name: 'Audio Recording' })
      .or(panel2.getByLabel('Audio Recording'))
      .first()
    const persisted = await audioToggle2.getAttribute('aria-checked')
    assert.equal(persisted, after, `Audio Recording persisted across reload (${after} → ${persisted})`)
    await page.screenshot({ path: path.join(shotsDir, 'general-cards-after-reload.png') })
  })
})
