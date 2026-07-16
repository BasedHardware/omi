/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Connections panel E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron. Opens the Hub's Connect stage (the ask-bar "Connect"
// toggle) and asserts the registered ConnectionsPanel renders its two-column TRAY
// top level (Mac's homeConnectPanel: "Connect data" sources + "Use omi memory
// anywhere" destinations), then exercises the drill-in navigation and screenshots
// each state at 1280x720 for the skeptical reviewer. Hermetic: OMI_E2E_FAKE_AUTH
// boots an offline authed shell; no backend is required (status probes fail closed).
//
// Run after a build: electron-vite build && node --test e2e/connections.spec.mjs
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
mkdirSync(shotsDir, { recursive: true })

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture', '#/glow']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-conn-e2e-'))
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
  throw new Error('main window never became ready')
}

const clickTestId = (page, id) =>
  page.evaluate((t) => document.querySelector(`[data-testid="${t}"]`)?.click(), id)

const hasText = (page, t) =>
  page.evaluate(
    (text) => !![...document.querySelectorAll('*')].find((el) => el.textContent === text),
    t
  )

describe('Connections panel', () => {
  test('Connect stage renders the two-column tray and drills in', async () => {
    const { app, cleanup } = await launch()
    try {
      const page = await mainPage(app)

      // Deterministic 1280x720 for the reviewer's screenshot.
      await app.evaluate(({ BrowserWindow }) => {
        const w = BrowserWindow.getAllWindows().find(
          (win) => !/#\/(bar|insight-toast|capture|glow)/.test(win.webContents.getURL())
        )
        if (w) {
          w.setResizable(true)
          w.setContentSize(1280, 720)
        }
      })

      await page.evaluate(() => {
        window.location.hash = '#/home'
      })
      await page.waitForSelector('[aria-label="Ask omi anything"]', { timeout: 15000 })

      // Open the Connect stage via the ask bar's Connect toggle (aria-pressed +
      // "Connect" label). It only renders while the bar is unfocused (resting hub).
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find(
          (b) => b.getAttribute('aria-pressed') !== null && /Connect/.test(b.textContent || '')
        )
        if (!btn) throw new Error('Connect toggle not found')
        btn.click()
      })

      const tray = await page.waitForSelector('[data-testid="connect-tray"]', { timeout: 15000 })
      assert.ok(tray, 'the ConnectionsPanel tray renders in the Connect stage')

      // The two-column top level: both serif headers and every tile.
      for (const text of ['Connect data', 'Use omi memory anywhere']) {
        assert.ok(await hasText(page, text), `tray shows the "${text}" column header`)
      }
      for (const id of [
        'tray-tile-gmail',
        'tray-tile-calendar',
        'tray-tile-sticky-notes',
        'tray-tile-x-twitter',
        'tray-tile-omi-device',
        'tray-tile-more-imports',
        'tray-tile-ask-omi',
        'tray-tile-claude-claude-code',
        'tray-tile-chatgpt-codex',
        'tray-tile-openclaw',
        'tray-tile-hermes',
        'tray-tile-more-exports'
      ]) {
        const present = await page.evaluate(
          (t) => !!document.querySelector(`[data-testid="${t}"]`),
          id
        )
        assert.ok(present, `tray shows tile ${id}`)
      }

      await new Promise((r) => setTimeout(r, 500)) // let the drop-in transition settle
      await page.screenshot({ path: path.join(shotsDir, 'connections-01-tray.png') })

      // Drill into the full Imports list from the left "+ More".
      await clickTestId(page, 'tray-tile-more-imports')
      await page.waitForFunction(
        () => document.querySelector('[data-testid="connections-detail"]'),
        {
          timeout: 10000
        }
      )
      for (const text of [
        'Imports',
        'Calendar',
        'Email',
        'Sticky Notes',
        'X (Twitter)',
        'ChatGPT',
        'Claude',
        'Browse the App Marketplace'
      ]) {
        assert.ok(await hasText(page, text), `Imports list shows "${text}"`)
      }
      await new Promise((r) => setTimeout(r, 300))
      await page.screenshot({ path: path.join(shotsDir, 'connections-02-imports.png') })

      // Back to the tray, then the OpenClaw "coming soon" detail.
      await clickTestId(page, 'connections-back')
      await page.waitForSelector('[data-testid="connect-tray"]', { timeout: 10000 })
      await clickTestId(page, 'tray-tile-openclaw')
      await page.waitForFunction(
        () =>
          !![...document.querySelectorAll('*')].find(
            (el) => el.textContent === 'Live connection setup is coming soon.'
          ),
        { timeout: 10000 }
      )
      await new Promise((r) => setTimeout(r, 300))
      await page.screenshot({ path: path.join(shotsDir, 'connections-03-comingsoon.png') })

      // The App Marketplace link (in the coming-soon detail) navigates to /apps.
      await clickTestId(page, 'connector-browse-the-app-marketplace')
      await page.waitForFunction(() => window.location.hash.includes('/apps'), undefined, {
        timeout: 10000
      })
      await new Promise((r) => setTimeout(r, 400))
      await page.screenshot({ path: path.join(shotsDir, 'connections-04-apps-nav.png') })
    } finally {
      await cleanup()
    }
  })
})
