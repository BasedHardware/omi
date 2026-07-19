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

async function launch(extraArgs = [], extraEnv = {}) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-bar-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`, ...extraArgs],
    env: { ...baseEnv, ...extraEnv }
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
  // window keeps focus — a summoned pill must never interrupt typing.
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
  assert.equal(afterPeek.barFocusEvents, 0, 'bar fired a focus event on a summon reveal')

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

test('bar hide returns cleanly and can re-reveal', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  await barShow(app, 'peek')
  // Graceful hide: renderer slide-out (≤200ms) then requestHide; fallback 450ms.
  // The persistent window is PARKED off-screen rather than win.hide()'d (parking
  // avoids the OS window-show fade on the NEXT reveal — see window.ts), so there
  // is no window 'hide' event to observe. Assert the LOGICAL visibility instead.
  await app.evaluate(() => globalThis.__omiE2E.barHide())
  let didHide = false
  for (let i = 0; i < 20; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (!s.visible) {
      didHide = true
      break
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  assert.equal(didHide, true, 'bar should hide (park off-screen) after the slide-out')
  const again = await barShow(app, 'expanded')
  assert.equal(again.visible, true, 'bar should re-reveal after a hide')
})

// C5 regression: pressing the summon hotkey must reveal the minimal PILL, NOT
// the expanded chat panel (Chris: "hotkey tap → pill; click the pill to expand").
// Top-edge hover reveal was removed entirely, so the summon gesture is the only
// reveal path. A pill is unfocusable (peek); the expanded chat is the one
// focusable mode — asserting !focusable proves the hotkey did NOT open the chat.
test('summon hotkey reveals the pill (peek), never the expanded chat (C5)', async (t) => {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  await app.firstWindow()

  await app.evaluate(() => globalThis.__omiE2E.barEnable())
  await findBarPage(app) // ensure the bar renderer has mounted (bar:ready)
  await app.evaluate(() => globalThis.__omiE2E.barSummonFire())

  let s = null
  for (let i = 0; i < 100; i++) {
    s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) break
    await new Promise((r) => setTimeout(r, 50))
  }
  assert.ok(s && s.visible, 'summon hotkey should reveal the bar')
  assert.equal(s.focusable, false, 'summon reveals the unfocusable PILL, not the focusable chat')
  assert.equal(s.focused, false, 'the summoned pill must not steal focus')
})

// Regression for the blank-bar paint race (C11): main used to showInactive()
// the HWND BEFORE the renderer had painted the revealing frame, so the compositor
// flashed the previous un-revealed frame — a blank window on first hover. The fix
// holds the HWND hidden until the renderer acks (double-rAF) it painted the
// revealed frame. This test proves (a) the structural invariant: the show is
// DEFERRED after arming, not synchronous; and (b) the observable outcome: the
// first frame the window shows is the revealing (fade/scale-in) frame, not the
// invisible pre-reveal one.
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
  // visible. Because the show was gated on the paint ack, the reveal (a scale +
  // fade GROW from the top-center seat, opacity 0→1) is already underway — so
  // .bar-slide is fading/growing IN, never the invisible pre-reveal frame
  // (opacity 0) the pre-fix code would have shown. (The entrance no longer uses
  // an off-screen translateY(-110%); the anti-blank guarantee is stronger — the
  // pre-reveal state is simply invisible, so a first opacity > 0 proves the show
  // was gated on the revealing frame.)
  let first = null
  for (let i = 0; i < 100 && !first; i++) {
    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    if (s.visible) {
      first = await barPage.evaluate(() => {
        const el = document.querySelector('.bar-slide')
        if (!el) return { opacity: 'no-element', transform: 'no-element' }
        const cs = getComputedStyle(el)
        return { opacity: cs.opacity, transform: cs.transform }
      })
      break
    }
    await new Promise((r) => setTimeout(r, 50))
  }
  assert.ok(first, 'bar never became visible after the paint ack')
  assert.notEqual(first.opacity, 'no-element', '.bar-slide missing at reveal')
  assert.ok(
    parseFloat(first.opacity) > 0,
    `visible frame was the invisible pre-reveal state (opacity ${first.opacity}, ` +
      `transform "${first.transform}") — paint ack did not gate on the revealing frame`
  )
})

// Bug A regression: a normal mouse move onto the pill + click must expand into
// the chat/agents surface. The reported bug was the pill "not expanding": main
// left the window click-through until an async renderer mouseenter → IPC round
// trip flipped hit-testing on, so a fast click landed first and passed through.
// The fix drives interactivity from the OS cursor in main (peekTick). This test
// drives the REAL built app: reveal the pill, locate its rect, move+click it,
// and assert the bar expanded (focusable) with the Omi Chat + agent rows shown.
// Signed-in (OMI_E2E_FAKE_AUTH) so the expanded surface renders its real rows,
// not the signed-out prompt. Repeated to prove it is reliable, not flaky.
//
// (Note: Playwright's page.mouse dispatches via CDP, below the OS window-message
// layer that setIgnoreMouseEvents gates, so this asserts the click→expand WIRING
// + rendered surface end-to-end; the OS-cursor→interactivity race itself is
// covered deterministically by the main/bar/watchdog.test.ts unit tests.)
test('pill click expands into the chat/agents surface (Bug A)', async (t) => {
  const { app, cleanup } = await launch([], { OMI_E2E_FAKE_AUTH: '1' })
  t.after(cleanup)
  await app.firstWindow()
  // Live-desktop cursor sits outside the peek footprint; hold the pill open so
  // the retract watchdog can't hide it between reveal and click.
  await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
  const barPage = await findBarPage(app)

  for (let i = 0; i < 5; i++) {
    await barShow(app, 'peek')
    // A REAL click on the pill. Playwright's locator.click auto-waits for the
    // element to be visible + STABLE (so the slide-in animation has settled) and
    // that it receives pointer events, then dispatches a real click — far more
    // robust than a raw mouse.move+click at a rect read mid-animation.
    await barPage.locator('.bar-content[role="button"]').click()

    // Expand is async: the mode IPC flips focus in main immediately, but the
    // renderer's pill→panel morph + content render lands a beat later. Wait for
    // the expanded surface's content rather than reading once (that read raced the
    // morph). Presence of the hub's "Ask Omi" inline input AND the always-connected
    // "Claude Code" agent row proves the click reached the real chat surface.
    await barPage.waitForFunction(() => {
      const active = document.querySelector('.bar-content-active')
      if (!active) return false
      const hasInput = !!active.querySelector('textarea[placeholder*="Ask Omi"]')
      const texts = [...active.querySelectorAll('.text-sm')].map((e) =>
        (e.textContent ?? '').trim()
      )
      return hasInput && texts.includes('Claude Code')
    })

    const s = await app.evaluate(() => globalThis.__omiE2E.barState())
    assert.equal(s.focusable, true, `pill click #${i} must expand the bar (focusable)`)

    // Back to a pill for the next iteration.
    await app.evaluate(() => globalThis.__omiE2E.barHide())
    await new Promise((r) => setTimeout(r, 700))
  }
})

