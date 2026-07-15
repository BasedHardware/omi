/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
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
import { mkdtempSync, rmSync, readFileSync } from 'node:fs'
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

test('crash sentinel: clean quit writes clean, next boot reads it (no false crash), and a forced-dirty flag is detected', async (t) => {
  const dir = tempUserDataDir()
  const sentinelPath = path.join(dir, 'clean-exit-sentinel.json')
  t.after(() => {
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  })

  // --- Boot 1: fresh profile (no sentinel) --------------------------------
  const app1 = await launch(dir)
  await app1.firstWindow()
  // First launch ever: no prior sentinel → NOT reported as a crash.
  const crashed1 = await app1.evaluate(() => globalThis.__omiE2E.crashDetectedOnBoot())
  assert.equal(crashed1, false, 'first launch (no sentinel) must not be flagged as a crash')
  // Boot marked this session dirty/running.
  assert.equal(
    JSON.parse(readFileSync(sentinelPath, 'utf-8')).cleanExit,
    false,
    'boot should mark the session dirty (cleanExit=false)'
  )
  // Clean quit → will-quit writes cleanExit=true.
  const closed1 = new Promise((resolve) => app1.on('close', () => resolve('closed')))
  await app1.evaluate(({ ipcMain }) => ipcMain.emit('app:quit'))
  await Promise.race([closed1, new Promise((r) => setTimeout(() => r('timeout'), 15000))])
  assert.equal(
    JSON.parse(readFileSync(sentinelPath, 'utf-8')).cleanExit,
    true,
    'clean quit should mark cleanExit=true'
  )

  // --- Boot 2: same profile, previous exit was clean ----------------------
  const app2 = await launch(dir)
  await app2.firstWindow()
  const crashed2 = await app2.evaluate(() => globalThis.__omiE2E.crashDetectedOnBoot())
  assert.equal(crashed2, false, 'a clean previous exit must not be flagged as a crash on next boot')
  const closed2 = new Promise((resolve) => app2.on('close', () => resolve('closed')))
  await app2.evaluate(({ ipcMain }) => ipcMain.emit('app:quit'))
  await Promise.race([closed2, new Promise((r) => setTimeout(() => r('timeout'), 15000))])

  // --- Boot 3: simulate a crash by leaving the flag dirty -----------------
  // A real crash never reaches will-quit; emulate that end state by forcing the
  // sentinel dirty on disk, then boot and assert detection fires.
  const { writeFileSync } = await import('node:fs')
  writeFileSync(sentinelPath, JSON.stringify({ cleanExit: false }), 'utf-8')
  const app3 = await launch(dir)
  await app3.firstWindow()
  const crashed3 = await app3.evaluate(() => globalThis.__omiE2E.crashDetectedOnBoot())
  assert.equal(crashed3, true, 'a dirty sentinel from a prior crash must be detected on boot')
  const closed3 = new Promise((resolve) => app3.on('close', () => resolve('closed')))
  await app3.evaluate(({ ipcMain }) => ipcMain.emit('app:quit'))
  await Promise.race([closed3, new Promise((r) => setTimeout(() => r('timeout'), 15000))])
})

test('hidden title bar: overlay chrome + maximize/restore keeps sane bounds', async (t) => {
  // Regression guard for the known Electron path where titleBarStyle:'hidden'
  // + backgroundMaterial breaks maximize/restore geometry. Runs on the real
  // built app, so it exercises whatever material gating createWindow chose
  // for this machine.
  const dir = tempUserDataDir()
  const app = await launch(dir)
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

  await app.firstWindow()
  const result = await app.evaluate(async ({ BrowserWindow }) => {
    const hook = globalThis.__omiE2E
    const win = BrowserWindow.fromId(hook.mainWindowId)
    const before = win.getBounds()
    const minSize = win.getMinimumSize()
    win.maximize()
    await new Promise((r) => setTimeout(r, 400))
    const maximized = win.isMaximized()
    const maxBounds = win.getBounds()
    win.unmaximize()
    await new Promise((r) => setTimeout(r, 400))
    const after = win.getBounds()
    return { before, minSize, maximized, maxBounds, after, restored: !win.isMaximized() }
  })

  assert.equal(result.maximized, true, 'window should maximize')
  assert.ok(
    result.maxBounds.width > result.before.width,
    'maximized bounds should grow beyond the default window'
  )
  assert.equal(result.restored, true, 'window should restore from maximized')
  assert.ok(
    Math.abs(result.after.width - result.before.width) <= 2 &&
      Math.abs(result.after.height - result.before.height) <= 2,
    `restore should return to the original size (was ${JSON.stringify(result.before)}, got ${JSON.stringify(result.after)})`
  )
  // Windows-11 polish contract: the narrow-snap floor.
  assert.equal(result.minSize[0], 500, 'min width should be 500 (narrow snap support)')
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
