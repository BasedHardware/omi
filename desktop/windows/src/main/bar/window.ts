// The top-edge companion bar — Windows' answer to the Mac notch. One frameless
// TRANSPARENT window per reveal (fixed bounds, computed per display): all
// motion — slide-in, genesis, expand/morph — happens via CSS/canvas INSIDE the
// static window; bounds are never animated. This replaces the old acrylic
// overlay window: the overlay chat UI is the bar's expanded content, and the
// `overlay:*` IPC channel names remain the renderer-facing API (onboarding
// steps keep working untouched).
//
// NOTE on the overlay height-tween machinery (main/overlay/window.ts, now
// removed): it existed because that window was an opaque DWM-material panel
// whose bounds had to match content height. A transparent click-through window
// doesn't have that constraint, so the tween was deliberately NOT ported —
// expanded content sizes itself in CSS and scrolls internally.
//
// Focus rules (the bar must never steal keystrokes):
//   peek (edge-hover reveal)  → focusable:false, showInactive, click-through
//                               with interactive islands
//   ptt (hotkey held)         → same as peek, expanded listening UI
//   expanded (hotkey tap /    → focusable:true + focused — the ONLY mode that
//             click on pill)    takes focus, because the user asked to type
import { BrowserWindow, ipcMain, screen } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import iconPath from '../../../resources/icon.png?asset'
import { rendererBaseUrl } from '../rendererServer'
import { isQuitting } from '../lifecycle'
import {
  computeBarBounds,
  computeStripBounds,
  isCursorInPeekFootprint,
  isCursorOverPill,
  shouldSuppressStrips,
  type DisplayLike
} from './placement'
import { SummonGesture, type GestureKind } from './gesture'
import { makeKeySampler } from './keyState'
import { getForegroundWindowRect, subscribeForegroundChange } from '../usage/nativeForeground'
import { getAppSettings, setAppSettings } from '../appSettings'

export type BarMode = 'peek' | 'expanded' | 'ptt'
export type BarReveal = 'strip' | 'summon' | 'ptt'

let barWindow: BrowserWindow | null = null
let barReady = false
let barEnabled = false
let currentMode: BarMode | null = null
/** Whether real hit-testing is currently enabled (cursor over the surface). */
let barInteractive = false
/** Display the bar is currently presented on (retract watchdog target). */
let activeDisplayId: number | null = null
let pendingShow: { mode: BarMode; reveal: BarReveal } | null = null
let pendingPttDown = false
let hideFallback: ReturnType<typeof setTimeout> | null = null

export function getBarWindow(): BrowserWindow | null {
  return barWindow
}

export function isBarVisible(): boolean {
  return !!(barWindow && !barWindow.isDestroyed() && barWindow.isVisible())
}

function displayLike(d: Electron.Display): DisplayLike {
  return { id: d.id, bounds: d.bounds, workArea: d.workArea, scaleFactor: d.scaleFactor }
}

function send(channel: string, ...args: unknown[]): void {
  const win = barWindow
  if (win && !win.isDestroyed()) win.webContents.send(channel, ...args)
}

function broadcast(channel: string, ...args: unknown[]): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send(channel, ...args)
  }
}

/** Overlay-compat visibility broadcast (onboarding voice step relies on it). */
function broadcastVisibility(): void {
  const open = isBarVisible()
  const active = open && !!barWindow && barWindow.isFocused()
  broadcast('overlay:visibility', { open, active })
}

