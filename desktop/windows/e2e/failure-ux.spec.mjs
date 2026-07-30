/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Failure-UX E2E: boots the REAL built app (out/main/index.js) with the fake-auth
// authed shell and proves the two new main->renderer surfaces work end to end
// through the REAL preload bridge + real components — the wiring the jsdom unit
// tests mock away (they stub window.omi; here it is the real contextBridge).
//
// Covers:
//   1. The preload exposes the new bridge methods, and backend:degradedState
//      round-trips through the real main IPC handler (registerBackendDegradedIpc).
//   2. A backend:degraded broadcast makes the DegradedModeNotice banner appear and
//      a recovery broadcast clears it (bug 2's UI half).
//   3. A tasks:opFailed broadcast makes the (now-mounted) ToastHost show a toast
//      (bug 1's failure signal + the ToastHost mount).
//
// The main-side detection logic (429-storm tracker, tombstone/verify) is proven by
// the hermetic unit tests; this exercises the built-bundle IPC + render path.
//
// Build first, then run: `node --test e2e/failure-ux.spec.mjs` (or pnpm test:e2e:failure-ux).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { mkdtempSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1', // mounts the authed shell (where the notices live) without Firebase
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

// Fire an IPC event to every window from the MAIN process, exactly as the app's own
// broadcasts do (broadcastToAllWindows / emitTaskOpFailed).
async function broadcast(app, channel, payload) {
  await app.evaluate(
    ({ BrowserWindow }, { channel, payload }) => {
      for (const w of BrowserWindow.getAllWindows()) {
        if (!w.isDestroyed()) w.webContents.send(channel, payload)
      }
    },
    { channel, payload }
  )
}

// Broadcast, resending each poll until the page reaches `predicate`. ipcRenderer.on
// isn't buffered, so a single send can race a renderer subscription that is still
// mounting; resending removes that test-only race (production covers a mount-during-
// storm via the backendDegradedState() pull instead).
async function broadcastUntil(app, channel, payload, page, predicate, label) {
  for (let i = 0; i < 50; i++) {
    await broadcast(app, channel, payload)
    const ok = await page.evaluate(predicate).catch(() => false)
    if (ok) return
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(`timed out waiting for: ${label}`)
}

test('the new failure-UX bridge surfaces work end-to-end in the built app', async (t) => {
  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-failureux-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: baseEnv
  })
  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  })

  const page = await mainPage(app)

  // (1) The real preload exposes the new methods, and the pull channel round-trips
  //     through the real main handler.
  const shape = await page.evaluate(() => ({
    onBackendDegraded: typeof window.omi.onBackendDegraded,
    backendDegradedState: typeof window.omi.backendDegradedState,
    onTasksOpFailed: typeof window.omi.onTasksOpFailed
  }))
  assert.equal(shape.onBackendDegraded, 'function', 'preload should expose onBackendDegraded')
  assert.equal(shape.backendDegradedState, 'function', 'preload should expose backendDegradedState')
  assert.equal(shape.onTasksOpFailed, 'function', 'preload should expose onTasksOpFailed')

  const initial = await page.evaluate(() => window.omi.backendDegradedState())
  assert.equal(initial, false, 'backendDegradedState should round-trip and start healthy')

  // (2) Degraded banner: not present healthy, appears on the broadcast, clears on recovery.
  assert.equal(
    await page.evaluate(() => document.body.innerText.includes('Omi is catching up')),
    false,
    'the degraded banner must not show while healthy'
  )
  await broadcastUntil(
    app,
    'backend:degraded',
    true,
    page,
    () =>
      document.body.innerText.includes('Omi is catching up') &&
      document.body.innerText.includes('Syncing will resume automatically'),
    'degraded banner to appear'
  )
  await broadcast(app, 'backend:degraded', false)
  await page.waitForFunction(() => !document.body.innerText.includes('Omi is catching up'), null, {
    timeout: 5000
  })

  // (3) Task failure toast: the tasks:opFailed signal surfaces through the now-mounted
  //     ToastHost (previously mounted nowhere → this message would have been silent).
  const MSG = 'Could not delete task — it has been restored.'
  await broadcastUntil(
    app,
    'tasks:opFailed',
    { op: 'delete', message: MSG },
    page,
    () => document.body.innerText.includes('Could not delete task'),
    'delete-failure toast to appear'
  )

  await app.close()
})
