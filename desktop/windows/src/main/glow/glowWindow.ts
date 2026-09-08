// The halo: ONE transparent, click-through, always-on-top window sized to the
// user's active window + a pad, drawing a single soft rounded ring.
//
// This file owns the WINDOW. It is deliberately appearance-agnostic — it draws "a
// halo around the active window" and nothing here knows why. glowGeometry.ts owns
// the arithmetic; glowPresets.ts owns what a halo means and how it looks. The
// hard-won part below is the platform recipe (DWM frame bounds, one click-through
// window, the park pattern, opacity-only animation), and it is reusable by any
// future caller that wants a ring around the active window in some other colour.
//
// ── Three things that are deliberately NOT what a first attempt would do ──────
//
// 1. ONE window, not four. Four axis-aligned edge windows (the macOS build's
//    hit-testing workaround) CANNOT form a continuous rounded ring — each band
//    owns a corner with a hard 90° edge and its own mask axis, so the corners
//    visibly don't connect. Windows doesn't need the workaround at all:
//    setIgnoreMouseEvents(true) makes a whole window click-through at the OS
//    level (it sets WS_EX_TRANSPARENT — the same recipe Teams/Loom/OBS use for
//    their capture indicators).
//
// 2. DWM extended frame bounds, NOT GetWindowRect (see nativeForeground.ts). This
//    is the fix for the stray bar the user actually saw.
//
// 3. The window is NEVER hidden or re-shown. A transparent frameless window on
//    Windows fades in via the OS show-animation on every hide→show — the defect
//    documented at length in bar/window.ts (the pill "plummeting"). Same fix:
//    show it ONCE, parked off-screen, then move it with setBounds forever. A
//    "hide" is a park; a "show" is an unpark.
import { BrowserWindow, ipcMain, screen } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { rendererBaseUrl } from '../rendererServer'
import { getAppSettings } from '../appSettings'
import { getForegroundWindowFrame } from '../usage/nativeForeground'
import {
  planGlow,
  GLOW_LIFETIME_MS,
  GLOW_FOLLOW_MS,
  type GlowPlan,
  type Rect
} from './glowGeometry'
import { GLOW_PRESETS, isGlowPreset } from './glowPresets'
import type { GlowPresetName } from '../../shared/types'

/** Far outside any physical display — the Win32 "hidden window" corner. */
const PARKED_POS = { x: -32000, y: -32000 }
/** The renderer must confirm it painted the ring before we unpark; if it is
 *  wedged, present anyway after this so a glow can never be permanently stuck. */
const PAINT_ACK_FALLBACK_MS = 150

type ActiveGlow = {
  runId: number
  preset: GlowPresetName
  /** HWND of the window we are framing — if the foreground changes, we dismiss. */
  targetHandle: string | null
  bounds: Rect
}

let glowWindow: BrowserWindow | null = null
let glowReady = false
let glowPrimed = false
/** Logical visibility: is the halo on-screen (as opposed to parked)? The primed
 *  window is always technically visible, so isVisible() is not the truth. */
let onScreen = false
let active: ActiveGlow | null = null
let runSeq = 0
let ackToken = 0
let pendingReveal: { token: number; plan: GlowPlan; preset: GlowPresetName; runId: number } | null =
  null
let ackFallback: ReturnType<typeof setTimeout> | null = null
let lifetimeTimer: ReturnType<typeof setTimeout> | null = null
let followTimer: ReturnType<typeof setInterval> | null = null
/** A show requested before the renderer mounted — replayed on glow:ready. */
let pendingShow: GlowPresetName | null = null

function diag(msg: string): void {
  if (is.dev) console.log(`[glow] ${msg}`)
}

export function createGlowWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 400,
    height: 300,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: false,
    movable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    // No icon: this window is never in Alt-Tab (skipTaskbar + focusable:false)
    // and never takes focus.
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      backgroundThrottling: false
    }
  })

  win.setAlwaysOnTop(true, 'screen-saver')
  // Fully click-through — NO { forward: true }. The bar forwards mouse moves
  // because it has interactive islands; the halo has none and must not consume a
  // single event: the user has to keep working in the window we are framing.
  win.setIgnoreMouseEvents(true)
  // Deliberately NO setContentProtection here (unlike the bar). The bar is Omi's
  // private UI, so excluding it from capture protects the user. The halo is
  // feedback ABOUT the window the user is looking at — WDA_EXCLUDEFROMCAPTURE
  // would make it invisible to every screen capture and recording, including the
  // user's own, which is both surprising and unverifiable.

  win.on('closed', () => {
    glowWindow = null
    glowReady = false
    glowPrimed = false
    onScreen = false
    active = null
    clearTimers()
  })
  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[glow] did-fail-load', code, desc, url)
  )
  win.webContents.on('did-start-loading', () => {
    glowReady = false
  })

  // Slim per-window entry (glow.html) instead of the full-app index.html — see
  // perf/win-slim-aux-windows. The `#/glow` hash is preserved so window-role
  // detection (windowRole.ts) and IPC sender labeling (voicePlaneIpc.ts) are
  // unchanged.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/glow.html#/glow`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/glow.html#/glow`)
  } else {
    win.loadFile(join(__dirname, '../renderer/glow.html'), { hash: 'glow' })
  }

  glowWindow = win
  prime(win)
  return win
}

