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
  await app.evaluate((_electron, m) => {
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

/** The bar renderer's window is the one whose URL hash is #/bar. */
async function findBarPage(app) {
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
    if (page) return page
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('bar page (#/bar) not found')
}

/** Pull translateY (px) out of a computed `transform` matrix string. */
function translateYpx(transform) {
  if (!transform || transform === 'none') return 0
  const m = transform.match(/matrix(3d)?\(([^)]+)\)/)
  if (!m) return 0
  const parts = m[2].split(',').map((v) => parseFloat(v.trim()))
  return m[1] ? parts[13] : parts[5] // matrix3d ty@13, matrix ty@5
}

test('bar focus contract: peek/ptt never take or steal focus; expanded does', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  // Instrument BEFORE any reveal: count focus events on the bar window and
  // remember which window is focused now (the main window).
  await app.evaluate(({ BrowserWindow, app: electronApp }) => {
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
    electronApp.on('browser-window-created', (_e, w) => hook(w))
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
  // The load-bearing focus assertions: the bar itself never became the
  // focused window and never even received a focus event. (We deliberately do
  // NOT assert which window IS focused — this runs on a live desktop where
  // the user's own focus changes are environment noise, and getFocusedWindow
  // only reports this app's windows anyway.)
  assert.notEqual(afterPeek.focusedNow, afterPeek.barId, 'peek must not move focus to the bar')
  assert.equal(afterPeek.barFocusEvents, 0, 'bar fired a focus event on a hover reveal')

  // (b) PTT mode: same contract — expanded listening WITHOUT focus.
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  await new Promise((r) => setTimeout(r, 600))
  const ptt = await barShow(app, 'ptt')
  assert.equal(ptt.focusable, false, 'ptt bar must be unfocusable')
  assert.equal(ptt.focused, false, 'ptt bar must not be focused')

  // (c) EXPANDED (hotkey tap / pill click): the one mode that takes focus —
  // but its window must STILL be click-through outside the visible surface
  // (merge-blocker regression: a solid expanded window blocked clicks on
  // everything under the invisible dead space around the panel).
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  await new Promise((r) => setTimeout(r, 600))
  const expanded = await barShow(app, 'expanded')
  assert.equal(expanded.focusable, true, 'expanded bar must be focusable (chat typing)')
  assert.equal(
    expanded.interactive,
    false,
    'expanded bar must present CLICK-THROUGH — hit-testing only enables under the cursor'
  )
})

test('bar hide returns cleanly and can re-reveal; strips exist per display', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  await barShow(app, 'peek')
  // Graceful hide: renderer slide-out (≤200ms) then requestHide; fallback
  // 450ms. Observe the window's 'hide' EVENT rather than polling visibility —
  // on a live desktop the user's cursor can cross the top edge and legitimately
  // re-reveal the bar via a trigger strip right after the hide.
  const didHide = await app.evaluate(({ BrowserWindow }) => {
    return new Promise((resolve) => {
      const win = BrowserWindow.fromId(globalThis.__omiE2E.barState().id)
      win.once('hide', () => resolve(true))
      globalThis.__omiE2E.barHide()
      setTimeout(() => resolve(false), 1500)
    })
  })
  assert.equal(didHide, true, 'bar should hide after the slide-out (event observed)')
  const again = await barShow(app, 'expanded')
  assert.equal(again.visible, true, 'bar should re-reveal after a hide')

  // Trigger strips: one thin window per display (they exist even while the
  // bar is hidden — that IS the zero-poll reveal path), CENTERED over the
  // bar's footprint and far from the screen corners (merge-blocker
  // regression: a full-width strip hijacked ✕/minimize/tab-close targets).
  const diag = await app.evaluate(() => globalThis.__omiE2E.barStrips())
  assert.equal(diag.strips.length, diag.displays.length, 'one trigger strip per display')
  for (const s of diag.strips) {
    assert.ok(s.bounds.height <= 2, `strip ${s.id} is ${s.bounds.height}px tall (want 1px)`)
    // Find the display this strip belongs to (same y origin, x within bounds).
    const d = diag.displays.find(
      (dd) => s.bounds.x >= dd.bounds.x && s.bounds.x < dd.bounds.x + dd.bounds.width
    )
    assert.ok(d, `strip ${s.id} not on any display`)
    assert.ok(
      s.bounds.width < d.bounds.width / 2,
      `strip ${s.id} spans ${s.bounds.width}px of a ${d.bounds.width}px display — too wide`
    )
    assert.ok(
      s.bounds.x > d.bounds.x + d.bounds.width * 0.25,
      `strip ${s.id} reaches the top-left corner region`
    )
    assert.ok(
      s.bounds.x + s.bounds.width < d.bounds.x + d.bounds.width * 0.75,
      `strip ${s.id} reaches the top-right corner region`
    )
  }
})

// Regression for the blank-bar paint race (C11): main used to showInactive()
// the HWND BEFORE the renderer had painted the slide-in frame, so the compositor
// flashed the previous off-screen translateY(-110%) frame — a blank window on
// first hover. The fix holds the HWND hidden until the renderer acks (double-rAF)
// it painted the revealed frame. This test proves (a) the structural invariant:
// the show is DEFERRED after arming, not synchronous; and (b) the observable
// outcome: the first frame the window shows is the descended slide-in frame, not
// the off-screen blank one.
test('paint-ack: reveal defers the HWND show until the renderer paints slide-in', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  // Create the bar window (hidden) and locate its renderer page.
  await app.evaluate(() => globalThis.__omiE2E.barEnable())
  const barPage = await findBarPage(app)

  // Settle bar:ready so the MEASURED reveal below goes through the present path
  // (not the first-show pendingShow defer) — otherwise the structural assertion
  // is meaningless. A quick reveal+hide does this; the window is re-hidden, so
  // the next reveal still repaints slide-in from an off-screen start.
  await barShow(app, 'peek')
  await app.evaluate(
    () =>
      new Promise((resolve) => {
        globalThis.__omiE2E.barHide()
        setTimeout(resolve, 700) // > slide-out (200) + hide fallback (450)
      })
  )

  // (a) Structural invariant (the fix, proven deterministically): arming a
  // reveal must NOT show the HWND synchronously — it is deferred until the paint
  // ack. Immediately after the barShow call resolves, the bar is still hidden
  // (the ack needs a double-rAF + IPC round-trip, tens of ms away). Pre-fix,
  // showInactive() ran synchronously inside showBar, so the bar was already
  // visible here — THIS is the assertion that fails on the pre-fix code.
  await app.evaluate(() => globalThis.__omiE2E.barShow('peek'))
  const rightAfterArm = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.equal(
    rightAfterArm.visible,
    false,
    'reveal must defer the HWND show until the paint ack (pre-fix showed synchronously)'
  )

  // (b) Observable outcome: read .bar-slide the instant the window becomes
  // visible. Because the show was gated on the paint ack, the slide-in
  // transition is already underway, so the surface is descended into view —
  // never the off-screen translateY(-110%) blank the pre-fix code flashed.
  // (translateY is -110% of the ~36px pill ≈ -40px, ratio -1.1; revealed sits
  // well above.)
  let first = null
  for (let i = 0; i < 100 && !first; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) {
      first = await barPage.evaluate(() => {
        const el = document.querySelector('.bar-slide')
        return el
          ? { transform: getComputedStyle(el).transform, height: el.offsetHeight }
          : { transform: 'no-element', height: 0 }
      })
      break
    }
    await new Promise((r) => setTimeout(r, 50))
  }
  assert.ok(first, 'bar never became visible after the paint ack')
  assert.notEqual(first.transform, 'no-element', '.bar-slide missing at reveal')
  const ratio = translateYpx(first.transform) / (first.height || 36)
  assert.ok(
    ratio > -1.0,
    `visible frame was the off-screen blank (translateY ratio ${ratio.toFixed(2)}, ` +
      `transform "${first.transform}", height ${first.height})`
  )
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
    // Live-desktop capture: the cursor sits outside the peek footprint, so the
    // retract watchdog would (correctly) hide the bar mid-screenshot — hold it
    // open for the duration of the capture.
    await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
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
