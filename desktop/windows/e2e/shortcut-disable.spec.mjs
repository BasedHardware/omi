/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Record-hotkey "Off" chip E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron and exercises Settings →
// Shortcuts → Record hotkey → Off. Ports macOS's per-shortcut disable to the one
// Windows shortcut where it's architecturally clean (the Record chord is NOT
// push-to-talk; the Summon chord is, so Summon has no Off chip). Verifies:
//  - the Off chip renders on the Record card and NOT on the Summon card,
//  - clicking Off flips the persisted `enabled` state (read back through
//    window.omi.getRecordHotkey()) and shows the "off" note,
//  - the disabled state survives a reload.
// Hermetic: OMI_E2E_FAKE_AUTH boots an offline authed shell (no network). Each
// launch gets its own throwaway --user-data-dir; screenshots → .playwright-mcp/.
//
// Run after a build: node --test e2e/shortcut-disable.spec.mjs
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
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-shortcut-e2e-'))
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

async function openShortcuts(page) {
  await page.evaluate(() => {
    window.location.hash = '#/settings'
  })
  const rail = page.getByRole('button', { name: 'Shortcuts', exact: true })
  await rail.waitFor({ state: 'visible', timeout: 8000 })
  await rail.click()
  await page.getByRole('heading', { level: 1, name: 'Shortcuts' }).waitFor({ state: 'visible', timeout: 8000 })
  await new Promise((r) => setTimeout(r, 300))
  return page.locator('section:not(.hidden)').filter({ has: page.getByRole('heading', { level: 1, name: 'Shortcuts' }) })
}

// Each SettingRow card is a `div.border-b` (SettingRow root). Scope chip queries
// to a card by its unique title text.
const cardFor = (panel, title) => panel.locator('div.border-b').filter({ hasText: title })

// Read the persisted record-hotkey state straight from the bridge — the ground
// truth the Off chip drives.
const recordEnabled = (page) =>
  page.evaluate(() => window.omi?.getRecordHotkey?.().then((s) => s?.enabled))

describe('Shortcuts — Record hotkey Off chip', () => {
  test('Off disables only the Record chord and persists', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    const panel = await openShortcuts(page)

    // Both cards render.
    await panel.getByText('Summon hotkey', { exact: true }).waitFor({ state: 'visible', timeout: 8000 })
    await panel.getByText('Record hotkey', { exact: true }).waitFor({ state: 'visible', timeout: 8000 })
    await page.screenshot({ path: path.join(shotsDir, 'shortcuts-default.png') })

    // Exactly one "Off" chip exists — on the Record card, not the Summon card
    // (Summon is coupled to PTT, so it is intentionally not disable-able).
    assert.equal(
      await panel.getByRole('button', { name: 'Off', exact: true }).count(),
      1,
      'exactly one Off chip (Record card only)'
    )
    const recordCard = cardFor(panel, 'Record hotkey')
    const summonCard = cardFor(panel, 'Summon hotkey')
    const recordOff = recordCard.getByRole('button', { name: 'Off', exact: true })
    await recordOff.waitFor({ state: 'visible', timeout: 8000 })
    assert.equal(
      await summonCard.getByRole('button', { name: 'Off', exact: true }).count(),
      0,
      'Summon card must NOT have an Off chip (it is coupled to PTT)'
    )

    // Baseline: record hotkey is enabled.
    assert.equal(await recordEnabled(page), true, 'record hotkey enabled by default')

    // Click Off → persisted state flips to disabled and the "off" note appears.
    await recordOff.click()
    await new Promise((r) => setTimeout(r, 250))
    assert.equal(await recordEnabled(page), false, 'record hotkey disabled after clicking Off')
    await panel.getByText(/off/i).first().waitFor({ state: 'visible', timeout: 3000 })
    await page.screenshot({ path: path.join(shotsDir, 'shortcuts-record-off.png') })

    // Persist across reload.
    await page.reload()
    await mainPage(app)
    assert.equal(await recordEnabled(page), false, 'disabled state persisted across reload')
    const panel2 = await openShortcuts(page)

    // Re-enable by clicking the Record card's Default chip → state → enabled.
    await cardFor(panel2, 'Record hotkey').getByRole('button', { name: /Default/ }).click()
    await new Promise((r) => setTimeout(r, 250))
    assert.equal(await recordEnabled(page), true, 're-enabled by selecting Default')
    await page.screenshot({ path: path.join(shotsDir, 'shortcuts-record-reenabled.png') })
  })
})
