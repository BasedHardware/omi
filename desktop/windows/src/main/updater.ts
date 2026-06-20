import { app } from 'electron'
import { autoUpdater } from 'electron-updater'
import { addObservabilityBreadcrumb, captureMainException } from './observability'

const CHECK_DELAY_MS = 15000
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000

function updatesEnabled(): boolean {
  return app.isPackaged || process.env.OMI_UPDATES_ENABLED === '1'
}

function feedUrl(): string | null {
  const value = process.env.OMI_WINDOWS_UPDATE_FEED_URL?.trim()
  return value || null
}

export function startWindowsUpdater(): void {
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
