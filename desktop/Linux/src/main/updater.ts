import { app, dialog, BrowserWindow } from 'electron'
import updaterPkg from 'electron-updater'

// Linux auto-update is disabled until maintainers choose the official release
// channel. Keep the electron-updater wiring here, but gate it off so preview
// packages never check a contributor fork's release feed.
//
// On Linux, electron-updater's in-app auto-update only works from a packaged
// AppImage: it reads the running AppImage path from process.env.APPIMAGE, and its
// AppImageUpdater throws "APPIMAGE env is not defined" otherwise. That env var is
// unset in dev and in .deb installs (where app.isPackaged is still true), so we
// must guard on APPIMAGE, not just app.isPackaged, before touching autoUpdater,
// and degrade to a safe no-op so the tray/menu check still resolves cleanly.

const { autoUpdater } = updaterPkg
const LINUX_AUTO_UPDATE_ENABLED = false

// True only when maintainers enable the official Linux update feed and the app
// is running from a packaged AppImage. Dev and .deb builds leave APPIMAGE unset.
const canAutoUpdate = (): boolean => LINUX_AUTO_UPDATE_ENABLED && app.isPackaged && !!process.env.APPIMAGE

let wired = false
let manualNotificationPending = false
let checkInFlight: Promise<UpdateState> | null = null

export interface UpdateState {
  status: 'idle' | 'checking' | 'available' | 'downloading' | 'ready' | 'none' | 'error'
  version?: string
  percent?: number
  error?: string
}

let state: UpdateState = { status: 'idle' }

function broadcast(): void {
  for (const w of BrowserWindow.getAllWindows()) w.webContents.send('updater:state', state)
}

function consumeManualNotification(): boolean {
  if (!manualNotificationPending) return false
  manualNotificationPending = false
  return true
}

function wire(): void {
  if (wired) return
  wired = true
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('checking-for-update', () => {
    state = { status: 'checking' }
    broadcast()
  })
  autoUpdater.on('update-available', (info) => {
    state = { status: 'available', version: info.version }
    broadcast()
    manualNotificationPending = false
  })
  autoUpdater.on('update-not-available', () => {
    state = { status: 'none' }
    broadcast()
    if (consumeManualNotification()) {
      void dialog.showMessageBox({
        type: 'info',
        message: `Omi ${app.getVersion()}`,
        detail: 'You are on the latest version.'
      })
    }
  })
  autoUpdater.on('download-progress', (p) => {
    state = { status: 'downloading', percent: Math.round(p.percent) }
    broadcast()
  })
  autoUpdater.on('update-downloaded', (info) => {
    state = { status: 'ready', version: info.version }
    broadcast()
    manualNotificationPending = false
    dialog
      .showMessageBox({
        type: 'info',
        buttons: ['Restart now', 'Later'],
        defaultId: 0,
        message: 'Update ready',
        detail: `Omi ${info.version} has been downloaded. Restart to install.`
      })
      .then((r) => {
        if (r.response === 0) autoUpdater.quitAndInstall()
      })
      .catch(() => {})
  })
  autoUpdater.on('error', (err) => {
    state = { status: 'error', error: String(err) }
    broadcast()
    if (consumeManualNotification()) {
      void dialog.showMessageBox({ type: 'error', message: 'Update check failed', detail: String(err) })
    }
  })
}

export async function checkForUpdates(manual = false): Promise<UpdateState> {
  if (!canAutoUpdate()) {
    // No in-app updater here yet: the Linux release feed is not configured, dev
    // builds are unpackaged, and .deb installs should use the package manager.
    if (manual) {
      await dialog.showMessageBox({
        type: 'info',
        message: 'Updates',
        detail: app.isPackaged
          ? 'Linux auto-update is disabled until the official release channel is configured. Install updates from the project release page or your package manager.'
          : 'Linux auto-update is disabled in dev builds.'
      })
    }
    return { status: 'idle' }
  }
  wire()
  if (checkInFlight) {
    if (manual) {
      await dialog.showMessageBox({
        type: 'info',
        message: 'Updates',
        detail: 'An update check is already running.'
      })
    }
    return checkInFlight
  }
  manualNotificationPending = manual
  checkInFlight = (async () => {
    try {
      await autoUpdater.checkForUpdates()
    } catch (e) {
      state = { status: 'error', error: String(e) }
      broadcast()
      if (consumeManualNotification()) {
        await dialog.showMessageBox({ type: 'error', message: 'Update check failed', detail: String(e) })
      }
    }
    return state
  })()
  try {
    return await checkInFlight
  } finally {
    checkInFlight = null
  }
}

export function getUpdateState(): UpdateState {
  return state
}

let startupTimer: NodeJS.Timeout | null = null

/** Check shortly after launch (non-blocking), like Sparkle's auto-check. */
export function scheduleStartupCheck(): void {
  // Skip until maintainers enable the official Linux update feed.
  if (!canAutoUpdate()) return
  startupTimer = setTimeout(() => {
    startupTimer = null
    void checkForUpdates(false)
  }, 8000)
  // Don't fire a deferred update check into a tearing-down app.
  app.once('will-quit', () => {
    if (startupTimer) {
      clearTimeout(startupTimer)
      startupTimer = null
    }
  })
}
