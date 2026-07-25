// Auto-update via electron-updater. Silent by design: downloads in the
// background and installs on the next quit (never force-restarts a listening
// session). When an update is staged we tell the main window so it can offer a
// "restart to update" action and mark the tray tooltip.
//
// Production checks first resolve an immutable Windows release directory from
// the backend, then use electron-updater's generic provider for latest.yml and
// its installer. This avoids GitHubProvider's repository-wide /releases/latest,
// which can select a macOS release in this multi-platform repository.
//
// For local testing, set OMI_UPDATER_DEV=1 and provide dev-app-update.yml. That
// keeps electron-updater on the developer-supplied feed.
import { app, net, type BrowserWindow } from 'electron'
import { autoUpdater } from 'electron-updater'
import { setTrayUpdateReady } from './tray'
import { markQuitting } from './lifecycle'
import { getAppSettings, onAppSettingsChanged } from './appSettings'
import { betaOptInToUpdateChannel, resolveBetaChannelChange } from './updaterChannel'
import {
  resolveWindowsUpdateFeedUrl,
  WindowsUpdateFeedSelector,
  type WindowsUpdateChannel
} from './windowsUpdateFeed'
import type { UpdateCheckResult } from '../shared/types'

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000
const OMI_API_BASE = import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me'

let started = false
let pendingUpdate: { version: string } | null = null
let selectedChannel: WindowsUpdateChannel = 'stable'
let feedSelector: WindowsUpdateFeedSelector | null = null
let updateCheckTail: Promise<void> = Promise.resolve()

type ElectronUpdateCheckResult = Awaited<ReturnType<typeof autoUpdater.checkForUpdates>>

/** The update staged for install-on-quit, if any. The update:ready event fires
 * once (usually while nobody is on Settings), so the UI queries this on mount. */
export function getPendingUpdate(): { version: string } | null {
  return pendingUpdate
}

async function prepareUpdateFeed(): Promise<void> {
  if (feedSelector) await feedSelector.prepareSelected()
}

function runPreparedUpdateCheck(): Promise<ElectronUpdateCheckResult> {
  const operation = updateCheckTail.then(async (): Promise<ElectronUpdateCheckResult> => {
    await prepareUpdateFeed()
    return autoUpdater.checkForUpdates()
  })
  updateCheckTail = operation.then(
    (): undefined => undefined,
    (): undefined => undefined
  )
  return operation
}

/**
 * Manual update check for Settings -> About. In unpackaged dev or on an
 * unsupported platform the updater never starts, so there is nothing to check.
 * When active, a staged download reports `update-available`, a newer feed
 * version reports `update-available`, otherwise `up-to-date`. Never throws.
 */
export async function checkForUpdatesNow(): Promise<UpdateCheckResult> {
  const current = app.getVersion()
  if (!started) return { status: 'unsupported', version: current }
  if (pendingUpdate) return { status: 'update-available', version: pendingUpdate.version }
  try {
    const res = await runPreparedUpdateCheck()
    const found = typeof res?.updateInfo?.version === 'string' ? res.updateInfo.version : undefined
    if (found && found !== current) return { status: 'update-available', version: found }
    return { status: 'up-to-date', version: current }
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    console.warn('[updater] manual check failed (non-fatal):', message)
    return { status: 'error', message }
  }
}

/**
 * Install the staged update now (Settings -> About "Restart to update"). Plain
 * app.quit() relies on autoInstallOnAppQuit, which runs the NSIS installer
 * without relaunching. quitAndInstall(silent, forceRunAfter) installs and comes
 * back up on the new version, which is what the button promises.
 */
export function installUpdateNow(): boolean {
  if (!started || !pendingUpdate) return false
  markQuitting()
  autoUpdater.quitAndInstall(true, true)
  return true
}

export function initAutoUpdater(
  getMainWindow: () => BrowserWindow | null,
  platform: NodeJS.Platform = process.platform
): void {
  if (started || platform !== 'win32') return
  const devForced = process.env.OMI_UPDATER_DEV === '1'
  if (!app.isPackaged && !devForced) return
  started = true

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  if (devForced) autoUpdater.forceDevUpdateConfig = true

  selectedChannel = betaOptInToUpdateChannel(getAppSettings().betaUpdatesEnabled)
  // Kept aligned for dev feeds and electron-updater's public state. Production
  // channel selection is owned by the backend resolver below.
  autoUpdater.allowPrerelease = selectedChannel === 'beta'
  if (!devForced) {
    feedSelector = new WindowsUpdateFeedSelector(
      selectedChannel,
      (channel): Promise<string> => resolveWindowsUpdateFeedUrl(OMI_API_BASE, channel, net.fetch),
      (feedUrl): void => {
        autoUpdater.setFeedURL({ provider: 'generic', url: feedUrl })
      }
    )
  }

  autoUpdater.on('update-downloaded', (info) => {
    const version = typeof info?.version === 'string' ? info.version : ''
    pendingUpdate = { version }
    const win = getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('update:ready', { version })
    setTrayUpdateReady(true)
    console.log('[updater] update downloaded and staged for next quit:', version)
  })

  autoUpdater.on('error', (err) => {
    console.warn('[updater] error (non-fatal):', err?.message ?? err)
  })

  const check = async (): Promise<void> => {
    try {
      await runPreparedUpdateCheck()
    } catch (e) {
      console.warn(
        '[updater] check failed (non-fatal):',
        e instanceof Error ? e.message : String(e)
      )
    }
  }

  // Delay the first check so it does not compete with startup/renderer load.
  setTimeout((): void => {
    void check()
  }, 45_000)
  setInterval((): void => {
    void check()
  }, CHECK_INTERVAL_MS)

  // Apply a live beta toggle immediately instead of waiting for the 4h timer.
  onAppSettingsChanged((settings) => {
    const change = resolveBetaChannelChange(selectedChannel, settings.betaUpdatesEnabled)
    if (!change.changed) return
    selectedChannel = change.channel
    autoUpdater.allowPrerelease = selectedChannel === 'beta'
    feedSelector?.select(selectedChannel)
    console.log(
      '[updater] beta channel',
      selectedChannel === 'beta' ? 'ON (prereleases included)' : 'OFF (stable only)',
      '-> re-checking'
    )
    void check()
  })
}
