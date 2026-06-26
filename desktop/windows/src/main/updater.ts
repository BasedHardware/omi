import { app } from 'electron'
import { addObservabilityBreadcrumb, captureMainException } from './observability'
import type { WindowsUpdateStatus } from '../shared/types'

const CHECK_DELAY_MS = 15000
const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000

type AutoUpdater = (typeof import('electron-updater'))['autoUpdater']
type UpdateInfo = { version: string }
type ProgressInfo = { percent: number }

let updaterInstance: AutoUpdater | null = null
let status: WindowsUpdateStatus = {
  enabled: false,
  configured: false,
  feedUrl: null,
  checking: false,
  downloaded: false,
  lastEvent: null,
  lastVersion: null,
  lastError: null
}

export function updatesEnabled(): boolean {
  return app.isPackaged || process.env.OMI_UPDATES_ENABLED === '1'
}

export function feedUrl(): string | null {
  const value = process.env.OMI_WINDOWS_UPDATE_FEED_URL?.trim()
  return value || null
}

function setUpdateStatus(patch: Partial<WindowsUpdateStatus>): void {
  status = {
    ...status,
    enabled: updatesEnabled(),
    configured: Boolean(feedUrl()),
    feedUrl: feedUrl(),
    ...patch
  }
}

export function getWindowsUpdateStatus(): WindowsUpdateStatus {
  setUpdateStatus({})
  return status
}

export function startWindowsUpdater(): void {
  setUpdateStatus({})
  if (!updatesEnabled()) {
    setUpdateStatus({ lastEvent: 'disabled' })
    addObservabilityBreadcrumb('updater.skipped', { reason: 'disabled' }, { category: 'updater' })
    return
  }

  const url = feedUrl()
  if (!url) {
    setUpdateStatus({ lastEvent: 'missing_feed_url' })
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
    setUpdateStatus({ lastEvent: 'load_failed', lastError: (error as Error).message })
    captureMainException('updater.load_failed', error, {}, 'warning')
    return null
  }
}

async function startWindowsUpdaterWithFeed(url: string): Promise<void> {
  const autoUpdater = await loadAutoUpdater()
  if (!autoUpdater) return
  updaterInstance = autoUpdater

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.setFeedURL({ provider: 'generic', url })

  autoUpdater.on('checking-for-update', () => {
    setUpdateStatus({ checking: true, lastEvent: 'checking', lastError: null })
    addObservabilityBreadcrumb('updater.checking', {}, { category: 'updater' })
  })
  autoUpdater.on('update-available', (info: UpdateInfo) => {
    setUpdateStatus({
      checking: false,
      lastEvent: 'update_available',
      lastVersion: info.version,
      lastError: null
    })
    addObservabilityBreadcrumb(
      'updater.update_available',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    setUpdateStatus({
      checking: false,
      lastEvent: 'update_not_available',
      lastVersion: info.version,
      lastError: null
    })
    addObservabilityBreadcrumb(
      'updater.update_not_available',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('download-progress', (progress: ProgressInfo) => {
    setUpdateStatus({ lastEvent: 'download_progress', lastError: null })
    addObservabilityBreadcrumb(
      'updater.download_progress',
      { percent: Math.round(progress.percent) },
      { category: 'updater' }
    )
  })
  autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
    setUpdateStatus({
      downloaded: true,
      lastEvent: 'update_downloaded',
      lastVersion: info.version,
      lastError: null
    })
    addObservabilityBreadcrumb(
      'updater.update_downloaded',
      { version: info.version },
      { category: 'updater' }
    )
  })
  autoUpdater.on('error', (error) => {
    setUpdateStatus({
      checking: false,
      lastEvent: 'error',
      lastError: error.message
    })
    captureMainException('updater.error', error)
  })

  const check = (): void => {
    void autoUpdater.checkForUpdatesAndNotify().catch((error) => {
      setUpdateStatus({
        checking: false,
        lastEvent: 'check_failed',
        lastError: (error as Error).message
      })
      captureMainException('updater.check_failed', error)
    })
  }
  setTimeout(check, CHECK_DELAY_MS)
  setInterval(check, CHECK_INTERVAL_MS)
}

export async function checkWindowsUpdaterNow(): Promise<WindowsUpdateStatus> {
  if (!updatesEnabled()) {
    setUpdateStatus({ lastEvent: 'disabled' })
    return getWindowsUpdateStatus()
  }
  const url = feedUrl()
  if (!url) {
    setUpdateStatus({ lastEvent: 'missing_feed_url' })
    return getWindowsUpdateStatus()
  }
  if (!updaterInstance) await startWindowsUpdaterWithFeed(url)
  if (!updaterInstance) return getWindowsUpdateStatus()
  setUpdateStatus({ checking: true, lastEvent: 'checking', lastError: null })
  try {
    await updaterInstance.checkForUpdatesAndNotify()
  } catch (error) {
    setUpdateStatus({
      checking: false,
      lastEvent: 'check_failed',
      lastError: (error as Error).message
    })
    captureMainException('updater.check_failed', error)
  }
  return getWindowsUpdateStatus()
}
