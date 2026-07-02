import { BrowserWindow, screen, shell, app } from 'electron'
import { join } from 'path'
import { settings } from './settings'

// Geometry mirrors the Mac app: main window 1200x800 (min 900x600,
// DesktopHomeView.swift); floating bar is a borderless always-on-top panel
// (FloatingControlBarWindow.swift) whose size is driven by the renderer state.

let mainWindow: BrowserWindow | null = null
let floatingBar: BrowserWindow | null = null
let movePersistTimer: NodeJS.Timeout | null = null

const DEV_URL = process.env['ELECTRON_RENDERER_URL']

function loadRenderer(win: BrowserWindow, page: 'index' | 'floating'): void {
  if (DEV_URL) {
    win.loadURL(`${DEV_URL}/${page === 'index' ? '' : 'floating.html'}`)
  } else {
    win.loadFile(join(__dirname, `../renderer/${page}.html`))
  }
}

// Lock navigation: the renderer is a fixed local bundle. Never let in-page navigation
// (e.g. a markdown link in model output) replace the app shell; cross-origin http(s)
// opens in the system browser instead. Same-origin (dev server / internal) is allowed.
function hardenNavigation(win: BrowserWindow): void {
  win.webContents.on('will-navigate', (e, url) => {
    const here = win.webContents.getURL()
    try {
      if (new URL(url).origin === new URL(here).origin) return
    } catch {
      // fall through to deny
    }
    e.preventDefault()
    try {
      const u = new URL(url)
      if (u.protocol === 'http:' || u.protocol === 'https:') shell.openExternal(u.toString())
    } catch {
      // ignore non-web targets
    }
  })
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

export function getFloatingBar(): BrowserWindow | null {
  return floatingBar
}

export function createMainWindow(): BrowserWindow {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show()
    mainWindow.focus()
    return mainWindow
  }
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: '#0F0F0F',
    title: 'Omi',
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#0F0F0F', symbolColor: '#B0B0B0', height: 38 },
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true
    }
  })
  mainWindow.once('ready-to-show', () => mainWindow?.show())
  mainWindow.on('closed', () => {
    mainWindow = null
  })
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Only ever hand http(s) to the OS, never file://, ms-settings:, etc.
    if (/^https?:\/\//i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  hardenNavigation(mainWindow)
  loadRenderer(mainWindow, 'index')
  return mainWindow
}

// Collapsed pill is 40x14 on Mac; we keep a slightly larger hit target on Windows
// because there is no tracking-area hover wake-up at 14px height.
export const FLOATING_SIZES = {
  pill: { width: 56, height: 22 },
  bar: { width: 210, height: 50 },
  conversation: { width: 430, height: 430 }
}

