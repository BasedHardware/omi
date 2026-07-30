/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Token PULL channel E2E: proves the main<->renderer freshness-pull round-trip in
// the REAL built app (out/main/index.js) via Playwright's _electron. The unit tests
// mock the IPC boundary; this exercises the LITERAL Electron transport of the two
// new channels end to end, both sides real code:
//
//   main  webContents.send('session:tokenRequest', id)
//     -> real preload  ipcRenderer.on('session:tokenRequest')
//     -> real renderer  aiProfileHost.respondTokenPull (registered by the authed
//        shell's useAppLifetimeJobs -> startAiProfileHost)
//     -> real preload  ipcRenderer.send('session:tokenResponse', id, session)
//     -> main  ipcMain.on('session:tokenResponse')
//
// Fake auth (OMI_E2E_FAKE_AUTH) mounts the authed shell WITHOUT Firebase, so the
// responder has no real user and replies `null` — which is exactly the "no token
// available" contract (never a sign-out). The point here is that the reply ARRIVES,
// and fast: a working channel replies in tens of ms; a broken channel would hang to
// the app's 8s refresher timeout. No primary instance, no real backend.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

async function mainPage(app) {
  for (let i = 0; i < 120; i++) {
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

// Fire one main-process pull round-trip against the real renderer responder.
function pullOnce(app) {
  return app.evaluate(async ({ BrowserWindow, ipcMain }, secondary) => {
    const win = BrowserWindow.getAllWindows().find((w) => {
      const u = w.webContents.getURL()
      return u && !secondary.some((h) => u.includes(h))
    })
    if (!win) return { ok: false, reason: 'no-main-window' }
    const requestId = 987654
    const start = Date.now()
    return await new Promise((resolve) => {
      const onResp = (_e, id, session) => {
        if (id !== requestId) return
        ipcMain.removeListener('session:tokenResponse', onResp)
        clearTimeout(timer)
        resolve({ ok: true, elapsedMs: Date.now() - start, session: session ?? null })
      }
      const timer = setTimeout(() => {
        ipcMain.removeListener('session:tokenResponse', onResp)
        resolve({ ok: false, reason: 'timeout', elapsedMs: Date.now() - start })
      }, 9000)
      ipcMain.on('session:tokenResponse', onResp)
      win.webContents.send('session:tokenRequest', requestId)
    })
  }, SECONDARY_HASHES)
}

describe('Token PULL channel — main<->renderer round-trip in the real app', () => {
  test('the renderer responds to a main-process token pull (fast, non-timeout)', async (t) => {
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-tokenpull-e2e-'))
    const app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: baseEnv
    })
    t.after(async () => {
      await app.close().catch(() => {})
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    await mainPage(app)

    // The responder registers in a post-mount effect; retry a few times so a pull
    // that races ahead of registration doesn't flake the result.
    let result = { ok: false, reason: 'not-run' }
    for (let i = 0; i < 8; i++) {
      result = await pullOnce(app)
      if (result.ok) break
      await new Promise((r) => setTimeout(r, 500))
    }

    assert.ok(result.ok, `pull must round-trip, got: ${JSON.stringify(result)}`)
    // Fast reply proves the renderer actively answered (a dead channel would hang
    // to the timeout). Fake auth has no Firebase user, so the session is null.
    assert.ok(result.elapsedMs < 3000, `reply must be prompt, took ${result.elapsedMs}ms`)
    assert.equal(result.session, null, 'fake-auth (no Firebase user) replies null, not a token')
    console.log(`[token-pull-e2e] round-trip OK in ${result.elapsedMs}ms; session=null (as expected)`)
  })
})
