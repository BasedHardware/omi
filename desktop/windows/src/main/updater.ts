import { app } from 'electron'
import { addObservabilityBreadcrumb, captureMainException } from './observability'

const CHECK_DELAY_MS = 15000
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000
export const DEFAULT_WINDOWS_UPDATE_FEED_URL =
  'https://github.com/BasedHardware/omi/releases/latest/download'

type AutoUpdater = (typeof import('electron-updater'))['autoUpdater']

let updaterStarted = false

function updatesEnabled(): boolean {
  return app.isPackaged || process.env.OMI_UPDATES_ENABLED === '1'
}

function feedUrl(): string | null {
  const value = process.env.OMI_WINDOWS_UPDATE_FEED_URL?.trim()
  return value || DEFAULT_WINDOWS_UPDATE_FEED_URL
}

export function startWindowsUpdater(): void {
  if (updaterStarted) return
  // The feed and packaging here are Windows-specific (NSIS artifacts on the
  // GitHub release feed). Packaged macOS/Linux builds of this package must
  // never initialize electron-updater or register periodic checks.
  if (process.platform !== 'win32') {
    addObservabilityBreadcrumb(
      'updater.skipped',
      { reason: 'unsupported_platform', platform: process.platform },
      { category: 'updater' }
    )
    return
  }
  if (!updatesEnabled()) {
    addObservabilityBreadcrumb('updater.skipped', { reason: 'disabled' }, { category: 'updater' })
    return
  }

  const url = feedUrl()
  if (!url) {
    addObservabilityBreadcrumb(
      'updater.skipped',
      { reason: 'missing_feed_url' },
      { category: 'updater', level: 'warning' }
    )
    return
  }

  void startWindowsUpdaterWithFeed(url)
}

async function loadAutoUpdater(): Promise<AutoUpdater | null> {
  try {
    const updater = await import('electron-updater')
    return updater.autoUpdater
  } catch (error) {
    captureMainException('updater.load_failed', error, {}, 'warning')
    return null
  }
}

async function startWindowsUpdaterWithFeed(url: string): Promise<void> {
  if (updaterStarted) return
  updaterStarted = true
  const autoUpdater = await loadAutoUpdater()
  if (!autoUpdater) return

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.setFeedURL({ provider: 'generic', url })

  autoUpdater.on('checking-for-update', () => {
    addObservabilityBreadcrumb('updater.checking', {}, { category: 'updater' })
  })
  autoUpdater.on('update-available', (info) => {
    addObservabilityBreadcrumb(
      'updater.update_available',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('update-not-available', (info) => {
    addObservabilityBreadcrumb(
      'updater.update_not_available',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('download-progress', (progress) => {
    addObservabilityBreadcrumb(
      'updater.download_progress',
      { percent: Math.round(progress.percent) },
      { category: 'updater' }
    )
  })
  autoUpdater.on('update-downloaded', (info) => {
    addObservabilityBreadcrumb(
      'updater.update_downloaded',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('error', (error) => {
    captureMainException('updater.error', error)
  })

  const check = (): void => {
    void autoUpdater.checkForUpdatesAndNotify().catch((error) => {
      captureMainException('updater.check_failed', error)
    })
  }
  setTimeout(check, CHECK_DELAY_MS)
  setInterval(check, CHECK_INTERVAL_MS)
}

export function resetWindowsUpdaterForTests(): void {
  updaterStarted = false
}
