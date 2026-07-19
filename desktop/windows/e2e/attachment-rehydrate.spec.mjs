/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Attachment rehydrate-after-reload E2E: the reload half of the attachment story
// that hub-attachments.spec.mjs (send-path staging) does NOT cover. Drives the REAL
// built app (out/main/index.js) via Playwright's _electron: seeds a files-only chat
// message into the DEFAULT thread's local conversation through the REAL db IPC
// (window.omi.insertLocalConversation → SQLite), RELOADS the window, and asserts the
// mount loader rehydrates the attachment and the shared ChatMessages renders the
// name+mime card — never an empty "You" bubble (the C/D/E sweep regression).
//
// Hermetic: OMI_E2E_FAKE_AUTH boots an offline authed shell; no backend is touched
// (the seed writes straight to the local conversation the mount loader reads back).
//
// Run after a build: node --test e2e/attachment-rehydrate.spec.mjs
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

// The default shared thread's local-conversation id key (renderer chatStorageKeys.ts).
const CHAT_INFINITE_ID_KEY = 'omi-chat-infinite-id'
const SEED_ID = 'chat-e2e-attach-rehydrate'

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-attach-rehydrate-e2e-'))
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

describe('Attachment rehydrate after reload', () => {
  test('a files-only message survives reload as a name+mime card, not an empty bubble', async () => {
    const { app, cleanup } = await launch()
    try {
      let page = await mainPage(app)
      await page.evaluate(() => {
        window.location.hash = '#/home'
      })
      await page.waitForSelector('[aria-label="Ask omi anything"]', { timeout: 20000 })

      // Seed the DEFAULT thread's local conversation with a files-only image message
      // AND a files-only PDF message (the exact C/D/E fixtures: attachments present,
      // NO thumbnailUrl — the real post-upload shape for files with no thumbnail),
      // through the REAL db IPC that getLocalConversation reads back on mount.
      await page.evaluate(
        async ({ key, id }) => {
          window.localStorage.setItem(key, id)
          const now = Date.now()
          const messages = [
            {
              id: 'seed-img',
              role: 'user',
              content: '',
              attachments: [{ id: 'file-img', name: 'test-cde-image.png', mimeType: 'image/png' }]
            },
            {
              id: 'seed-pdf',
              role: 'user',
              content: '',
              attachments: [
                { id: 'file-pdf', name: 'test-cde-doc.pdf', mimeType: 'application/pdf' }
              ]
            },
            { id: 'seed-reply', role: 'assistant', content: 'Got your files.' }
          ]
          await window.omi.insertLocalConversation({
            id,
            startedAt: now,
            endedAt: now,
            transcript: 'You: \n\nOmi: Got your files.',
            createdAt: now,
            kind: 'chat',
            messages
          })
        },
        { key: CHAT_INFINITE_ID_KEY, id: SEED_ID }
      )

      // RELOAD — remounts useChat, which reads the infinite id from localStorage and
      // rehydrates the seeded conversation via getLocalConversation (the bug's path).
      await page.reload()
      page = await mainPage(app)
      await page.evaluate(() => {
        window.location.hash = '#/home'
      })
      await page.waitForSelector('[aria-label="Ask omi anything"]', { timeout: 20000 })

      // Focus the ask bar → hubStage 'askFocused' → chat panel renders the thread.
      await page.click('[aria-label="Ask omi anything"]')
      // Wait for the rehydrated thread to paint the assistant reply (proves history
      // loaded), then assert on the attachment cards.
      await page.waitForFunction(() => document.body.textContent?.includes('Got your files.'), {
        timeout: 15000
      })

      const result = await page.evaluate(() => {
        const has = (t) => document.body.textContent?.includes(t) ?? false
        // Empty user bubble = a `.whitespace-pre-wrap` node with no trimmed text
        // (ChatMessages renders that ONLY for a user message that reached the bubble
        // branch — which a files-only message must never do).
        const emptyBubbles = [...document.querySelectorAll('.whitespace-pre-wrap')].filter(
          (el) => (el.textContent ?? '').trim().length === 0
        ).length
        return {
          pdfName: has('test-cde-doc.pdf'),
          pdfMime: has('application/pdf'),
          imgName: has('test-cde-image.png'),
          emptyBubbles
        }
      })
      await page.screenshot({ path: path.join(shotsDir, 'attach-rehydrate-thread.png') })

      assert.ok(result.pdfName, 'PDF filename card survived reload')
      assert.ok(result.pdfMime, 'PDF mime subtitle survived reload')
      assert.ok(result.imgName, 'image filename card survived reload')
      assert.equal(result.emptyBubbles, 0, 'no empty "You" bubble for a files-only message')
    } finally {
      await cleanup()
    }
  })
})