// Bug A live gap: a pill summoned by a HOTKEY HOLD (mode 'ptt') must expand on
// click just like a tap-summoned peek pill. The original interactivity watch was
// peek-only, so a ptt-mode pill (the one that lingers after a hold) had no watch
// arming click-to-expand. The fix runs the interactivity half of the watch in
// EVERY visible collapsed mode (peek + ptt); retract stays peek-only. This drives
// a ptt reveal + pill click and asserts it reaches the same expanded chat surface.
// (CDP click bypasses OS hit-testing; the OS-cursor path in ptt is proven by the
// barWatchPlan unit test + the real-cursor pywinauto run noted in the PR.)
test('pill click expands from a ptt-summoned pill too (Bug A live gap)', async (t) => {
  const { app, cleanup } = await launch([], { OMI_E2E_FAKE_AUTH: '1' })
  t.after(cleanup)
  await app.firstWindow()
  const barPage = await findBarPage(app)
  await barShow(app, 'ptt')
  // The ptt pill is collapsed (!expanded), so its content is clickable; a click
  // must expand into the shared chat surface (the hub's Ask-Omi input + the
  // always-on agent row).
  await barPage.locator('.bar-content[role="button"]').click()
  await barPage.waitForFunction(() => {
    const active = document.querySelector('.bar-content-active')
    if (!active) return false
    const hasInput = !!active.querySelector('textarea[placeholder*="Ask Omi"]')
    const texts = [...active.querySelectorAll('.text-sm')].map((e) => (e.textContent ?? '').trim())
    return hasInput && texts.includes('Claude Code')
  })
  const s = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.equal(s.focusable, true, 'a ptt-summoned pill must expand on click (focusable)')
})

