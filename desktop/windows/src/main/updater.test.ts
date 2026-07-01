import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const autoUpdater = {
    autoDownload: false,
    autoInstallOnAppQuit: false,
    setFeedURL: vi.fn(),
    on: vi.fn(),
    checkForUpdatesAndNotify: vi.fn(() => Promise.resolve())
  }
  return {
    app: { isPackaged: true },
    breadcrumbs: [] as unknown[],
    exceptions: [] as unknown[],
    autoUpdater
  }
})

vi.mock('electron', () => ({
  app: mocks.app
}))

vi.mock('./observability', () => ({
  addObservabilityBreadcrumb: vi.fn((...args: unknown[]) => mocks.breadcrumbs.push(args)),
  captureMainException: vi.fn((...args: unknown[]) => mocks.exceptions.push(args))
}))

vi.mock('electron-updater', () => ({
  autoUpdater: mocks.autoUpdater
}))

import {
  DEFAULT_WINDOWS_UPDATE_FEED_URL,
  resetWindowsUpdaterForTests,
  startWindowsUpdater
} from './updater'

async function settle(): Promise<void> {
  await vi.dynamicImportSettled()
  await Promise.resolve()
  await Promise.resolve()
}

describe('windows updater', () => {
  beforeEach(() => {
    resetWindowsUpdaterForTests()
    mocks.app.isPackaged = true
    delete process.env.OMI_UPDATES_ENABLED
    delete process.env.OMI_WINDOWS_UPDATE_FEED_URL
    mocks.breadcrumbs.length = 0
    mocks.exceptions.length = 0
    mocks.autoUpdater.autoDownload = false
    mocks.autoUpdater.autoInstallOnAppQuit = false
    mocks.autoUpdater.setFeedURL.mockClear()
    mocks.autoUpdater.on.mockClear()
    mocks.autoUpdater.checkForUpdatesAndNotify.mockClear()
    vi.useFakeTimers()
    vi.clearAllTimers()
  })

  it('uses a default feed for packaged apps', async () => {
    startWindowsUpdater()
    await settle()

    expect(mocks.autoUpdater.setFeedURL).toHaveBeenCalledWith({
      provider: 'generic',
      url: DEFAULT_WINDOWS_UPDATE_FEED_URL
    })
  })

  it('does not stack listeners or timers when started twice', async () => {
    startWindowsUpdater()
    startWindowsUpdater()
    await settle()

    expect(mocks.autoUpdater.setFeedURL).toHaveBeenCalledTimes(1)
    expect(mocks.autoUpdater.on).toHaveBeenCalledTimes(6)

    await vi.advanceTimersByTimeAsync(15000)
    expect(mocks.autoUpdater.checkForUpdatesAndNotify).toHaveBeenCalledTimes(1)
  })

  it('stays disabled for unpackaged dev runs unless explicitly enabled', () => {
    mocks.app.isPackaged = false

    startWindowsUpdater()

    expect(mocks.autoUpdater.setFeedURL).not.toHaveBeenCalled()
    expect(mocks.breadcrumbs[0]).toEqual([
      'updater.skipped',
      { reason: 'disabled' },
      { category: 'updater' }
    ])
  })
})