export function createBarWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 560,
    height: 400,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    // Frameless + skipTaskbar, but still set the app icon so Alt-Tab/system
    // listings never show the default Electron icon (ported from the OAuth
    // window-icon fix that landed on the old overlay window upstream).
    icon: iconPath,
    // Transparent windows have no DWM material; the renderer paints the bar
    // surface itself (dark, rounded — understated).
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      backgroundThrottling: false
    }
  })

  // Float above fullscreen-ish surfaces; the strip suppression keeps us out of
  // real fullscreen apps.
  win.setAlwaysOnTop(true, 'screen-saver')
  // Default: click-through, but keep receiving mousemove (forward) so the
  // renderer can manage its interactive islands + hover grace.
  win.setIgnoreMouseEvents(true, { forward: true })
  applyBarContentProtection(win)

  win.on('focus', () => {
    send('overlay:active', true)
    broadcastVisibility()
  })
  win.on('blur', () => {
    send('overlay:active', false)
    broadcastVisibility()
  })
  win.on('close', (e) => {
    if (!isQuitting()) {
      e.preventDefault()
      hideBar()
    }
  })
  win.on('closed', () => {
    barWindow = null
    barReady = false
    currentMode = null
  })
  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[bar] did-fail-load', code, desc, url)
  )
  // A crash-reload restarts the renderer: it must re-report bar:ready before
  // any deferred show presents (otherwise we'd present an unmounted frame).
  win.webContents.on('did-start-loading', () => {
    barReady = false
  })

  // Same-origin as the main window (auth/localStorage are per-origin).
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#/bar`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/index.html#/bar`)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'), { hash: 'bar' })
  }

  barWindow = win
  return win
}

/** Content protection (WDA_EXCLUDEFROMCAPTURE) is a USER TOGGLE (persisted in
 *  app settings, default on) — consistent with the old overlay's behavior. */
function applyBarContentProtection(win: BrowserWindow): void {
  try {
    win.setContentProtection(getAppSettings().hudContentProtection)
  } catch {
    /* unsupported build */
  }
}

function ensureBarWindow(): BrowserWindow {
  if (barWindow && !barWindow.isDestroyed()) return barWindow
  return createBarWindow()
}

/** Enable/disable the bar (gated until onboarding's shortcut step). Enabling
 *  pre-warms the window so the first summon is instant and signed-in. */
export function setBarEnabled(enabled: boolean): void {
  barEnabled = enabled
  if (!enabled) {
    hideBarNow()
    return
  }
  ensureBarWindow()
}

export function isBarEnabled(): boolean {
  return barEnabled
}

/**
 * Reveal the bar on the display under the cursor (or an explicit display).
 * Defers until the renderer has mounted (bar:ready) so the first summon never
 * flashes an empty frame.
 */
export function showBar(mode: BarMode, reveal: BarReveal, display?: Electron.Display): void {
  if (!barEnabled) return
  const win = ensureBarWindow()
  const target = display ?? screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
  activeDisplayId = target.id
  win.setBounds(computeBarBounds(displayLike(target)))
  if (!barReady) {
    pendingShow = { mode, reveal }
    return
  }
  presentBar(win, mode, reveal)
}

// Hit-testing rule (merge-blocker fix): the bar window is ALWAYS click-through
// (ignore + forward) except while the cursor is actually over the visible
// surface — the renderer's mouseenter/mouseleave drives bar:setInteractive in
// EVERY mode. Focus is orthogonal: expanded keeps keyboard focus for typing
// while dead space around the panel stays fully click-through. (Making the
// whole window solid in expanded mode blocked clicks on everything under the
// invisible 560×~640 region — live bug.)
function applyClickThrough(win: BrowserWindow): void {
  barInteractive = false
  win.setIgnoreMouseEvents(true, { forward: true })
}

function presentBar(win: BrowserWindow, mode: BarMode, reveal: BarReveal): void {
  if (hideFallback) {
    clearTimeout(hideFallback)
    hideFallback = null
  }
  currentMode = mode
  applyClickThrough(win)
  if (mode === 'expanded') {
    win.setFocusable(true)
    win.showInactive()
    win.focus()
  } else {
    win.setFocusable(false)
    win.showInactive()
  }
  if (mode === 'peek') startPeekWatch()
  else stopPeekWatch()
  send('bar:show', { mode, reveal })
  send('overlay:shown')
  broadcastVisibility()
}

// --- Peek retract watchdog ----------------------------------------------------
// A hover-revealed bar must retract when the cursor leaves its footprint. The
// renderer CANNOT own this: with click-through + forwarded events, DOM
// mouseleave never fires once the cursor exits the window region — the events
// simply stop, so the bar got stuck open when hovering elsewhere along the
// top edge (live bug). Main polls the cursor ONLY while a peek bar is visible
// (a rare, brief state — idle remains strictly zero-poll) and hides after the
// grace period once the cursor is outside (bar footprint ∪ strip footprint).
const PEEK_WATCH_MS = 150
const PEEK_GRACE_MS = 600
let peekWatch: ReturnType<typeof setInterval> | null = null
let peekOutsideSince: number | null = null
/** Harness-only (OMI_E2E hook): hold a peek bar open while screenshots are
 *  captured — on a live desktop the cursor is legitimately outside the
 *  footprint, so the watchdog would retract mid-capture. Never set in prod. */
