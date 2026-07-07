// WINDOW MATERIAL: non-transparent, frameless window + setBackgroundMaterial
// ('acrylic'→'mica'→none) = the Win11 DWM system backdrop. That backdrop is the
// only acrylic that actually renders TRANSLUCENT on modern Win11 builds
// (ACCENT_ENABLE_ACRYLICBLURBEHIND, the custom-color path, now paints opaque on
// 22H2+/build 26200). The backdrop is OS-theme-tinted, so a thin CSS black wash
// in the renderer (overlay.css) recolors it toward black while staying
// translucent. transparent:false lets the backdrop composite and DWM auto-round
// the corners. Visual confirmation is manual GUI.
import { app, BrowserWindow, screen } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { computeOverlayBounds, OVERLAY_WIDTH } from './bounds'
import { rendererBaseUrl } from '../rendererServer'

let overlayWindow: BrowserWindow | null = null

// Distinguishes a real app shutdown from the user clicking the overlay's native
// close button: on quit we let the window actually close; otherwise we hide it.
let isQuitting = false
app.on('before-quit', () => {
  isQuitting = true
})

export function getOverlayWindow(): BrowserWindow | null {
  return overlayWindow
}

/**
 * Create the overlay window, hidden. Loads the existing renderer bundle at the
 * `#/overlay` hash route so it shares the default session (Firebase auth +
 * useChat work unchanged). Kept alive for the app lifetime so summoning is
 * instant and the auth/session stay warm.
 */
export function createOverlayWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: OVERLAY_WIDTH,
    height: 200,
    show: false,
    // Hidden title bar, NO native caption buttons (no minimize/close). The window
    // is moved via a CSS drag region in the renderer and dismissed via the global
    // shortcut / Esc only. titleBarStyle 'hidden' keeps the window frame, so Win11
    // still rounds the corners and the Mica/acrylic material renders.
    titleBarStyle: 'hidden',
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: true,
    focusable: true,
    // Pure-black base so any pre-paint frame and the acrylic's inactive fallback
    // read black, not grey. The DWM backdrop composites over this where the
    // renderer is transparent/translucent.
    backgroundColor: '#000000',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      webSecurity: false, // match main window (Omi API CORS workaround)
      backgroundThrottling: false
    }
  })

  // Float above fullscreen-ish apps. 'screen-saver' is the highest standard
  // level; if it proves too aggressive over the taskbar/Start, drop to 'pop-up-menu'.
  win.setAlwaysOnTop(true, 'screen-saver')

  // Exclude the overlay from screen capture (Windows WDA_EXCLUDEFROMCAPTURE). The
  // chat's "what's on my screen" feature grabs a screenshot at send time; without
  // this, the floating bar itself would appear in that capture (and in the user's
  // own screenshots/recordings). It's a transient HUD, so hiding it from capture is
  // what you want.
  win.setContentProtection(true)

  // Tell the renderer when the window gains/loses focus so it can darken the wash
  // in rest mode. Win11 renders the acrylic backdrop with a brighter luminosity
  // layer when the window is inactive; a darker inactive wash (overlay.css)
  // cancels that brightening so the panel stays dark + translucent, instead of
  // flashing the OS's bright inactive tint. BrowserWindow focus/blur is reliable
  // for this, unlike DOM window focus/blur.
  win.on('focus', () => {
    if (!win.isDestroyed()) win.webContents.send('overlay:active', true)
    broadcastOverlayState()
  })
  win.on('blur', () => {
    if (!win.isDestroyed()) win.webContents.send('overlay:active', false)
    broadcastOverlayState()
  })

  // The native close button should HIDE the summon overlay (so the global
  // shortcut can re-open it), not destroy it. Real teardown uses destroy()
  // (main-window close / quit), which bypasses this 'close' handler.
  win.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      hideOverlay()
    }
  })

  win.on('closed', () => {
    overlayWindow = null
  })

  // Surface overlay load failures (e.g. a bad renderer URL) instead of silently
  // leaving an empty window.
  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[overlay] did-fail-load', code, desc, url)
  )

  // Must load from the same origin as the main window (dev server or the
  // production loopback server) — auth/localStorage state is per-origin, so a
  // file:// overlay would always look signed out.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#/overlay`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/index.html#/overlay`)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'), { hash: 'overlay' })
  }

  applyOverlayMaterial(win)
  overlayWindow = win
  return win
}

