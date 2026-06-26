import { BrowserWindow, screen } from 'electron'
import { join } from 'path'

// Screen-edge glow overlay, the Windows counterpart of GlowOverlayWindow.swift:
// a borderless, transparent, click-through, always-on-top window covering the
// work area. Shows a green (focused) or red (distracted) animated border for
// ~2.5s, then hides. Colors/params match GlowBorderView.swift.

let overlay: BrowserWindow | null = null
let hideTimer: NodeJS.Timeout | null = null
let pendingSend = false
let pendingStatus: 'focused' | 'distracted' = 'focused'

const DEV_URL = process.env['ELECTRON_RENDERER_URL']

function activeDisplay() {
  return screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
}

function ensureOverlay(): BrowserWindow {
  if (overlay && !overlay.isDestroyed()) return overlay
  const display = activeDisplay()
  const { x, y, width, height } = display.bounds
  overlay = new BrowserWindow({
    x,
    y,
    width,
    height,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    title: 'Omi Focus Glow',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true,
      backgroundThrottling: false
    }
  })
  // Click-through: on X11 setIgnoreMouseEvents(true) installs an empty input shape
  // (XShape) so pointer events pass to the window underneath. `forward: true` keeps
  // mouse-move messages flowing to Chromium so hover/mouseleave still fire; it is a
  // macOS/Windows-only option and is ignored on Linux, but harmless to pass for parity.
  overlay.setIgnoreMouseEvents(true, { forward: true })
  // The `level` arg is macOS/Windows-only; on Linux/X11 this is a plain always-on-top
  // (_NET_WM_STATE_ABOVE), which is what we want for the overlay. Safe no-op level on Linux.
  overlay.setAlwaysOnTop(true, 'screen-saver')
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  // Same navigation lockdown as the other windows: the glow overlay exposes the
  // preload bridge, so deny window.open and any in-page navigation (it has none).
  overlay.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  overlay.webContents.on('will-navigate', (e) => e.preventDefault())
  if (DEV_URL) overlay.loadURL(`${DEV_URL}/glow.html`)
  else overlay.loadFile(join(__dirname, '../renderer/glow.html'))
  overlay.on('closed', () => {
    overlay = null
  })
  return overlay
}

/** Flash the glow for `status`. Resizes to the current primary display first. */
export function flashGlow(status: 'focused' | 'distracted'): void {
  const win = ensureOverlay()
  const display = activeDisplay()
  win.setBounds(display.bounds)
  pendingStatus = status
  if (win.webContents.isLoading()) {
    // Queue at most one load listener; rapid early flashes must not stack handlers
    // that each fire a glow:show. The single handler sends the latest status.
    if (!pendingSend) {
      pendingSend = true
      win.webContents.once('did-finish-load', () => {
        pendingSend = false
        if (overlay && !overlay.isDestroyed()) overlay.webContents.send('glow:show', { status: pendingStatus })
      })
    }
  } else {
    win.webContents.send('glow:show', { status })
  }
  win.showInactive()
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    if (overlay && !overlay.isDestroyed()) overlay.hide()
  }, 2700)
}

export function disposeGlow(): void {
  if (hideTimer) clearTimeout(hideTimer)
  overlay?.destroy()
  overlay = null
}
