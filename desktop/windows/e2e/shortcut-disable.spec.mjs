/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Record-hotkey "Off" chip E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron and exercises Settings →
// Shortcuts → Record hotkey → Off. Ports macOS's per-shortcut disable to the one
// Windows shortcut where it's architecturally clean (the Record chord is NOT
// push-to-talk; the Summon chord is, so Summon has no Off chip). Verifies:
//  - the Off chip renders on the Record card and NOT on the Summon card,
//  - clicking Off flips the persisted `enabled` state (read back through
//    window.omi.getRecordHotkey()) and shows the "off" note,
//  - the disabled state survives a renderer reload AND a real relaunch (a second
//    Electron process on the same profile — the read-from-disk → never-register
//    path, which page.reload() cannot reach).
// Hermetic: OMI_E2E_FAKE_AUTH boots an offline authed shell (no network). One
// throwaway --user-data-dir per test (shared by its relaunches, removed once at the
// end); screenshots → .playwright-mcp/.
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

// `userDataDir` is a parameter (not minted per launch) so a test can RELAUNCH a
// second Electron process against the SAME profile — the only way to exercise the
// real persistence path (read settings from disk → don't register the chord at
// startup). page.reload() only reloads the renderer; main's process state survives.
async function launch(userDataDir, extraArgs = []) {
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`, ...extraArgs],
    env: baseEnv
  })
  const close = async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
  }
  return { app, close }
}

function makeUserDataDir() {
  return mkdtempSync(path.join(tmpdir(), 'omi-shortcut-e2e-'))
}

function removeUserDataDir(dir) {
  try {
    rmSync(dir, { recursive: true, force: true })
  } catch {
    /* best-effort */
  }
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
    // ONE profile dir, shared by the first app and the relaunched one below. A
    // single teardown hook closes every instance still running, THEN removes the
    // dir (order matters — Windows won't delete a profile a live process holds).
    const userDataDir = makeUserDataDir()
    const running = new Set()
    t.after(async () => {
      for (const close of running) await close()
      removeUserDataDir(userDataDir)
    })
    const track = ({ app, close }) => {
      const done = async () => {
        await close()
        running.delete(done)
      }
      running.add(done)
      return { app, close: done }
    }

    const { app, close } = track(await launch(userDataDir))
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

    // Persist across a renderer reload (main's in-memory state survives here).
    await page.reload()
    await mainPage(app)
    assert.equal(await recordEnabled(page), false, 'disabled state persisted across reload')

    // …and across a REAL relaunch: a brand-new Electron process on the SAME
    // --user-data-dir must read `recordHotkeyEnabled: false` back off disk and NOT
    // register the chord at startup. This is the persistence path the reload above
    // cannot reach (main's module state + appSettings cache outlive page.reload()).
    await close()

    const relaunched = track(await launch(userDataDir))
    const page2 = await mainPage(relaunched.app)
    assert.equal(
      await recordEnabled(page2),
      false,
      'disabled state read back from disk on a fresh process'
    )
    const panel2 = await openShortcuts(page2)
    const recordCard2 = cardFor(panel2, 'Record hotkey')
    const off2 = recordCard2.getByRole('button', { name: 'Off', exact: true })
    await off2.waitFor({ state: 'visible', timeout: 8000 })
    // The Off chip renders SELECTED (Chip's selected styling) on the fresh process.
    assert.match(
      (await off2.getAttribute('class')) ?? '',
      /bg-white\/\[0\.08\]/,
      'Off chip is selected after relaunch'
    )
    await panel2
      .getByText('Recording shortcut is off.')
      .waitFor({ state: 'visible', timeout: 3000 })
    await page2.screenshot({ path: path.join(shotsDir, 'shortcuts-record-off-relaunch.png') })

    // Re-enable by clicking the Record card's Default chip → state → enabled.
    await recordCard2.getByRole('button', { name: /Default/ }).click()
    await new Promise((r) => setTimeout(r, 250))
    assert.equal(await recordEnabled(page2), true, 're-enabled by selecting Default')
    await page2.screenshot({ path: path.join(shotsDir, 'shortcuts-record-reenabled.png') })
  })
})