/**
 * Apply the Win11 DWM system backdrop: acrylic → mica → none. This is the only
 * acrylic that renders TRANSLUCENT on modern Win11 (the custom-color
 * SetWindowCompositionAttribute path paints opaque on build 26200). The backdrop
 * is OS-theme-tinted; overlay.css adds a thin black wash to push it toward black.
 * Wrapped in try/catch because setBackgroundMaterial throws on unsupported
 * platforms/builds (Win10, old Electron).
 */
export function applyOverlayMaterial(win: BrowserWindow): 'acrylic' | 'mica' | 'none' {
  const trySet = (material: 'acrylic' | 'mica'): boolean => {
    try {
      // setBackgroundMaterial exists on Win; guard for type/platform safety.
      const w = win as BrowserWindow & {
        setBackgroundMaterial?: (m: string) => void
      }
      if (typeof w.setBackgroundMaterial !== 'function') return false
      w.setBackgroundMaterial(material)
      return true
    } catch {
      return false
    }
  }

  if (process.platform === 'win32') {
    if (trySet('acrylic')) return 'acrylic'
    if (trySet('mica')) return 'mica'
  }
  return 'none'
}

// --- Summon / dismiss -------------------------------------------------------

const TWEEN_FRAME_MS = 20
// Per-frame fraction of the remaining gap to close (exponential ease). Follows a
// MOVING target smoothly instead of restarting a fresh tween on each report —
// which is what made a live voice transcript's growth lurch.
const TWEEN_EASE = 0.28
const INITIAL_HEIGHT = 200 // BrowserWindow's initial (hidden) height; real size comes from the renderer
const SETTLE_MS = 250 // after an open, snap (don't tween) height reports for this long
let tweenTimer: ReturnType<typeof setInterval> | null = null
// The (continuously updated) height goal the tween eases toward, plus the anchor
// it holds while doing so. A live voice transcript retargets these many times a
// second; the single running loop just follows the latest values (no restart).
let tweenTargetH = INITIAL_HEIGHT
let tweenW = 0
let lastToggle = 0
// True once the renderer has mounted and reported its content height at least
// once. Until then the window holds an unmeasured, wrongly-sized empty frame, so
// the first summon is DEFERRED (pendingSummon) rather than flashing that frame.
let overlayReady = false
let pendingSummon = false
// Last content height the renderer reported. The window opens at this height (no
// flash from a fixed placeholder size), and it persists across hide/show.
let lastContentHeight = INITIAL_HEIGHT
// Until this timestamp, height reports snap instantly instead of tweening, so
// post-open layout settling doesn't animate a resize against the entrance fade.
let snapUntil = 0
// Work area of the display captured at summon, reused by the height tween so a
// mid-stream cursor move to another monitor can't yank the panel across screens.
let activeWorkArea: { x: number; y: number; width: number; height: number } | null = null
// Whether the summon shortcut may open the overlay. Off until onboarding completes
// (the renderer reports the flag via 'overlay:setEnabled'); the overlay's own
// shortcut-setup step ships later.
let overlayEnabled = false

/** Enable/disable summoning. Disabling also hides the overlay if it's open. */
export function setOverlayEnabled(enabled: boolean): void {
  overlayEnabled = enabled
  if (!enabled) {
    hideOverlay()
    return
  }
  // Pre-warm: create + load the overlay (hidden) as soon as it's enabled — i.e.
  // right after sign-in/onboarding — so the FIRST summon is instant instead of
  // paying for window creation + bundle load + React/Firebase mount on activation.
  // Created here (post-sign-in) rather than at cold startup so its Firebase still
  // reads the already-persisted session. The renderer reports its height when it
  // mounts, flipping overlayReady, so a summon during warm-up is handled by the
  // existing pendingSummon path.
  ensureOverlayWindow()
}

