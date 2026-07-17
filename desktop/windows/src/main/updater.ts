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
import { getAppSettings, onAppSettingsChanged } from './appSettings'
import { betaOptInToAllowPrerelease, resolveBetaChannelChange } from './updaterChannel'
import type { UpdateCheckResult } from '../shared/types'

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // every 4h

let started = false
let pendingUpdate: { version: string } | null = null

/** The update staged for install-on-quit, if any. The update:ready event fires
 * once (usually while nobody is on Settings), so the UI queries this on mount. */
export function getPendingUpdate(): { version: string } | null {
  return pendingUpdate
}

/**
 * Manual update check for Settings → About. In unpackaged dev the updater never
 * started (see initAutoUpdater's guard), so there's nothing to check — return
 * `unsupported` and let the UI say updates install automatically. When active, run
 * a one-shot check: a staged download reports `update-available`, a newer feed
 * version reports `update-available`, otherwise `up-to-date`. Never throws.
 */
export async function checkForUpdatesNow(): Promise<UpdateCheckResult> {
  const current = app.getVersion()
  if (!started) return { status: 'unsupported', version: current }
  if (pendingUpdate) return { status: 'update-available', version: pendingUpdate.version }
  try {
    const res = await autoUpdater.checkForUpdates()
    const found = typeof res?.updateInfo?.version === 'string' ? res.updateInfo.version : undefined
    if (found && found !== current) return { status: 'update-available', version: found }
    return { status: 'up-to-date', version: current }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    console.warn('[updater] manual check failed (non-fatal):', message)
    return { status: 'error', message }
  }
}

export function initAutoUpdater(getMainWindow: () => BrowserWindow | null): void {
  if (started) return
  const devForced = process.env.OMI_UPDATER_DEV === '1'
  // Only run for real installs (or an explicit dev-forced local test).
  if (!app.isPackaged && !devForced) return
  started = true

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  if (devForced) autoUpdater.forceDevUpdateConfig = true

  // Beta opt-in (Mac's "beta" update channel). GitHub provider only: when the
  // user opts in we serve GitHub *prerelease* builds (our betas); otherwise only
  // promoted stable releases. Read the persisted pref at startup, then keep it in
  // lock-step with live Settings flips (onAppSettingsChanged fires for every
  // write, so resolveBetaChannelChange filters to actual beta-toggle changes and
  // triggers an immediate re-check — opting in shouldn't wait for the 4h timer).
  autoUpdater.allowPrerelease = betaOptInToAllowPrerelease(getAppSettings().betaUpdatesEnabled)

  autoUpdater.on('update-downloaded', (info) => {
    const version = typeof info?.version === 'string' ? info.version : ''
    pendingUpdate = { version }
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
  // Delay the first check so it doesn't compete with startup/renderer load — a
  // fresh update can trigger a full background download.
  setTimeout(check, 45_000)
  setInterval(check, CHECK_INTERVAL_MS)

  // Apply a live "receive beta updates" flip: flip allowPrerelease and re-check
  // now so the newer channel is picked up immediately, not on the next timer.
  onAppSettingsChanged((s) => {
    const { allowPrerelease, changed } = resolveBetaChannelChange(
      autoUpdater.allowPrerelease,
      s.betaUpdatesEnabled
    )
    if (!changed) return
    autoUpdater.allowPrerelease = allowPrerelease
    console.log(
      '[updater] beta channel',
      allowPrerelease ? 'ON (prereleases included)' : 'OFF (stable only)',
      '→ re-checking'
    )
    check()
  })
}