let peekWatchSuspended = false

export function setPeekWatchSuspended(suspended: boolean): void {
  peekWatchSuspended = suspended
}

function startPeekWatch(): void {
  stopPeekWatch()
  peekOutsideSince = null
  peekWatch = setInterval(() => {
    const win = barWindow
    if (!win || win.isDestroyed() || !win.isVisible() || currentMode !== 'peek') {
      stopPeekWatch()
      return
    }
    const display =
      screen.getAllDisplays().find((d) => d.id === activeDisplayId) ?? screen.getPrimaryDisplay()
    const dl = displayLike(display)
    const cursor = screen.getCursorScreenPoint()
    // Click-through safety net: the bar window is intentionally oversized (560×…
    // for the morph), but only the 148×36 pill should ever capture a click. If
    // the interactive flag stuck on after the cursor left the pill (DOM
    // mouseleave never fires once the cursor exits a forwarded-events window),
    // force the whole window back to click-through so a control under the
    // top-center dead space stays clickable. (Not while the E2E holds peek open.)
    if (!peekWatchSuspended && barInteractive && !isCursorOverPill(cursor, dl)) {
      applyClickThrough(win)
    }
    const inside = peekWatchSuspended || isCursorInPeekFootprint(cursor, dl)
    if (inside) {
      peekOutsideSince = null
    } else if (peekOutsideSince === null) {
      peekOutsideSince = Date.now()
    } else if (Date.now() - peekOutsideSince >= PEEK_GRACE_MS) {
      stopPeekWatch()
      hideBar()
    }
  }, PEEK_WATCH_MS)
}

function stopPeekWatch(): void {
  if (peekWatch) clearInterval(peekWatch)
  peekWatch = null
  peekOutsideSince = null
}

/** Mode transition while visible (peek ⇄ expanded, ptt → expanded). */
export function setBarMode(mode: BarMode): void {
  const win = barWindow
  if (!win || win.isDestroyed() || !win.isVisible()) return
  if (currentMode === mode) return
  currentMode = mode
  if (mode === 'expanded') {
    win.setFocusable(true)
    win.focus()
  } else {
    win.setFocusable(false)
    applyClickThrough(win)
  }
  if (mode === 'peek') startPeekWatch()
  else stopPeekWatch()
  send('bar:mode', mode)
  broadcastVisibility()
}

/** Graceful hide: the renderer plays its slide-out, then asks for the real
 *  hide (bar:requestHide). A fallback timer guarantees the window hides even
 *  if the renderer is wedged. */
export function hideBar(): void {
  const win = barWindow
  if (!win || win.isDestroyed() || !win.isVisible()) return
  send('overlay:willHide')
  send('bar:willHide')
  if (hideFallback) clearTimeout(hideFallback)
  hideFallback = setTimeout(hideBarNow, 450)
}

function hideBarNow(): void {
  if (hideFallback) {
    clearTimeout(hideFallback)
    hideFallback = null
  }
  stopPeekWatch()
  const win = barWindow
  if (!win || win.isDestroyed()) return
  if (win.isVisible()) win.hide()
  win.setFocusable(false)
  applyClickThrough(win)
  currentMode = null
  broadcastVisibility()
}

// --- Summon gesture (hotkey tap = toggle chat, hold = push-to-talk) ----------

let gesture: SummonGesture | null = null
let gestureStartedVisible = false
let samplerAvailable = false

function sendPtt(phase: 'down' | 'up'): void {
  if (!barReady) {
    // A cold first summon: queue the down, drop a release that beat the mount.
    pendingPttDown = phase === 'down'
    return
  }
  send('bar:ptt', phase)
}

function onGestureStart(): void {
  if (!barEnabled) return
  broadcast('overlay:summoned')
  gestureStartedVisible = isBarVisible()
  if (samplerAvailable) {
    // Tap-vs-hold resolves at release; open now (stable — never flaps), and
    // arm the PTT path (the renderer's own hold threshold decides recording).
    if (!gestureStartedVisible) showBar('expanded', 'summon')
    sendPtt('down')
  } else {
    // No key-state sampling (koffi unavailable): classic debounced toggle.
    if (gestureStartedVisible) hideBar()
    else showBar('expanded', 'summon')
  }
}