/**
 * Get the overlay window, creating it lazily on first summon. Creating it AFTER
 * sign-in (instead of eagerly at startup) means its Firebase reads the
 * already-persisted session, so the overlay opens authenticated — and we avoid
 * the expensive per-summon reload we'd otherwise need to refresh auth. The
 * window then stays warm, so later summons are instant.
 */
function ensureOverlayWindow(): BrowserWindow {
  if (overlayWindow && !overlayWindow.isDestroyed()) return overlayWindow
  return createOverlayWindow()
}

/**
 * Summon the overlay on the display under the cursor. If the renderer hasn't
 * mounted/measured yet (first ever summon), DEFER the actual show until the first
 * height report — otherwise we'd flash an empty, wrongly-sized acrylic frame
 * during the heavy first bundle load. Once warm, this presents instantly.
 */
export function showOverlay(): void {
  const win = ensureOverlayWindow()

  // Capture the display under the cursor ONCE at summon; the height tween reuses
  // it so the panel stays on the display it opened on.
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
  activeWorkArea = display.workArea

  if (!overlayReady) {
    pendingSummon = true
    return
  }
  presentOverlay(win)
}

/** Position at the last measured height, show + focus, and tell the renderer to
 *  play the entrance animation. Chat history is preserved across summons. */
function presentOverlay(win: BrowserWindow): void {
  if (!activeWorkArea) {
    activeWorkArea = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
  }
  win.setBounds(computeOverlayBounds(activeWorkArea, lastContentHeight))
  snapUntil = Date.now() + SETTLE_MS
  win.show()
  win.focus()
  win.webContents.send('overlay:shown')
  broadcastOverlayState()
}

export function hideOverlay(): void {
  const win = overlayWindow
  if (!win || win.isDestroyed()) return
  if (tweenTimer) {
    clearInterval(tweenTimer)
    tweenTimer = null
  }
  // Let the renderer pre-stage its panel to opacity 0 BEFORE we hide, so the next
  // summon fades in cleanly instead of flashing the fully-opaque panel for a frame.
  if (win.isVisible()) win.webContents.send('overlay:willHide')
  win.hide()
  broadcastOverlayState()
}

/**
 * Broadcast that the summon shortcut fired, so any window (e.g. the onboarding
 * shortcut-setup step) can give "it works" feedback. Sent on every accepted
 * toggle — globalShortcut swallows the key globally and focus jumps to the
 * overlay, so a renderer can't observe the press itself.
 */
function broadcastSummoned(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('overlay:summoned')
  }
}

/**
 * Broadcast the overlay's open/focused state to every window so the onboarding
 * voice step can switch between "press the hotkey" and "hold Space". `active`
 * requires the overlay to be both visible and focused (you can only hold-Space
 * when it has focus).
 */
function broadcastOverlayState(): void {
  const win = overlayWindow
  const open = !!(win && !win.isDestroyed() && win.isVisible())
  const active = open && !!win && win.isFocused()
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('overlay:visibility', { open, active })
  }
}

/** Debounced toggle so a rapid double-press doesn't flicker. */
export function toggleOverlay(): void {
  // Gated until the onboarding shortcut step enables it — the shortcut stays
  // registered (so it's claimed) but does nothing until then.
  if (!overlayEnabled) return
  const now = Date.now()
  if (now - lastToggle < 150) return
  lastToggle = now
  broadcastSummoned()
  const win = overlayWindow
  const visible = !!(win && !win.isDestroyed() && win.isVisible())
  // Hide only if it exists and is visible; otherwise summon — showOverlay lazily
  // creates the window on first use (so a null window must NOT short-circuit here).
  if (visible) {
    hideOverlay()
  } else {
    showOverlay()
  }
}

