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
import { autoUpdater, type CancellationToken } from 'electron-updater'
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
let selectedChannel: WindowsUpdateChannel = 'stable'
let channelGeneration = 0
let pendingUpdate: {
  version: string
  channel: WindowsUpdateChannel
  generation: number
} | null = null
let feedSelector: WindowsUpdateFeedSelector | null = null
let updateCheckTail: Promise<void> = Promise.resolve()
let activeDownload: {
  channel: WindowsUpdateChannel
  generation: number
  version: string
  cancellationToken: CancellationToken
} | null = null

type ElectronUpdateCheckResult = Awaited<ReturnType<typeof autoUpdater.checkForUpdates>>
type UpdateAttempt = { channel: WindowsUpdateChannel; generation: number }

function isCurrentAttempt(attempt: UpdateAttempt): boolean {
  return attempt.channel === selectedChannel && attempt.generation === channelGeneration
}

export function shouldForceDevUpdater(
  isPackaged: boolean,
  env: NodeJS.ProcessEnv = process.env
): boolean {
  return !isPackaged && env.OMI_UPDATER_DEV === '1'
}

/** The update staged for install-on-quit, if any. The update:ready event fires
 * once (usually while nobody is on Settings), so the UI queries this on mount. */
export function getPendingUpdate(): { version: string } | null {
  return pendingUpdate ? { version: pendingUpdate.version } : null
}

async function prepareUpdateFeed(): Promise<void> {
  if (feedSelector) await feedSelector.prepareSelected()
}

function runPreparedUpdateCheck(): Promise<ElectronUpdateCheckResult> {
  const operation = updateCheckTail.then(async (): Promise<ElectronUpdateCheckResult> => {
    if (pendingUpdate && isCurrentAttempt(pendingUpdate)) return null
    if (activeDownload) {
      activeDownload.cancellationToken.cancel()
      activeDownload = null
    }

    const attempt = { channel: selectedChannel, generation: channelGeneration }
    await prepareUpdateFeed()
    if (!isCurrentAttempt(attempt)) return null

    const result = await autoUpdater.checkForUpdates()
    if (!isCurrentAttempt(attempt)) {
      result?.cancellationToken?.cancel()
      return null
    }
    if (!result?.isUpdateAvailable || !result.cancellationToken) return result

    const version = typeof result.updateInfo?.version === 'string' ? result.updateInfo.version : ''
    const download = {
      ...attempt,
      version,
      cancellationToken: result.cancellationToken
    }
    activeDownload = download
    try {
      await autoUpdater.downloadUpdate(download.cancellationToken)
    } finally {
      if (activeDownload === download) activeDownload = null
    }
    return isCurrentAttempt(download) ? result : null
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
  // A runtime environment variable must never redirect a packaged install to a
  // developer-controlled update feed.
  const devForced = shouldForceDevUpdater(app.isPackaged)
  // Only run for real installs (or an explicit dev-forced local test).
  if (!app.isPackaged && !devForced) return
  started = true

  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = false
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
    // electron-updater emits this before downloadUpdate() settles. Accept it
    // only while the matching channel generation still owns the download.
    const download = activeDownload
    const version = typeof info?.version === 'string' ? info.version : ''
    if (!download || !isCurrentAttempt(download) || version !== download.version) return

    pendingUpdate = {
      version,
      channel: download.channel,
      generation: download.generation
    }
    const win = getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('update:ready', { version })
    setTrayUpdateReady(true)
    autoUpdater.autoInstallOnAppQuit = true
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
    channelGeneration += 1
    autoUpdater.autoInstallOnAppQuit = false
    if (activeDownload && !isCurrentAttempt(activeDownload)) {
      const staleDownload = activeDownload
      activeDownload = null
      staleDownload.cancellationToken.cancel()
    }
    if (pendingUpdate && !isCurrentAttempt(pendingUpdate)) {
      pendingUpdate = null
      setTrayUpdateReady(false)
    }
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
