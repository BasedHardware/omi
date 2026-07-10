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
import { rendererBaseUrl } from '../rendererServer'
import { isQuitting } from '../lifecycle'
import {
  computeBarBounds,
  computeStripBounds,
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
  win.setBounds(computeBarBounds(displayLike(target)))
  if (!barReady) {
    pendingShow = { mode, reveal }
    return
  }
  presentBar(win, mode, reveal)
}

function presentBar(win: BrowserWindow, mode: BarMode, reveal: BarReveal): void {
  if (hideFallback) {
    clearTimeout(hideFallback)
    hideFallback = null
  }
  currentMode = mode
  if (mode === 'expanded') {
    win.setFocusable(true)
    win.setIgnoreMouseEvents(false)
    win.showInactive()
    win.focus()
  } else {
    win.setFocusable(false)
    win.setIgnoreMouseEvents(true, { forward: true })
    win.showInactive()
  }
  send('bar:show', { mode, reveal })
  send('overlay:shown')
  broadcastVisibility()
}

/** Mode transition while visible (peek ⇄ expanded, ptt → expanded). */
export function setBarMode(mode: BarMode): void {
  const win = barWindow
  if (!win || win.isDestroyed() || !win.isVisible()) return
  if (currentMode === mode) return
  currentMode = mode
  if (mode === 'expanded') {
    win.setFocusable(true)
    win.setIgnoreMouseEvents(false)
    win.focus()
  } else {
    win.setFocusable(false)
    win.setIgnoreMouseEvents(true, { forward: true })
  }
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
  const win = barWindow
  if (!win || win.isDestroyed()) return
  if (win.isVisible()) win.hide()
  win.setFocusable(false)
  win.setIgnoreMouseEvents(true, { forward: true })
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
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })
  win.setAlwaysOnTop(true, 'screen-saver')
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
    // The hook fires on our thread; keep the handler tiny + guarded.
    try {
      evaluateStripSuppression()
    } catch {
      /* never throw into the native dispatcher */
    }
  })
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
  // Interactive islands: the renderer toggles real hit-testing as the cursor
  // enters/leaves interactive elements (peek/ptt modes only — expanded is
  // fully interactive).
  ipcMain.on('bar:setInteractive', (_e, interactive: boolean) => {
    const win = barWindow
    if (!win || win.isDestroyed() || currentMode === 'expanded') return
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