/**
 * Ease the window height toward `contentHeight` (clamped to the display via
 * computeOverlayBounds). Manual tween because Electron ignores setBounds'
 * animate flag on Windows. Width/x/y stay anchored; only height grows downward.
 */
export function setOverlayHeight(contentHeight: number): void {
  lastContentHeight = contentHeight

  // First report ever: the renderer has now mounted + measured. Mark ready, and if
  // a summon was waiting on that, present at the real height now.
  if (!overlayReady) {
    overlayReady = true
    if (pendingSummon) {
      pendingSummon = false
      const w = overlayWindow
      if (w && !w.isDestroyed()) presentOverlay(w)
    }
    return
  }

  const win = overlayWindow
  if (!win || win.isDestroyed() || !win.isVisible()) return

  // Reuse the display captured at summon (fall back to the cursor's display if
  // somehow unset) so the tween never repositions onto a different monitor.
  const workArea =
    activeWorkArea ?? screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
  const target = computeOverlayBounds(workArea, contentHeight)
  const current = win.getBounds()

  // Retarget the (single, continuous) tween toward the latest goal. Updating these
  // every report — instead of cancelling and starting a new tween — is what keeps a
  // fast-growing voice transcript smooth rather than lurchy. Width only (x/y are
  // read LIVE per frame in applyTweenHeight so a drag is never fought).
  tweenTargetH = target.height
  tweenW = target.width

  if (current.height === target.height) return

  // Snap instantly (no tween) during the post-open settle window OR on a large
  // GROW. The big one is the first message: it inserts the whole message list above
  // the input, so the window must grow a lot at once. Tweening that leaves the
  // window shorter than the content for a few hundred ms, clipping the input row off
  // the bottom until the tween catches up (it "vanishes, then comes back"). Snapping
  // grows the window in one step so the input is never clipped. Small streaming
  // grows (and shrinks) still tween for smoothness.
  const bigGrow = target.height - current.height > 40
  if (Date.now() < snapUntil || bigGrow) {
    if (tweenTimer) {
      clearInterval(tweenTimer)
      tweenTimer = null
    }
    applyTweenHeight(win, tweenTargetH)
    return
  }

  // A tween is already easing toward the (now-updated) goal — let it keep running
  // instead of restarting it. Otherwise start one: each frame closes a fraction of
  // the remaining gap toward the latest tweenTargetH (exponential ease), so a moving
  // target stays smooth and it always lands exactly on the goal.
  if (tweenTimer) return
  tweenTimer = setInterval(() => {
    const w = overlayWindow
    if (!w || w.isDestroyed()) {
      if (tweenTimer) clearInterval(tweenTimer)
      tweenTimer = null
      return
    }
    const cur = w.getBounds().height
    const diff = tweenTargetH - cur
    if (Math.abs(diff) <= 1) {
      applyTweenHeight(w, tweenTargetH)
      if (tweenTimer) clearInterval(tweenTimer)
      tweenTimer = null
      return
    }
    applyTweenHeight(w, Math.round(cur + diff * TWEEN_EASE))
  }, TWEEN_FRAME_MS)
}

// Apply a new window HEIGHT while preserving the window's LIVE x/y, so the resize
// only ever changes height and never rewrites position. This is what stops the
// tween from fighting an in-progress user DRAG: the old code wrote a captured
// x/y every 20ms, so dragging the window while it was resizing (e.g. during a
// streaming reply) yanked it back to the pre-drag spot each frame — the glitch.
// We still nudge up if growing would run off the bottom of the captured work
// area, so a tall reply stays on-screen.
function applyTweenHeight(win: BrowserWindow, height: number): void {
  const b = win.getBounds()
  let y = b.y
  const wa = activeWorkArea
  if (wa && y + height > wa.y + wa.height) y = Math.max(wa.y, wa.y + wa.height - height)
  win.setBounds({ x: b.x, y, width: tweenW, height })
}
