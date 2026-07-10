// Auto-update via electron-updater. Silent by design: downloads in the
// background and installs on the NEXT quit (never force-restarts a listening
// session). When an update is staged we tell the main window (so it can offer a
// "restart to update" affordance) and mark the tray tooltip.
//
// Gated to packaged builds. For local testing, set OMI_UPDATER_DEV=1 and provide
// dev-app-update.yml — that flips forceDevUpdateConfig so the updater runs
// against a dev feed without a real signed release.
import { app, type BrowserWindow } from 'electron'
import { autoUpdater } from 'electron-updater'
import { setTrayUpdateReady } from './tray'

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // every 4h

let started = false

export function initAutoUpdater(getMainWindow: () => BrowserWindow | null): void {
  if (started) return
  const devForced = process.env.OMI_UPDATER_DEV === '1'
  // Only run for real installs (or an explicit dev-forced local test).
  if (!app.isPackaged && !devForced) return
  started = true

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  if (devForced) autoUpdater.forceDevUpdateConfig = true

  autoUpdater.on('update-downloaded', (info) => {
    const version = typeof info?.version === 'string' ? info.version : ''
    const win = getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('update:ready', { version })
    setTrayUpdateReady(true)
    console.log('[updater] update downloaded and staged for next quit:', version)
  })

  // Never crash the app on an updater failure (offline, feed 404, bad signature…).
  autoUpdater.on('error', (err) => {
    console.warn('[updater] error (non-fatal):', err?.message ?? err)
  })

  const check = (): void => {
    autoUpdater.checkForUpdates().catch((e) => {
      console.warn('[updater] check failed (non-fatal):', e?.message ?? e)
    })
  }
  check()
  setInterval(check, CHECK_INTERVAL_MS)
}