function onGestureEnd(kind: GestureKind): void {
  if (!samplerAvailable) return
  sendPtt('up')
  // A tap on an already-open bar closes it (deferred to release so a HOLD on
  // an open bar stays a stable push-to-talk, never a flap).
  if (kind === 'tap' && gestureStartedVisible) hideBar()
}

/** Wire as the global summon shortcut's callback (fires on every auto-repeat;
 *  the gesture machine collapses repeats into one gesture). */
export function handleSummonPress(): void {
  gesture?.fire()
}

/** (Re)build the gesture machine for an accelerator — call at startup and
 *  after every rebind so hold detection tracks the current chord. */
export function setSummonGestureAccelerator(accelerator: string): void {
  gesture?.dispose()
  const sampler = makeKeySampler(accelerator)
  samplerAvailable = !!sampler
  gesture = new SummonGesture(
    { onStart: onGestureStart, onEnd: onGestureEnd },
    { sampleKeyDown: sampler }
  )
}

// --- Trigger strips (1px, top edge of every display; zero polling) -----------

const strips = new Map<number, BrowserWindow>()
let stripsStarted = false
let unsubForeground: (() => void) | null = null

// A fully-transparent window is click-through on Windows (layered hit-testing
// skips alpha-0 pixels), so the strip paints an imperceptible 1/255-alpha wash
// to stay hit-testable. mousemove over the 1px line is the reveal trigger.
const STRIP_HTML =
  'data:text/html;charset=utf-8,' +
  encodeURIComponent(
    `<!doctype html><html><body style="margin:0;background:rgba(0,0,0,0.004)"></body>` +
      `<script>addEventListener('mousemove',()=>{window.omiBar&&window.omiBar.stripEnter()},{passive:true})</script></html>`
  )

