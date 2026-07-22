/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Claude Code sign-in + Omi Pro upsell E2E: drives the REAL built app via
// Playwright's _electron. Boots signed-out for Claude Code by pointing
// CLAUDE_CONFIG_DIR at an empty dir (so the real authStatus IPC reports no
// credentials), then screenshots (1) the Settings → Agents signed-out row and
// (2) the "Upgrade to Omi Pro" sheet the "Sign in to Claude" button raises.
//
// OMI_E2E suppresses the real browser launch inside codingAgent:startAuth, so
// clicking Sign in shows the sheet hermetically (no claude.ai tab). Screenshots
// land in .playwright-mcp/ for the skeptical reviewer.
//
// Run after a build: node --test e2e/claude-signin.spec.mjs
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
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-claude-signin-e2e-'))
  const emptyClaudeDir = mkdtempSync(path.join(tmpdir(), 'omi-empty-claude-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_E2E_FAKE_AUTH: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      // Signed-out for Claude Code: the real authStatus IPC reads this dir.
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
  await new Promise((r) => setTimeout(r, 300))
}

describe('claude code sign-in + omi pro upsell', () => {
  test('signed-out row + upsell sheet screenshots for the skeptical review', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    await openAgents(page)

    // Signed out → the built-in Claude Code row offers "Sign in to Claude"
    // (no misleading Test/Connected).
    const signIn = page.getByRole('button', { name: 'Sign in to Claude' })
    await signIn.waitFor({ state: 'visible', timeout: 8000 })
    await page.screenshot({ path: path.join(shotsDir, 'claude-signin-signedout.png') })
    // No handshake "Test" button on the Claude Code row while signed out (a real
    // button, not the word "test" in the intro copy / other hidden panels).
    assert.equal(
      await page.getByRole('button', { name: 'Test', exact: true }).count(),
      0,
      'no Test button while signed out'
    )

    // Click Sign in → the "Upgrade to Omi Pro" upsell sheet appears (browser
    // launch is suppressed under OMI_E2E).
    await signIn.click()
    const dialog = page.getByRole('dialog')
    await dialog.waitFor({ state: 'visible', timeout: 8000 })
    await dialog
      .getByText('Unlock Omi Pro for $199/month')
      .waitFor({ state: 'visible', timeout: 8000 })
    assert.ok(
      (await dialog.getByRole('button', { name: 'Upgrade to Omi Pro' }).count()) >= 1,
      'sheet has the Upgrade CTA'
    )
    assert.ok(
      (await dialog.getByRole('button', { name: 'Cancel' }).count()) >= 1,
      'sheet has Cancel'
    )
    await new Promise((r) => setTimeout(r, 400)) // modal enter transition settle
    await page.screenshot({ path: path.join(shotsDir, 'claude-signin-upsell-sheet.png') })

    // Cancel dismisses the sheet.
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await dialog.waitFor({ state: 'hidden', timeout: 8000 })
  })
})