export function createFloatingBar(): BrowserWindow {
  if (floatingBar && !floatingBar.isDestroyed()) return floatingBar

  const w = FLOATING_SIZES.bar.width
  const h = FLOATING_SIZES.bar.height
  // Resolve the saved position against whichever display currently contains it,
  // then clamp, otherwise a position saved on a now-disconnected monitor would
  // place the bar off-screen and invisible.
  const savedPos = settings.get().floatingBarPosition
  const anchor = savedPos
    ? screen.getDisplayNearestPoint({ x: savedPos.x, y: savedPos.y }).workArea
    : screen.getPrimaryDisplay().workArea
  const x = savedPos
    ? Math.max(anchor.x, Math.min(savedPos.x, anchor.x + anchor.width - w))
    : Math.round(anchor.x + (anchor.width - w) / 2)
  const y = savedPos
    ? Math.max(anchor.y, Math.min(savedPos.y, anchor.y + anchor.height - h))
    : anchor.y + 8

  floatingBar = new BrowserWindow({
    width: w,
    height: FLOATING_SIZES.bar.height,
    x,
    y,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    title: 'Omi Floating Bar',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true,
      backgroundThrottling: false
    }
  })
  // Float above normal windows. The `level` arg is macOS/Windows-only; on Linux/X11
  // this maps to a plain always-on-top (_NET_WM_STATE_ABOVE). skipTaskbar (set above)
  // keeps the borderless bar out of the taskbar/pager. No thickFrame/roundedCorners/
  // vibrancy/backgroundMaterial/type options are set, so nothing Windows-only to guard.
  floatingBar.setAlwaysOnTop(true, 'screen-saver')
  floatingBar.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  floatingBar.on('moved', () => {
    // Electron fires 'moved' rapidly while dragging. Debounce so we do one settings
    // write (synchronous disk I/O + a tray rebuild) per drag, not per move tick.
    if (movePersistTimer) clearTimeout(movePersistTimer)
    movePersistTimer = setTimeout(() => {
      movePersistTimer = null
      if (!floatingBar || floatingBar.isDestroyed()) return
      const [px, py] = floatingBar.getPosition()
      settings.set({ floatingBarPosition: { x: px, y: py } })
    }, 400)
  })
  floatingBar.on('closed', () => {
    floatingBar = null
  })
  floatingBar.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  hardenNavigation(floatingBar)
  loadRenderer(floatingBar, 'floating')
  floatingBar.once('ready-to-show', () => {
    if (settings.get().floatingBarVisible) floatingBar?.show()
  })
  return floatingBar
}

let resizeTween: NodeJS.Timeout | null = null

// Spring-ish ease-out-back (slight overshoot), approximating the Mac's
// spring(response: 0.3, dampingFraction: 0.85) on floating-bar state changes.
function easeOutBack(t: number): number {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

/** Resize the floating bar around a fixed top-center anchor, clamped to the work area.
 *  Animated (~260ms spring) since Windows snaps OS window bounds instantly otherwise. */
export function resizeFloatingBar(width: number, height: number): void {
  if (!floatingBar || floatingBar.isDestroyed()) return
  const win = floatingBar
  const [x, y] = win.getPosition()
  const [curW, curH] = win.getSize()
  const display = screen.getDisplayNearestPoint({ x, y })
  const wa = display.workArea
  const target = { w: Math.round(width), h: Math.round(height) }
  let tx = Math.round(x + (curW - target.w) / 2)
  tx = Math.max(wa.x, Math.min(tx, wa.x + wa.width - target.w))
  const ty = Math.max(wa.y, Math.min(y, wa.y + wa.height - target.h))

  if (resizeTween) {
    clearInterval(resizeTween)
    resizeTween = null
  }
  // Tiny changes (or first show) just snap.
  if (Math.abs(curW - target.w) + Math.abs(curH - target.h) < 6) {
    win.setBounds({ x: tx, y: ty, width: target.w, height: target.h })
    return
  }
  const start = { w: curW, h: curH, x, y }
  const DURATION = 260
  const STEP = 16
  let elapsed = 0
  resizeTween = setInterval(() => {
    if (win.isDestroyed()) {
      if (resizeTween) clearInterval(resizeTween)
      resizeTween = null
      return
    }
    elapsed += STEP
    const t = Math.min(1, elapsed / DURATION)
    const e = easeOutBack(t)
    const w = Math.round(start.w + (target.w - start.w) * e)
    const h = Math.round(start.h + (target.h - start.h) * e)
    const cx = Math.round(start.x + (tx - start.x) * t)
    win.setBounds({ x: cx, y: ty, width: Math.max(8, w), height: Math.max(8, h) })
    if (t >= 1) {
      win.setBounds({ x: tx, y: ty, width: target.w, height: target.h })
      if (resizeTween) clearInterval(resizeTween)
      resizeTween = null
    }
  }, STEP)
}

export function toggleFloatingBar(visible?: boolean): boolean {
  const bar = createFloatingBar()
  const next = visible ?? !bar.isVisible()
  if (next) bar.showInactive()
  else bar.hide()
  settings.set({ floatingBarVisible: next })
  return next
}

export function quitApp(): void {
  app.quit()
}
