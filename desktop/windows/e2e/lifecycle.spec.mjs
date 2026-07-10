// Lifecycle E2E: drives the REAL built app (out/main/index.js) via Playwright's
// _electron and asserts main-process lifecycle facts. Hermetic — no network is
// required; the renderer's Firebase errors are irrelevant because every
// assertion is about the main process. Each launch gets its own throwaway
// --user-data-dir so it never touches real profile data.
//
// Build first, then run: `pnpm test:e2e:lifecycle` (scripts/run-lifecycle-e2e.mjs).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import electronPath from 'electron'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

function tempUserDataDir() {
  return mkdtempSync(path.join(tmpdir(), 'omi-e2e-'))
}

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_AUTOMATION: '0', // don't spawn the automation helper in the harness
  OMI_SKIP_TUNNEL: '1'
}

async function launch(userDataDir, extraArgs = []) {
  return electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`, ...extraArgs],
    env: baseEnv
  })
}

test('single instance, tray, close-hides-to-tray, and app:quit really quits', async (t) => {
  const dir = tempUserDataDir()
  const app = await launch(dir)
  t.after(async () => {
    // If an assertion failed before app:quit ran, don't leak the instance.
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
  })

  // Wait until the main window exists (createWindow ran).
  await app.firstWindow()

  // (b) A REAL tray exists after ready (the hook calls into the tray module).
  const trayCreated = await app.evaluate(() => {
    const hook = globalThis.__omiE2E
    return !!(hook && typeof hook.trayCreated === 'function' && hook.trayCreated())
  })
  assert.equal(trayCreated, true, 'tray should be created after ready')

  // (a) Single instance: a second launch sharing the same user-data-dir must exit
  // quickly (it lost the lock) while THIS app stays alive.
  const second = spawn(electronPath, [mainEntry, `--user-data-dir=${dir}`], {
    env: baseEnv,
    stdio: 'ignore'
  })
  const secondExit = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve('timeout'), 15000)
    second.on('exit', (code) => {
      clearTimeout(timer)
      resolve(code ?? 0)
    })
  })
  assert.notEqual(secondExit, 'timeout', 'second instance should exit, not linger')
  // First app is still alive (has windows).
  assert.ok((await app.windows()).length >= 1, 'first instance should still be alive')

  // (c) Closing the MAIN window hides it (does NOT quit, does NOT destroy).
  // Target it by id from the E2E hook — getAllWindows() also returns the insight
  // toast window, whose close is NOT intercepted (that one really destroys).
  const afterClose = await app.evaluate(async ({ BrowserWindow }) => {
    const hook = globalThis.__omiE2E
    const win = BrowserWindow.fromId(hook.mainWindowId)
    win.close()
    // Give the synchronous 'close' handler a tick.
    await new Promise((r) => setTimeout(r, 200))
    return {
      destroyed: win.isDestroyed(),
      visible: win.isDestroyed() ? false : win.isVisible(),
      windowCount: BrowserWindow.getAllWindows().length
    }
  })
  assert.equal(afterClose.destroyed, false, 'close should not destroy the window')
  assert.equal(afterClose.visible, false, 'close should hide the window')
  assert.ok(afterClose.windowCount >= 1, 'window should still exist after close')

  // App did not quit — still responsive.
  const stillAlive = await app.evaluate(({ app }) => app.isReady())
  assert.equal(stillAlive, true, 'app should still be running after close-to-tray')

  // (d) The app:quit IPC path quits for real. Emit the same channel the renderer
  // uses; the handler flips isQuitting and calls app.quit().
  const closed = new Promise((resolve) => app.on('close', () => resolve('closed')))
  await app.evaluate(({ ipcMain }) => ipcMain.emit('app:quit'))
  const result = await Promise.race([
    closed,
    new Promise((resolve) => setTimeout(() => resolve('timeout'), 15000))
  ])
  assert.equal(result, 'closed', 'app:quit should terminate the app')
})

test('--hidden start creates the window but does not show it', async (t) => {
  const dir = tempUserDataDir()
  const app = await launch(dir, ['--hidden'])
  t.after(async () => {
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
  })

  // The window exists (created) but is hidden (tray-only start).
  const state = await app.evaluate(async ({ BrowserWindow }) => {
    // Wait for the window to be created.
    for (let i = 0; i < 50 && BrowserWindow.getAllWindows().length === 0; i++) {
      await new Promise((r) => setTimeout(r, 100))
    }
    const win = BrowserWindow.getAllWindows()[0]
    return { exists: !!win, visible: win ? win.isVisible() : false }
  })
  assert.equal(state.exists, true, '--hidden should still create the main window')
  assert.equal(state.visible, false, '--hidden should not show the main window')
})