/** One-time off-screen show: the unavoidable OS window-show fade is spent
 *  invisibly, and the HWND is never hidden again (see the header). */
function prime(win: BrowserWindow): void {
  if (glowPrimed) return
  glowPrimed = true
  const b = win.getBounds()
  win.setBounds({ x: PARKED_POS.x, y: PARKED_POS.y, width: b.width, height: b.height })
  win.showInactive()
  win.setIgnoreMouseEvents(true)
  onScreen = false
  diag('primed off-screen (OS show-fade spent invisibly)')
}

function ensureWindow(): BrowserWindow {
  if (glowWindow && !glowWindow.isDestroyed()) return glowWindow
  return createGlowWindow()
}

function park(win: BrowserWindow): void {
  const b = win.getBounds()
  win.setBounds({ x: PARKED_POS.x, y: PARKED_POS.y, width: b.width, height: b.height })
  onScreen = false
}

function clearTimers(): void {
  if (ackFallback) clearTimeout(ackFallback)
  ackFallback = null
  if (lifetimeTimer) clearTimeout(lifetimeTimer)
  lifetimeTimer = null
  if (followTimer) clearInterval(followTimer)
  followTimer = null
  pendingReveal = null
}

/** Sample the foreground window and decide where (and whether) to draw. Returns
 *  null when ANY gate fails — the caller then draws nothing, never a fragment. */
function currentPlan(): { plan: GlowPlan; handle: string | null } | null {
  const frame = getForegroundWindowFrame()
  // Env-gated decision dump for reproducing ghost-ring reports: everything the
  // gates key on, at the moment we decide. GLOW_DIAG=1 to enable in any build.
  if (process.env['GLOW_DIAG']) {
    console.warn(
      `[glow-diag] target hwnd=${frame.handle} class=${frame.className} pid=${frame.pid} ` +
        `own=${frame.pid != null && frame.pid === process.pid} cloaked=${frame.cloaked} ` +
        `visible=${frame.visible} min=${frame.minimized} max=${frame.maximized} ` +
        `rect=${frame.rect ? `${frame.rect.x},${frame.rect.y} ${frame.rect.width}x${frame.rect.height}` : 'null'}`
    )
  }
  if (!frame.rect) return null
  // Physical → DIP. screenToDipRect scales relative to the display nearest the
  // rect, which is the only multi-monitor-correct conversion Electron exposes
  // (dividing by a scale factor teleports the window on any layout whose origin
  // isn't zero). If it throws, we have no trustworthy geometry: draw nothing.
  let targetDip: Rect
  try {
    targetDip = screen.screenToDipRect(null, frame.rect)
  } catch (e) {
    diag(`screenToDipRect failed: ${String(e)}`)
    return null
  }
  const decision = planGlow({
    targetDip,
    displays: screen.getAllDisplays().map((d) => ({ bounds: d.bounds, workArea: d.workArea })),
    className: frame.className,
    maximized: frame.maximized,
    minimized: frame.minimized,
    visible: frame.visible,
    cloaked: frame.cloaked,
    // All of Omi's BrowserWindows are owned by this (the main/browser) process, so
    // a foreground window sharing our pid is our own UI — never frame it.
    ownWindow: frame.pid != null && frame.pid === process.pid
  })
  if (!decision.ok) {
    diag(`no halo: ${decision.reason}`)
    return null
  }
  return { plan: decision.plan, handle: frame.handle }
}

/**
 * Draw a halo around the active window in the named appearance (see
 * glowPresets.ts). A new glow supersedes any glow already on screen. No-op when
 * the user has turned the overlay off, or when any validity gate fails — the halo
 * is all-or-nothing.
 */
export function showGlow(preset: GlowPresetName): void {
  if (!getAppSettings().glowOverlayEnabled) return
  const target = currentPlan()
  if (!target) {
    // A superseding trigger that can't find a valid target must not leave the
    // previous halo hanging around a window it no longer describes.
    dismissGlow()
    return
  }
  const win = ensureWindow()
  if (!glowReady) {
    pendingShow = preset
    return
  }
  present(win, preset, target.plan, target.handle)
}

/** ARM: size the still-parked window and tell the renderer to play the run. The
 *  window stays invisible until the renderer acks it painted (otherwise the
 *  compositor shows the previous, stale frame first). */
