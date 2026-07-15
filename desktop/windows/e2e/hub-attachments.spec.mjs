/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Hub attachments E2E (Track 5): drives the REAL built app (out/main/index.js) via
// Playwright's _electron and exercises the ask-bar paperclip/attachment UI against
// the real renderer — real drag-drop (browser File + DataTransfer → File.arrayBuffer
// → addAttachments), real chip rendering, real remove, real 4-file cap, and the
// attachment-only Send affordance. Hermetic: OMI_E2E_FAKE_AUTH boots an offline
// authed shell; the /v2/files upload is route-stubbed so chips reach 'uploaded'
// without a backend. The native file picker is intentionally NOT clicked (it would
// block on a native dialog) — drag-drop exercises the same addAttachments path.
// Screenshots land in .playwright-mcp/ for the skeptical reviewer.
//
// Run after a build: node --test e2e/hub-attachments.spec.mjs
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
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-attach-e2e-'))
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

// Dispatch a real drag-drop of N synthetic image files onto the ask bar. This is
// the actual production drop path: DataTransfer → onDrop → filesToPickedChatFiles
// (File.arrayBuffer) → addAttachments.
async function dropFiles(page, names) {
  await page.evaluate((fileNames) => {
    const bar = document.querySelector('[data-testid="hub-ask-bar"]')
    if (!bar) throw new Error('ask bar not found')
    const dt = new DataTransfer()
    for (const name of fileNames) {
      dt.items.add(new File([new Uint8Array([1, 2, 3, 4, 5])], name, { type: 'image/png' }))
    }
    bar.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, names)
}

const chipCount = (page) =>
  page.evaluate(
    () => document.querySelector('[data-testid="hub-attachment-chips"]')?.childElementCount ?? 0
  )

describe('Hub attachments', () => {
  test('paperclip, drag-drop chips, remove, cap, and attachment-only Send', async () => {
    const { app, cleanup } = await launch()
    try {
      const page = await mainPage(app)

      // Stub the upload so chips settle to 'uploaded' without a backend.
      await page.route('**/v2/files', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'stub-file-id', name: 'photo.png', mime_type: 'image/png' }])
        })
      )

      // Land on the Hub home and wait for the ask bar + its paperclip.
      await page.evaluate(() => {
        window.location.hash = '#/home'
      })
      await page.waitForSelector('[aria-label="Ask omi anything"]', { timeout: 15000 })
      const clip = await page.waitForSelector('[aria-label="Attach files"]', { timeout: 15000 })
      assert.ok(clip, 'paperclip renders in the resting hub')
      await page.screenshot({ path: path.join(shotsDir, 'hub-attach-01-resting.png') })

      // Drag-drop two files → two chips, upload settles to uploaded, Send appears.
      await dropFiles(page, ['photo.png', 'notes.pdf'])
      await page.waitForFunction(
        () =>
          (document.querySelector('[data-testid="hub-attachment-chips"]')?.childElementCount ?? 0) === 2,
        undefined,
        { timeout: 10000 }
      )
      await page.waitForSelector('[aria-label="Send"]', { timeout: 10000 })
      const connectGone = await page.evaluate(
        () => !document.querySelector('button[aria-pressed]')?.textContent?.includes('Connect')
      )
      assert.equal(await chipCount(page), 2, 'two chips staged')
      assert.ok(connectGone, 'Connect is replaced by Send once files are staged')
      // give the stubbed upload a beat to flip the chip out of the spinner state
      await new Promise((r) => setTimeout(r, 500))
      await page.screenshot({ path: path.join(shotsDir, 'hub-attach-02-two-chips.png') })

      // Remove one chip → one remains.
      await page.click('[aria-label="Remove notes.pdf"]')
      await page.waitForFunction(
        () =>
          (document.querySelector('[data-testid="hub-attachment-chips"]')?.childElementCount ?? 0) === 1,
        undefined,
        { timeout: 10000 }
      )
      assert.equal(await chipCount(page), 1, 'one chip after remove')
      await page.screenshot({ path: path.join(shotsDir, 'hub-attach-03-after-remove.png') })

      // Stage up to the 4-file cap → paperclip disables.
      await dropFiles(page, ['a.png', 'b.png', 'c.png'])
      await page.waitForFunction(
        () =>
          (document.querySelector('[data-testid="hub-attachment-chips"]')?.childElementCount ?? 0) === 4,
        undefined,
        { timeout: 10000 }
      )
      const capDisabled = await page.evaluate(() => {
        const btn = document.querySelector('[aria-label^="Attachment limit reached"]')
        return !!btn && btn.disabled === true
      })
      assert.ok(capDisabled, 'paperclip is disabled at the 4-file cap')
      await page.screenshot({ path: path.join(shotsDir, 'hub-attach-04-cap-disabled.png') })
    } finally {
      await cleanup()
    }
  })
})
