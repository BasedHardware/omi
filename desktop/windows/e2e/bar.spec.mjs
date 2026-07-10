/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Bar E2E: drives the REAL built app (out/main/index.js) via Playwright's
// _electron and asserts the bar's focus contract + reveal machinery. Hermetic —
// no network needed (assertions are main-process facts; the bar renderer only
// needs Firebase to resolve a null user from empty persistence). Each launch
// gets its own throwaway --user-data-dir.
//
// Build first, then run: `pnpm test:e2e:bar` (scripts/run-bar-e2e.mjs).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.orb-out', 'bar-shots')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

async function launch(extraArgs = []) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-bar-e2e-'))
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

/** Wait until the bar renderer reports ready and a show settles. */
async function barShow(app, mode) {
  await app.evaluate(({ ipcMain: _i }, m) => {
    globalThis.__omiE2E.barShow(m)
  }, mode)
  // The first show defers until the renderer mounts (bar:ready); poll.
  for (let i = 0; i < 100; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) return s
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(`bar never became visible in mode ${mode}`)
}

test('bar focus contract: peek/ptt never take or steal focus; expanded does', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  // Instrument BEFORE any reveal: count focus events on the bar window and
  // remember which window is focused now (the main window).
  await app.evaluate(({ BrowserWindow }) => {
    globalThis.__barFocusEvents = 0
    const before = BrowserWindow.getFocusedWindow()
    globalThis.__focusedBefore = before ? before.id : null
    // The bar window may not exist yet; hook it when it appears.
    const hook = (win) => {
      win.on('focus', () => {
        if (globalThis.__omiE2E.barState().id === win.id) globalThis.__barFocusEvents++
      })
    }
    BrowserWindow.getAllWindows().forEach(hook)
    require('electron').app.on('browser-window-created', (_e, w) => hook(w))
  })

  // (a) PEEK: revealed inactive, unfocusable, and the previously-focused
  // window keeps focus — a hover reveal must never interrupt typing.
  const peek = await barShow(app, 'peek')
  assert.equal(peek.visible, true, 'peek should reveal the bar')
  assert.equal(peek.focusable, false, 'peek bar must be unfocusable')
  assert.equal(peek.focused, false, 'peek bar must not be focused')
  const afterPeek = await app.evaluate(({ BrowserWindow }) => ({
    focusedNow: BrowserWindow.getFocusedWindow() ? BrowserWindow.getFocusedWindow().id : null,
    barFocusEvents: globalThis.__barFocusEvents,
    barId: globalThis.__omiE2E.barState().id
  }))
  assert.notEqual(afterPeek.focusedNow, afterPeek.barId, 'peek must not move focus to the bar')
  assert.equal(afterPeek.barFocusEvents, 0, 'bar fired a focus event on a hover reveal')

  // Keystrokes still land in the main window: sanity that the OS-focused
  // window is unchanged from before the reveal (typing keeps flowing there).
  assert.equal(
    afterPeek.focusedNow,
    await app.evaluate(() => globalThis.__focusedBefore),
    'focused window changed across a peek reveal'
  )

  // (b) PTT mode: same contract — expanded listening WITHOUT focus.
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  await new Promise((r) => setTimeout(r, 600))
  const ptt = await barShow(app, 'ptt')
  assert.equal(ptt.focusable, false, 'ptt bar must be unfocusable')
  assert.equal(ptt.focused, false, 'ptt bar must not be focused')

  // (c) EXPANDED (hotkey tap / pill click): the one mode that takes focus.
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  await new Promise((r) => setTimeout(r, 600))
  const expanded = await barShow(app, 'expanded')
  assert.equal(expanded.focusable, true, 'expanded bar must be focusable (chat typing)')
})

test('bar hide returns cleanly and can re-reveal; strips exist per display', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  await barShow(app, 'peek')
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  // Graceful hide: renderer slide-out (≤200ms) then requestHide; fallback 450ms.
  await new Promise((r) => setTimeout(r, 800))
  const hidden = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.equal(hidden.visible, false, 'bar should hide after the slide-out')
  const again = await barShow(app, 'expanded')
  assert.equal(again.visible, true, 'bar should re-reveal after a hide')

  // Trigger strips: one 1px window at the top of every display (they exist
  // even while the bar is hidden — that IS the zero-poll reveal path).
  const strips = await app.evaluate(({ BrowserWindow, screen }) => {
    const displays = screen.getAllDisplays()
    const oneByOne = BrowserWindow.getAllWindows().filter((w) => w.getBounds().height === 1)
    return { displays: displays.length, strips: oneByOne.length }
  })
  assert.equal(strips.strips, strips.displays, 'one trigger strip per display')
})

test('bar screenshots (collapsed / expanded) for the skeptical review', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  for (const [suffix, args] of [
    ['100', []],
    ['150', ['--force-device-scale-factor=1.5']]
  ]) {
    const { app, cleanup } = await launch(args)
    t.after(cleanup)
    await app.firstWindow()
    await barShow(app, 'peek')
    // The bar page is the window whose URL hash is #/bar.
    let barPage = null
    for (let i = 0; i < 50 && !barPage; i++) {
      barPage = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
      if (!barPage) await new Promise((r) => setTimeout(r, 100))
    }
    assert.ok(barPage, 'bar page not found')
    await new Promise((r) => setTimeout(r, 700)) // let the slide-in + genesis settle
    await barPage.screenshot({ path: path.join(shotsDir, `bar-peek-${suffix}.png`) })
    await app.evaluate(() => globalThis.__omiE2E.barShow('expanded'))
    await new Promise((r) => setTimeout(r, 900)) // morph + content dissolve
    await barPage.screenshot({ path: path.join(shotsDir, `bar-expanded-${suffix}.png`) })
    await cleanup()
  }
})
