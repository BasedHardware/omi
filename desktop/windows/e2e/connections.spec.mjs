/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Connections panel E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron. Opens the Hub's Connect stage (the ask-bar "Connect"
// toggle) and asserts the registered ConnectionsPanel renders its real content —
// the Imports/Exports sections and every connector card — then screenshots it at
// 1280x720 for the skeptical reviewer. Hermetic: OMI_E2E_FAKE_AUTH boots an
// offline authed shell; no backend is required (useMemories' fetch simply fails
// closed to an empty list, which the panel renders fine).
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

describe('Connections panel', () => {
  test('Connect stage renders the registered Imports/Exports connectors', async () => {
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

      const panel = await page.waitForSelector('[data-testid="connections-panel"]', {
        timeout: 15000
      })
      assert.ok(panel, 'the ConnectionsPanel is registered and renders in the Connect stage')

      // The real content: both section headers and every connector row (Mac order).
      for (const text of [
        'Imports',
        'Exports',
        'Calendar',
        'Email',
        'Sticky Notes',
        'ChatGPT',
        'Claude',
        'Notion',
        'Obsidian',
        'Markdown file',
        'Browse the App Marketplace'
      ]) {
        const found = await page.evaluate(
          (t) => !![...document.querySelectorAll('*')].find((el) => el.textContent === t),
          text
        )
        assert.ok(found, `panel shows "${text}"`)
      }

      // A couple of the interactive affordances exist (not dead UI).
      const stickyReadBtn = await page.evaluate(
        () =>
          !![...document.querySelectorAll('button')].find((b) =>
            /Read notes/.test(b.textContent || '')
          )
      )
      assert.ok(stickyReadBtn, 'Sticky Notes has a live "Read notes" action')

      await new Promise((r) => setTimeout(r, 500)) // let the drop-in transition settle
      await page.screenshot({ path: path.join(shotsDir, 'connections-01-panel.png') })

      // Scroll the panel's own overflow region to the foot so the Exports section
      // and the App Marketplace link card are in-frame for the reviewer.
      await page.evaluate(() => {
        const panel = document.querySelector('[data-testid="connections-panel"]')
        const scroller = panel?.querySelector('.overflow-y-auto')
        if (scroller) scroller.scrollTop = scroller.scrollHeight
      })
      await new Promise((r) => setTimeout(r, 300))
      await page.screenshot({ path: path.join(shotsDir, 'connections-01b-exports.png') })

      // The App Marketplace link navigates to /apps and closes the panel.
      await page.evaluate(() =>
        document.querySelector('[data-testid="connections-apps-link"]').click()
      )
      await page.waitForFunction(() => window.location.hash.includes('/apps'), undefined, {
        timeout: 10000
      })
      await new Promise((r) => setTimeout(r, 400))
      await page.screenshot({ path: path.join(shotsDir, 'connections-02-apps-nav.png') })
    } finally {
      await cleanup()
    }
  })
})