// Hub inline-input regression (fix/win-hub-inline-input): clicking/focusing the
// hub's "Ask Omi anything" input must NOT navigate — the surface only flips to the
// conversation on SEND (macOS AskAIInputView: .mainInput → .mainResponse on send).
// Drives the REAL built app (signed-in fake auth) end-to-end: expand the bar,
// confirm the hub hosts the inline input, focus+click it and assert we stay on the
// hub (no back chevron), then type + Enter and assert the conversation opens (the
// back chevron appears). The view flip is a renderer transition, independent of the
// backend, so it is deterministic under fake auth with no network.
test('hub Ask-Omi input: focus stays on the hub; only send opens the conversation', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const { app, cleanup } = await launch([], { OMI_E2E_FAKE_AUTH: '1' })
  t.after(cleanup)
  await app.firstWindow()
  await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
  const barPage = await findBarPage(app)
  await barShow(app, 'expanded')

  // The hub hosts the inline input, not a navigate-on-click row.
  const input = barPage.locator('.bar-content-active textarea[placeholder*="Ask Omi"]')
  await input.waitFor({ state: 'visible' })

  // Focusing + clicking the input must not navigate: no back chevron appears.
  await input.click()
  await barPage.evaluate(() => document.querySelector('.bar-content-active textarea')?.focus())
  await new Promise((r) => setTimeout(r, 250))
  assert.equal(
    await barPage.locator('[aria-label="Back to list"]').count(),
    0,
    'clicking/focusing the hub input must NOT open the conversation'
  )
  await barPage.screenshot({ path: path.join(shotsDir, 'bar-hub-input-idle.png') })

  // Typing + Enter sends and opens the conversation (the back chevron appears).
  await input.fill('hub input smoke test')
  await input.press('Enter')
  await barPage.locator('[aria-label="Back to list"]').waitFor({ state: 'visible' })
  const s = await app.evaluate(() => globalThis.__omiE2E.barState())
  assert.equal(s.focusable, true, 'the conversation surface stays focusable for typing')
  await barPage.screenshot({ path: path.join(shotsDir, 'bar-hub-input-conversation.png') })
})

// Skeptical-review screenshot of the expanded surface WITH the agent rows
// (signed-in so the real rows render, not the sign-in prompt).
test('bar expanded agents-surface screenshot (signed-in)', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const { app, cleanup } = await launch([], { OMI_E2E_FAKE_AUTH: '1' })
  t.after(cleanup)
  await app.firstWindow()
  await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
  const barPage = await findBarPage(app)
  await barShow(app, 'expanded')
  await new Promise((r) => setTimeout(r, 900)) // morph + content dissolve + agent list
  await barPage.screenshot({ path: path.join(shotsDir, 'bar-expanded-agents.png') })
})

// Bug C: the collapsed pill shows "Listening" while the orb is in its listening
// pose (always-on mic live), and the resting "Omi" wordmark otherwise. Drives a
// REAL listening state: signed-in (fake auth) + the continuousRecording pref
// flipped on via the bar's own localStorage prefs channel — no test-only render
// hook. Asserts the label flips Omi→Listening and captures the pill for review.
test('pill shows the Listening label in the listening pose (Bug C)', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const { app, cleanup } = await launch([], { OMI_E2E_FAKE_AUTH: '1' })
  t.after(cleanup)
  await app.firstWindow()
  await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
  const barPage = await findBarPage(app)
  await barShow(app, 'peek')

  const labelText = () =>
    barPage.evaluate(() => document.querySelector('.bar-pill-label')?.textContent ?? null)

  // Resting pill: the "Omi" wordmark (continuous recording off).
  await barPage.waitForFunction(
    () => document.querySelector('.bar-pill-label')?.textContent === 'Omi'
  )
  assert.equal(await labelText(), 'Omi', 'resting pill should show the Omi wordmark')

  // Flip always-on mic ON through the real preferences channel (the bar listens
  // for the cross-window `storage` event and re-derives the orb pose).
  await barPage.evaluate(() => {
    const KEY = 'omi-windows-prefs-v1'
    const prefs = JSON.parse(localStorage.getItem(KEY) || '{}')
    prefs.continuousRecording = true
    localStorage.setItem(KEY, JSON.stringify(prefs))
    window.dispatchEvent(
      new StorageEvent('storage', { key: KEY, newValue: localStorage.getItem(KEY) })
    )
  })

  await barPage.waitForFunction(
    () => document.querySelector('.bar-pill-label')?.textContent === 'Listening'
  )
  assert.equal(await labelText(), 'Listening', 'listening pose should show the Listening label')
  await new Promise((r) => setTimeout(r, 400)) // let the orb settle for the shot
  await barPage.screenshot({ path: path.join(shotsDir, 'bar-peek-listening.png') })
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
