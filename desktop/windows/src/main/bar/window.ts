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
// The bar is summoned by the hotkey ONLY (top-edge hover reveal was removed —
// Chris disliked it). A hotkey TAP reveals the collapsed pill; clicking the pill
// expands it to the chat surface; a hotkey HOLD is push-to-talk (auto-reveals
// the pill). The peek retract watchdog stays as the pill's dismissal mechanism
// (cursor leaves its footprint → grace → hide), suspended while voice/chat
// activity is in flight (bar:keepAlive) so a spoken exchange isn't cut short.
//
// Focus rules (the bar must never steal keystrokes):
//   peek (hotkey tap / PTT)   → focusable:false, showInactive, click-through
//                               with interactive islands
//   ptt (dead — E2E only)     → same as peek
//   expanded (click on pill)  → focusable:true + focused — the ONLY mode that
//                               takes focus, because the user asked to type
import { BrowserWindow, ipcMain, screen } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import iconPath from '../../../resources/icon.png?asset'
import { rendererBaseUrl } from '../rendererServer'
import { isQuitting } from '../lifecycle'
import {
  computeBarBounds,
  isCursorInPeekFootprint,
  isCursorOverPill,
  type DisplayLike
} from './placement'
import { SummonGesture, type GestureKind } from './gesture'
import {
  evaluatePeekWatchdog,
  nextInteractivity,
  barWatchPlan,
  barGestureSeesOpen
} from './watchdog'
import { makeKeySampler } from './keyState'
import { getAppSettings, setAppSettings } from '../appSettings'

export type BarMode = 'peek' | 'expanded' | 'ptt'
export type BarReveal = 'summon' | 'ptt'

let barWindow: BrowserWindow | null = null
let barReady = false
let barEnabled = false
let currentMode: BarMode | null = null
/** True from the moment a graceful hide begins (slide-out sent) until the window
 *  is actually hidden. During this window win.isVisible() is still TRUE and
 *  currentMode is still set, but the bar is on its way OUT — the summon gesture
 *  must treat it as NOT presented (see isBarCleanlyPresented): the live bug was a
 *  tap landing during a retract's slide-out seeing "visible", skipping showBar
 *  (so the peek watch + interactivity never restarted) AND toggling the bar shut
 *  on release — "the bar goes back up extremely quickly" + dead clicks. */
let barHiding = false
/** Whether real hit-testing is currently enabled (cursor over the surface). */
let barInteractive = false
/** Display the bar is currently presented on (retract watchdog target). */
let activeDisplayId: number | null = null
let pendingShow: { mode: BarMode; reveal: BarReveal } | null = null
let pendingPttDown = false
let hideFallback: ReturnType<typeof setTimeout> | null = null
// Per-reveal paint-ack handshake (see presentBar/commitReveal): the bar window
// is ARMED (renderer told to reveal) but stays hidden until the renderer acks
// it painted the revealed frame, so we never flash the previous off-screen
// frame (blank-bar paint race). The token rejects stale acks from a reveal that
// was cancelled or superseded before it painted.
let revealToken = 0
let pendingReveal: { token: number; mode: BarMode; reveal: BarReveal } | null = null
let revealFallback: ReturnType<typeof setTimeout> | null = null
// If the renderer is wedged/slow and never acks, show anyway after this — the
// bar must never become unsummonable.
const REVEAL_ACK_FALLBACK_MS = 150

export function getBarWindow(): BrowserWindow | null {
  return barWindow
}

export function isBarVisible(): boolean {
  return !!(barWindow && !barWindow.isDestroyed() && barWindow.isVisible())
}

/** Whether the bar is up in a clean, interactive presentation (a real peek /
 *  ptt / expanded surface with its watch running) — as opposed to merely having
 *  a shown HWND. A window mid-retract (barHiding) or shown-but-unpresented
 *  (currentMode null, e.g. a hide that didn't fully take) is NOT cleanly
 *  presented. The summon gesture keys off THIS, not raw window visibility, so a
 *  tap always re-presents (restarting the peek watch + interactivity) unless the
 *  bar is genuinely, cleanly open — the fix for the stuck-window inversion where
 *  a tap saw "visible", skipped showBar, and left clicks dead / toggled it shut. */
