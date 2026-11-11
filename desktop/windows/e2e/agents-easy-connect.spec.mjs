/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// External coding-agent "easy connect" E2E: drives the REAL built app via
// Playwright's _electron to screenshot the reworked Settings → Agents surface —
// per-agent CLI detection status, the one-click Connect buttons, the install
// help block, and Codex's OpenAI API-key lane. On a dev/CI box the three CLIs
// are typically NOT installed, so this captures the honest "not connected"
// state (Connect + install help + key field). Screenshots land in
// .playwright-mcp/ for the skeptical reviewer.
//
// Run after a build: node --test e2e/agents-easy-connect.spec.mjs
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

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-agents-easy-e2e-'))
  const emptyClaudeDir = mkdtempSync(path.join(tmpdir(), 'omi-empty-claude-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_E2E_FAKE_AUTH: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      CLAUDE_CONFIG_DIR: emptyClaudeDir
    }
  })
  const cleanup = async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    for (const d of [dir, emptyClaudeDir]) {
      try {
        rmSync(d, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
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
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

async function openAgents(page) {
  await page.evaluate(() => {
    window.location.hash = '#/settings'
  })
  const rail = page.getByRole('button', { name: 'Agents', exact: true })
  await rail.waitFor({ state: 'visible', timeout: 8000 })
  await rail.click()
  await page
    .getByRole('heading', { level: 1, name: 'Agents' })
    .waitFor({ state: 'visible', timeout: 8000 })
  await new Promise((r) => setTimeout(r, 500)) // detection + codex-key IPC settle
}

describe('external agents easy-connect', () => {
  test('detection + Connect + install help + Codex key screenshots', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    await openAgents(page)

    // The three external rows render.
    for (const name of ['OpenClaw', 'Hermes', 'Codex']) {
      await page.getByText(name, { exact: true }).first().waitFor({ state: 'visible', timeout: 8000 })
    }

    // One-click Connect replaces the hand-pasted command as the primary action.
    assert.ok(
      (await page.getByRole('button', { name: 'Connect' }).count()) >= 1,
      'at least one Connect button'
    )

    await page.screenshot({ path: path.join(shotsDir, 'agents-easy-connect.png'), fullPage: true })

    // Codex exposes an in-app OpenAI API-key lane — it sits lower in the settings
    // pane's own scroll region, so scroll it into view and capture it too.
    const keyLabel = page.getByText('OpenAI API key', { exact: true })
    await keyLabel.waitFor({ state: 'visible', timeout: 8000 })
    await keyLabel.scrollIntoViewIfNeeded()
    await new Promise((r) => setTimeout(r, 300))
    assert.ok(
      (await page.getByPlaceholder('sk-…').count()) >= 1,
      'Codex OpenAI API-key input is present'
    )
    await page.screenshot({ path: path.join(shotsDir, 'agents-easy-connect-codex.png') })
  })
})