function present(
  win: BrowserWindow,
  preset: GlowPresetName,
  plan: GlowPlan,
  handle: string | null
): void {
  clearTimers()
  const runId = ++runSeq
  const token = ++ackToken
  active = { runId, preset, targetHandle: handle, bounds: plan.windowBounds }
  // Size at the parked position; position follows on the ack.
  win.setBounds({
    x: PARKED_POS.x,
    y: PARKED_POS.y,
    width: plan.windowBounds.width,
    height: plan.windowBounds.height
  })
  pendingReveal = { token, plan, preset, runId }
  ackFallback = setTimeout(() => {
    console.warn('[glow] paint ack timed out; presenting via fallback')
    commitReveal(token)
  }, PAINT_ACK_FALLBACK_MS)
  // The renderer is handed a PAINT, never a preset name — it draws what it is
  // given and knows nothing about focus, distraction, or any future caller.
  win.webContents.send('glow:show', {
    paint: GLOW_PRESETS[preset],
    runId,
    token,
    pad: plan.pad,
    overlap: plan.overlap,
    radius: plan.radius,
    maximized: plan.maximized
  })
  diag(`arm run=${runId} preset=${preset} radius=${plan.radius} maximized=${plan.maximized}`)
}

/** COMMIT: the ring is painted — unpark. A stale ack (its run superseded or
 *  cancelled) is rejected. */
function commitReveal(token: number): void {
  const pending = pendingReveal
  if (!pending || pending.token !== token) return
  pendingReveal = null
  if (ackFallback) clearTimeout(ackFallback)
  ackFallback = null
  const win = glowWindow
  if (!win || win.isDestroyed() || !active || active.runId !== pending.runId) return
  win.setBounds(pending.plan.windowBounds)
  onScreen = true
  diag(
    `show run=${pending.runId} at ${pending.plan.windowBounds.x},${pending.plan.windowBounds.y} ${pending.plan.windowBounds.width}x${pending.plan.windowBounds.height}`
  )
  lifetimeTimer = setTimeout(dismissGlow, GLOW_LIFETIME_MS)
  followTimer = setInterval(followTick, GLOW_FOLLOW_MS)
}

/** Follow the target while the halo is up: re-read its frame, move with it, and
 *  dismiss the instant it stops being a valid target (minimized, closed, or the
 *  user switched to another app). ~110 samples over a 3.5s run — trivially cheap,
 *  and it only runs while a halo is on screen. */
function followTick(): void {
  const win = glowWindow
  if (!win || win.isDestroyed() || !onScreen || !active) {
    dismissGlow()
    return
  }
  const target = currentPlan()
  if (!target || target.handle !== active.targetHandle) {
    // Foreground switched apps, or the target minimized / went invalid.
    dismissGlow()
    return
  }
  const b = target.plan.windowBounds
  const cur = active.bounds
  if (b.x !== cur.x || b.y !== cur.y || b.width !== cur.width || b.height !== cur.height) {
    active.bounds = b
    win.setBounds(b)
    // The ring is `inset: var(--pad)` in CSS — it reflows with the window with
    // zero JS, and the CSS run keeps playing.
  }
}

/** Take the halo down (auto after GLOW_LIFETIME_MS, or when the target goes
 *  away). Parks the window — never hide(): a hidden transparent window fades in
 *  on its next show. */
export function dismissGlow(): void {
  clearTimers()
  active = null
  const win = glowWindow
  if (!win || win.isDestroyed()) return
  // PARK FIRST, then notify. If the send threw (a gone/destroyed webContents), an
  // unguarded send BEFORE the park would skip the park entirely — leaving the ring
  // on screen forever with every timer already cleared, i.e. the one path to a
  // permanently stuck overlay covering the user's window. Taking it off-screen is
  // the part that must not be able to fail.
  park(win)
  try {
    win.webContents.send('glow:hide')
  } catch {
    // The window is going away; it is already parked, which is what matters.
  }
  diag('dismiss (parked)')
}

/** The glow currently on screen, or null. */
export function getCurrentGlow(): { preset: GlowPresetName; runId: number } | null {
  if (!active || !onScreen) return null
  return { preset: active.preset, runId: active.runId }
}

export function registerGlowIpc(): void {
  ipcMain.on('glow:ready', (e) => {
    if (!glowWindow || e.sender.id !== glowWindow.webContents.id) return
    glowReady = true
    if (pendingShow) {
      const mode = pendingShow
      pendingShow = null
      showGlow(mode)
    }
  })
  ipcMain.on('glow:showAck', (e, token: number) => {
    if (!glowWindow || e.sender.id !== glowWindow.webContents.id) return
    commitReveal(token)
  })
  // The trigger the Focus assistant will call once it exists; today it is also
  // the dev/QA hook (window.omiGlow.trigger('distracted' | 'focused')). Unknown
  // preset names are ignored rather than crashing the main process.
  ipcMain.on('glow:trigger', (_e, preset: unknown) => {
    if (!isGlowPreset(preset)) return
    showGlow(preset)
  })
  ipcMain.on('glow:dismiss', () => dismissGlow())
  ipcMain.handle('glow:getCurrent', () => getCurrentGlow())
}

export function destroyGlow(): void {
  clearTimers()
  active = null
  onScreen = false
  glowPrimed = false
  if (glowWindow && !glowWindow.isDestroyed()) glowWindow.destroy()
  glowWindow = null
}