export function isBarCleanlyPresented(): boolean {
  return barGestureSeesOpen({ visible: isBarVisible(), mode: currentMode, hiding: barHiding })
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
    cancelPendingReveal()
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

/** Invalidate an armed-but-not-yet-shown reveal (its token + fallback timer). */
function cancelPendingReveal(): void {
  pendingReveal = null
  if (revealFallback) {
    clearTimeout(revealFallback)
    revealFallback = null
  }
}

/**
 * ARM phase: prepare window state and tell the renderer to reveal, but do NOT
 * show the HWND yet. The window is shown in commitReveal, once the renderer
 * acks (bar:showAck) that it painted the revealed frame — otherwise the
 * compositor shows the previous off-screen frame first (the blank-bar race).
 */
function presentBar(win: BrowserWindow, mode: BarMode, reveal: BarReveal): void {
  // A pending hide-fallback must not fire mid-reveal.
  if (hideFallback) {
    clearTimeout(hideFallback)
    hideFallback = null
  }
  // A fresh reveal supersedes any in-flight graceful hide.
  barHiding = false
  currentMode = mode
  applyClickThrough(win)
  win.setFocusable(mode === 'expanded')
  const token = ++revealToken
  pendingReveal = { token, mode, reveal }
  if (revealFallback) clearTimeout(revealFallback)
  revealFallback = setTimeout(() => {
    // No paint ack arrived — present anyway so a wedged/slow renderer can never
    // make the bar unsummonable. Not silent: this is the fail-open path.
    console.warn('[bar] reveal paint-ack timed out; presenting via fallback')
    commitReveal(token)
  }, REVEAL_ACK_FALLBACK_MS)
  send('bar:show', { mode, reveal, token })
}

/** COMMIT phase: the renderer painted the revealed frame (or the fallback
 *  fired) — show the HWND now. Rejects a stale ack whose reveal was cancelled
 *  or superseded. */
function commitReveal(token: number): void {
  const pending = pendingReveal
  if (!pending || pending.token !== token) return
  const win = barWindow
  if (!win || win.isDestroyed()) {
    cancelPendingReveal()
    return
  }
  cancelPendingReveal()
  win.showInactive()
  if (pending.mode === 'expanded') win.focus()
  // Watch runs in every visible collapsed mode (peek + ptt) — it drives
  // click-to-expand interactivity; only peek also runs the retract grace.
  if (pending.mode !== 'expanded') startPeekWatch()
  else stopPeekWatch()
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
// Poll fast while a peek pill is visible (a rare, brief state — idle stays
// strictly zero-poll): the tick both drives interactivity from the OS cursor
// and runs the retract grace, and a normal move-and-click on the pill must flip
// hit-testing on before the click lands (Bug A). 50ms keeps that imperceptible.
const PEEK_WATCH_MS = 50
const PEEK_GRACE_MS = 600
// A freshly summoned pill the cursor has NOT yet reached lingers this long before
// the retract grace can fire — a tap summon puts the pill at top-center while the
// cursor is still at the working position, and 600ms was gone before the hand
// arrived (live bug: "the bar goes back up extremely quickly"). Once the cursor
// has visited the footprint and left, the short PEEK_GRACE_MS applies.
const SUMMON_LINGER_MS = 3000
let peekWatch: ReturnType<typeof setInterval> | null = null
let peekOutsideSince: number | null = null
/** Whether the cursor has entered the peek footprint since this reveal — gates
 *  the long summon linger vs. the short post-visit grace. Reset per reveal. */
let peekHasBeenHovered = false
/** Harness-only (OMI_E2E hook): hold a peek bar open while screenshots are
 *  captured — on a live desktop the cursor is legitimately outside the
 *  footprint, so the watchdog would retract mid-capture. Never set in prod. */
let peekWatchSuspended = false
/** Renderer-driven hold: while true, the summoned pill must NOT auto-retract
 *  even though the cursor is away from its footprint — a PTT hold / streaming
 *  reply / spoken answer is in flight (the user is talking or listening, not
 *  hovering). The bar renderer sets this via bar:keepAlive and drops it (after a
 *  short grace) when the exchange ends, letting the normal cursor watchdog
 *  reclaim the pill. */
let barActivityHold = false
/** Set for the ENTIRE lifetime of a summon gesture (the hotkey is physically
 *  held, or the gap window before a no-sampler gesture ends). Suppresses the
 *  retract watchdog structurally so a silent hold can't retract the pill before
 *  the renderer's busy-derived keepAlive arms (Bug B). Cleared at gesture end. */
let gestureActiveHold = false

export function setPeekWatchSuspended(suspended: boolean): void {
  peekWatchSuspended = suspended
}

/** One watch poll. Runs while the bar is visible and collapsed (peek OR ptt):
 *  drive interactivity from the OS cursor in EVERY such mode (Bug A — a ptt pill
 *  that lingers after release must be as clickable as a tap pill), then run the
 *  retract grace in PEEK ONLY (a ptt pill's lifetime is owned by the
 *  gesture/keepAlive, not the cursor watchdog). Also called once synchronously
 *  at reveal so a cursor already over the pill / outside the footprint is handled
 *  without a tick's delay. */
function peekTick(): void {
  const win = barWindow
  const plan = barWatchPlan(currentMode)
  if (!win || win.isDestroyed() || !win.isVisible() || !plan.trackInteractivity) {
    stopPeekWatch()
    return
  }
  const display =
    screen.getAllDisplays().find((d) => d.id === activeDisplayId) ?? screen.getPrimaryDisplay()
  const dl = displayLike(display)
  const cursor = screen.getCursorScreenPoint()
  // Main-driven interactivity (Bug A): the OS cursor over the 148×36 pill hit
  // rect is the source of truth — enable hit-testing the instant it enters (no
  // async renderer mouseenter → IPC round-trip a fast click could beat), and
  // force the oversized window back to click-through the instant it leaves so a
  // control under the top-center dead space stays clickable. The renderer's
  // mouseenter/leave path stays as a belt; here main leads.
  const wantInteractive = nextInteractivity({
    cursorOverPill: isCursorOverPill(cursor, dl),
    interactive: barInteractive,
    suspended: peekWatchSuspended
  })
  if (wantInteractive && !barInteractive) {
    barInteractive = true
    win.setIgnoreMouseEvents(false)
  } else if (!wantInteractive && barInteractive) {
    applyClickThrough(win)
  }
  // Retract grace is peek-only; a ptt pill never auto-retracts on the cursor.
  if (!plan.runRetract) {
    peekOutsideSince = null
    return
  }
  const cursorInFootprint = isCursorInPeekFootprint(cursor, dl)
  if (cursorInFootprint) peekHasBeenHovered = true
  const { outsideSince, retract } = evaluatePeekWatchdog({
    suspended: peekWatchSuspended,
    activityHold: barActivityHold,
    gestureActive: gestureActiveHold,
    cursorInFootprint,
    hasBeenHovered: peekHasBeenHovered,
    outsideSince: peekOutsideSince,
    now: Date.now(),
    graceMs: PEEK_GRACE_MS,
    lingerMs: SUMMON_LINGER_MS
  })
  peekOutsideSince = outsideSince
  if (retract) {
    stopPeekWatch()
    hideBar()
  }
}

function startPeekWatch(): void {
  stopPeekWatch()
  peekOutsideSince = null
  peekHasBeenHovered = false
  peekTick()
  peekWatch = setInterval(peekTick, PEEK_WATCH_MS)
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
  if (mode !== 'expanded') startPeekWatch()
  else stopPeekWatch()
  send('bar:mode', mode)
  broadcastVisibility()
}

/** Graceful hide: the renderer plays its slide-out, then asks for the real
 *  hide (bar:requestHide). A fallback timer guarantees the window hides even
 *  if the renderer is wedged. */
export function hideBar(): void {
  const win = barWindow
  if (!win || win.isDestroyed()) return
  // An armed-but-unshown reveal is cancelled outright — there is nothing to
  // slide out, and a late ack/fallback must not resurrect it.
  if (pendingReveal) {
    cancelPendingReveal()
    if (!win.isVisible()) {
      currentMode = null
      return
    }
  }
  if (!win.isVisible()) return
  // Mark the bar as on-its-way-out: a summon gesture arriving during the
  // slide-out must re-present it (restart the peek watch), not treat it as a
  // cleanly-open pill to toggle shut.
  barHiding = true
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
  barHiding = false
  // Kill any armed reveal so a late ack/fallback can't re-show after a hide.
  cancelPendingReveal()
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
  // Key off a CLEAN presentation, not raw window visibility: a bar mid-retract or
  // shown-but-unpresented must count as not-open, so a tap re-presents (restarts
  // the peek watch + interactivity) instead of being swallowed / toggled shut.
  gestureStartedVisible = isBarCleanlyPresented()
  // Pin the pill open for the whole physical hold (Bug B): the watchdog can't
  // retract while the key is down, so a silent hold never snaps shut before the
  // renderer's busy-derived keepAlive arms. Cleared in onGestureEnd.
  gestureActiveHold = true
  if (samplerAvailable) {
    // Tap-vs-hold resolves at release; reveal the PILL now (a tap peeks, never
    // auto-opens the chat — Chris's rule), and arm the PTT path (the renderer's
    // own hold threshold decides recording; a hold keeps the pill up + drives
    // the orb). Click the pill to expand into the chat surface.
    if (!gestureStartedVisible) showBar('peek', 'summon')
    sendPtt('down')
  } else {
    // No key-state sampling (koffi unavailable): classic debounced toggle — tap
    // reveals the pill, tap again hides it.
    if (gestureStartedVisible) hideBar()
    else showBar('peek', 'summon')
  }
}

function onGestureEnd(kind: GestureKind): void {
  // Release the physical-hold suppression FIRST — before any early return — so
  // gap mode (no sampler) and dispose()/rebind can never leave the watchdog
  // permanently suppressed (a stuck-open pill). The renderer's keepAlive takes
  // over from here for a real voice/chat exchange.
  gestureActiveHold = false
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

/** E2E diagnostic: is real hit-testing currently enabled? Must be FALSE right
 *  after any present (even expanded) — the window starts click-through and
 *  only the cursor entering the visible surface enables interaction. */
export function isBarInteractive(): boolean {
  return barInteractive
}

// --- IPC ----------------------------------------------------------------------

/**
 * @param sendToMain forwards a channel to the MAIN app window (the bar chat is a
 *   viewport over the main window's single chat engine — INV-CHAT-1). Injected
 *   because window.ts has no reference to the main window (it lives in index.ts).
 */
export function registerBarIpc(sendToMain: (channel: string, ...args: unknown[]) => void): void {
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
  // Paint ack for a per-reveal token — show the HWND now (see commitReveal).
  ipcMain.on('bar:showAck', (e, token: number) => {
    if (!barWindow || e.sender.id !== barWindow.webContents.id) return
    commitReveal(token)
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
  // Renderer-driven retract hold: keep a summoned pill open while a PTT hold /
  // streaming reply / spoken answer is in flight (the cursor is legitimately
  // away from the footprint the whole time). The renderer drops it after a short
  // grace once the exchange ends, and the normal cursor watchdog reclaims the pill.
  ipcMain.on('bar:keepAlive', (_e, active: boolean) => {
    barActivityHold = !!active
  })
  // Bar chat is a VIEWPORT over the main window's single chat engine (kills the
  // duplicate-useChat continuity bug, C3): the bar sends here, main forwards to
  // the main window, whose ChatBridgeHost drives the ONE chat.send(); the main
  // window broadcasts projected state back via chat:publishState → chat:state.
  ipcMain.on('bar:sendChat', (_e, payload: { text: string; fromVoice: boolean }) => {
    sendToMain('chat:barSend', payload)
  })
  // The bar (re)requests the current chat state — e.g. on first mount / each
  // reveal — so it renders the ongoing thread even if it missed prior broadcasts.
  ipcMain.on('bar:requestChatState', () => {
    sendToMain('chat:barRequestState')
  })
  // Main window → bar: projected chat state (history + streaming + status).
  ipcMain.on('chat:publishState', (_e, state: unknown) => {
    send('chat:state', state)
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
  gesture?.dispose() // ends an active gesture → onGestureEnd clears the hold
  gesture = null
  gestureActiveHold = false
  barHiding = false
  stopPeekWatch()
  cancelPendingReveal()
  if (hideFallback) clearTimeout(hideFallback)
  hideFallback = null
  if (barWindow && !barWindow.isDestroyed()) barWindow.destroy()
  barWindow = null
}