function createStrip(display: Electron.Display): BrowserWindow {
  const bounds = computeStripBounds(displayLike(display))
  const win = new BrowserWindow({
    ...bounds,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    // No WS_THICKFRAME: a sizing frame imposes an OS minimum window size that
    // would silently inflate the 1px strip.
    thickFrame: false,
    minHeight: 0,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  // The strip stays HIT-TESTABLE (NOT click-through) — it is the dedicated,
  // ultra-thin (1px) reveal detector, decoupled from the click-blocking surface
  // (the bar window). It must reliably catch the cursor reaching the top edge
  // from ANY approach; forwarded mousemove on a click-through window only fired
  // on an edge-slide, not a straight-up approach (reveal regression). Being 1px
  // at y=0 it cannot swallow a real click meant for the app (a browser's new-tab
  // "+" sits well below the top pixel). The click-through that BUG 4 needs lives
  // on the bar WINDOW instead: only the visible pill captures clicks, and the
  // peek watchdog forces the rest click-through (see isCursorOverPill).
  try {
    win.setContentProtection(true) // invisible helper — never in captures
  } catch {
    /* unsupported */
  }
  win.loadURL(STRIP_HTML)
  win.setBounds(bounds) // re-assert after load (some drivers nudge 1px windows)
  win.showInactive()
  return win
}

function rebuildStrips(): void {
  for (const [, w] of strips) {
    if (!w.isDestroyed()) w.destroy()
  }
  strips.clear()
  if (!stripsStarted) return
  for (const d of screen.getAllDisplays()) {
    strips.set(d.id, createStrip(d))
  }
  evaluateStripSuppression()
}

/** Hide strips on displays whose foreground window is fullscreen (never pop
 *  the bar over games/videos). Event-driven off the foreground hook. */
function evaluateStripSuppression(): void {
  const fg = getForegroundWindowRect()
  for (const d of screen.getAllDisplays()) {
    const strip = strips.get(d.id)
    if (!strip || strip.isDestroyed()) continue
    const suppress = shouldSuppressStrips(fg, displayLike(d), process.execPath)
    if (suppress && strip.isVisible()) strip.hide()
    else if (!suppress && !strip.isVisible()) strip.showInactive()
  }
}

/** Start the edge-reveal machinery (strips + display tracking + fullscreen
 *  suppression). Call once after app ready (deferred with the other services). */
export function startBarStrips(): void {
  if (stripsStarted) return
  stripsStarted = true
  rebuildStrips()
  screen.on('display-added', rebuildStrips)
  screen.on('display-removed', rebuildStrips)
  screen.on('display-metrics-changed', rebuildStrips)
  unsubForeground = subscribeForegroundChange(() => {
    // The WinEvent hook calls back on our thread mid-dispatch — defer the
    // window show/hide work out of the native callback, and never throw back
    // into the dispatcher.
    setImmediate(() => {
      try {
        evaluateStripSuppression()
      } catch {
        /* guarded */
      }
    })
  })
}

/** Diagnostics for the E2E harness: strips vs displays, with real bounds. */
export function getStripDiagnostics(): {
  displays: { id: number; bounds: Electron.Rectangle }[]
  strips: { id: number; bounds: Electron.Rectangle; visible: boolean }[]
} {
  return {
    displays: screen.getAllDisplays().map((d) => ({ id: d.id, bounds: d.bounds })),
    strips: [...strips.values()]
      .filter((w) => !w.isDestroyed())
      .map((w) => ({ id: w.id, bounds: w.getBounds(), visible: w.isVisible() }))
  }
}

/** E2E diagnostic: is real hit-testing currently enabled? Must be FALSE right
 *  after any present (even expanded) — the window starts click-through and
 *  only the cursor entering the visible surface enables interaction. */
export function isBarInteractive(): boolean {
  return barInteractive
}

// --- IPC ----------------------------------------------------------------------

export function registerBarIpc(): void {
  ipcMain.on('bar:ready', (e) => {
    if (!barWindow || e.sender.id !== barWindow.webContents.id) return
    barReady = true
    if (pendingShow) {
      const { mode, reveal } = pendingShow
      pendingShow = null
      presentBar(barWindow, mode, reveal)
    }
    if (pendingPttDown) {
      pendingPttDown = false
      send('bar:ptt', 'down')
    }
  })
  ipcMain.on('bar:requestHide', () => hideBarNow())
  ipcMain.on('bar:expand', () => setBarMode('expanded'))
  ipcMain.on('bar:collapse', () => setBarMode('peek'))
  // Interactive islands — EVERY mode: the renderer toggles real hit-testing
  // as the cursor enters/leaves the visible surface, so the effective ignore
  // region is always "window minus the bar's visual rect". The transparent
  // dead space around the panel must never eat clicks (merge-blocker fix).
  ipcMain.on('bar:setInteractive', (_e, interactive: boolean) => {
    const win = barWindow
    if (!win || win.isDestroyed()) return
    barInteractive = !!interactive
    if (interactive) win.setIgnoreMouseEvents(false)
    else win.setIgnoreMouseEvents(true, { forward: true })
  })
  // Edge reveal from a trigger strip: peek on the display under the cursor.
  ipcMain.on('bar:stripEnter', () => {
    if (!barEnabled || isBarVisible()) return
    showBar('peek', 'strip')
  })
  // Screen-share privacy toggle (persisted; applied live).
  ipcMain.handle('bar:getContentProtection', () => getAppSettings().hudContentProtection)
  ipcMain.handle('bar:setContentProtection', (_e, enabled: boolean) => {
    setAppSettings({ hudContentProtection: !!enabled })
    if (barWindow && !barWindow.isDestroyed()) applyBarContentProtection(barWindow)
    return getAppSettings().hudContentProtection
  })
}

// --- Teardown -----------------------------------------------------------------

export function destroyBar(): void {
  gesture?.dispose()
  gesture = null
  stopPeekWatch()
  if (hideFallback) clearTimeout(hideFallback)
  hideFallback = null
  unsubForeground?.()
  unsubForeground = null
  screen.removeListener('display-added', rebuildStrips)
  screen.removeListener('display-removed', rebuildStrips)
  screen.removeListener('display-metrics-changed', rebuildStrips)
  stripsStarted = false
  for (const [, w] of strips) {
    if (!w.isDestroyed()) w.destroy()
  }
  strips.clear()
  if (barWindow && !barWindow.isDestroyed()) barWindow.destroy()
  barWindow = null
}
