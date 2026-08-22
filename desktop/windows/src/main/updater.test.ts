import { describe, it, expect, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'omi-updater-'))

const feedFetch = vi.hoisted(() =>
  vi.fn(async (input: string | URL | Request) => {
    const channel = new URL(String(input)).searchParams.get('channel')
    const version = channel === 'beta' ? '1.0.19' : '1.0.1'
    return new Response(
      JSON.stringify({
        requested_channel: channel,
        served_channel: channel,
        version,
        feed_url: `https://github.com/BasedHardware/omi/releases/download/v${version}-windows/`
      }),
      { headers: { 'Content-Type': 'application/json' } }
    )
  })
)

const autoUpdater = vi.hoisted(() => ({
  allowPrerelease: false,
  autoDownload: false,
  autoInstallOnAppQuit: false,
  forceDevUpdateConfig: false,
  setFeedURL: vi.fn(),
  on: vi.fn(),
  checkForUpdates: vi.fn().mockResolvedValue({ updateInfo: { version: '9.9.9' } }),
  downloadUpdate: vi.fn().mockResolvedValue([]),
  quitAndInstall: vi.fn()
}))
vi.mock('electron-updater', () => ({ autoUpdater }))
vi.mock('electron', () => ({
  app: {
    getPath: (): string => dir,
    getVersion: (): string => '1.0.0',
    isPackaged: true,
    on: (): void => {}
  },
  globalShortcut: {
    register: (): boolean => true,
    unregister: (): void => {},
    isRegistered: (): boolean => false
  },
  net: { fetch: feedFetch }
}))
vi.mock('./tray', () => ({ setTrayUpdateReady: vi.fn() }))

import {
  checkForUpdatesNow,
  getPendingUpdate,
  initAutoUpdater,
  installUpdateNow,
  shouldForceDevUpdater
} from './updater'
import { setAppSettings } from './appSettings'

function deferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
} {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

afterAll(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('updater feed and beta channel wiring', () => {
  it('never enables the developer feed in a packaged build', () => {
    expect(shouldForceDevUpdater(true, { OMI_UPDATER_DEV: '1' })).toBe(false)
    expect(shouldForceDevUpdater(false, { OMI_UPDATER_DEV: '1' })).toBe(true)
  })

  it('stays Windows-only and switches immutable feeds on live beta changes', async () => {
    vi.useFakeTimers()

    initAutoUpdater(() => null, 'linux')
    expect(autoUpdater.on).not.toHaveBeenCalled()
    expect(autoUpdater.setFeedURL).not.toHaveBeenCalled()

    setAppSettings({ betaUpdatesEnabled: true })
    initAutoUpdater(() => null, 'win32')
    expect(autoUpdater.allowPrerelease).toBe(true)

    autoUpdater.checkForUpdates.mockClear()
    autoUpdater.setFeedURL.mockClear()
    feedFetch.mockClear()
    setAppSettings({ betaUpdatesEnabled: false })
    await vi.waitFor(() => expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1))
    expect(autoUpdater.allowPrerelease).toBe(false)
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith({
      provider: 'generic',
      url: 'https://github.com/BasedHardware/omi/releases/download/v1.0.1-windows/'
    })

    autoUpdater.checkForUpdates.mockClear()
    autoUpdater.setFeedURL.mockClear()
    feedFetch.mockClear()
    setAppSettings({ betaUpdatesEnabled: true })
    await vi.waitFor(() => expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1))
    expect(autoUpdater.allowPrerelease).toBe(true)
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith({
      provider: 'generic',
      url: 'https://github.com/BasedHardware/omi/releases/download/v1.0.19-windows/'
    })

    autoUpdater.checkForUpdates.mockClear()
    autoUpdater.setFeedURL.mockClear()
    feedFetch.mockClear()
    setAppSettings({ closeToTrayNoticeShown: true })
    await Promise.resolve()
    expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled()
    expect(autoUpdater.setFeedURL).not.toHaveBeenCalled()
    expect(feedFetch).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('drops an in-flight result and rechecks when the selected channel changes', async () => {
    const cancellationToken = { cancel: vi.fn() }
    const firstCheck = deferred<{
      isUpdateAvailable: true
      updateInfo: { version: string }
      cancellationToken: { cancel: ReturnType<typeof vi.fn> }
    }>()
    autoUpdater.checkForUpdates.mockReset()
    autoUpdater.checkForUpdates
      .mockImplementationOnce(() => firstCheck.promise)
      .mockResolvedValue({ updateInfo: { version: '9.9.9' } })
    autoUpdater.downloadUpdate.mockClear()
    autoUpdater.setFeedURL.mockClear()

    setAppSettings({ betaUpdatesEnabled: false })
    await vi.waitFor(() => expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1))
    setAppSettings({ betaUpdatesEnabled: true })
    await Promise.resolve()
    expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1)

    firstCheck.resolve({
      isUpdateAvailable: true,
      updateInfo: { version: '1.0.1' },
      cancellationToken
    })
    await vi.waitFor(() => expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(2))
    expect(cancellationToken.cancel).toHaveBeenCalledOnce()
    expect(autoUpdater.downloadUpdate).not.toHaveBeenCalledWith(cancellationToken)
    expect(autoUpdater.setFeedURL).toHaveBeenLastCalledWith({
      provider: 'generic',
      url: 'https://github.com/BasedHardware/omi/releases/download/v1.0.19-windows/'
    })
  })

  it('fails a manual check closed when feed resolution is unavailable', async () => {
    autoUpdater.checkForUpdates.mockClear()
    feedFetch.mockRejectedValueOnce(new Error('resolver unavailable'))

    await expect(checkForUpdatesNow()).resolves.toEqual({
      status: 'error',
      message: 'resolver unavailable'
    })
    expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled()
  })
})

describe('installUpdateNow', () => {
  it('clears and ignores a beta download that finishes after opting out', async () => {
    const betaDownload = deferred<string[]>()
    const cancellationToken = { cancel: vi.fn() }
    autoUpdater.checkForUpdates.mockReset()
    autoUpdater.checkForUpdates
      .mockResolvedValueOnce({
        isUpdateAvailable: true,
        updateInfo: { version: '2.0.0' },
        cancellationToken
      })
      .mockResolvedValue({ updateInfo: { version: '1.0.1' } })
    autoUpdater.downloadUpdate.mockReset()
    autoUpdater.downloadUpdate.mockReturnValueOnce(betaDownload.promise)
    autoUpdater.autoInstallOnAppQuit = true

    setAppSettings({ betaUpdatesEnabled: true })
    const checking = checkForUpdatesNow()
    await vi.waitFor(() =>
      expect(autoUpdater.downloadUpdate).toHaveBeenCalledWith(cancellationToken)
    )

    const downloaded = autoUpdater.on.mock.calls.find(
      (call) => call[0] === 'update-downloaded'
    )?.[1] as (info: { version: string }) => void
    downloaded({ version: '2.0.0' })
    expect(getPendingUpdate()).toEqual({ version: '2.0.0' })
    expect(autoUpdater.autoInstallOnAppQuit).toBe(true)

    setAppSettings({ betaUpdatesEnabled: false })
    expect(cancellationToken.cancel).toHaveBeenCalledOnce()
    expect(getPendingUpdate()).toBeNull()
    expect(autoUpdater.autoInstallOnAppQuit).toBe(false)

    downloaded({ version: '2.0.0' })
    expect(getPendingUpdate()).toBeNull()

    betaDownload.resolve([])
    await checking
    downloaded({ version: '2.0.0' })

    expect(getPendingUpdate()).toBeNull()
    expect(autoUpdater.autoInstallOnAppQuit).toBe(false)
    expect(installUpdateNow()).toBe(false)
  })

  it('does nothing when no update is staged', () => {
    expect(getPendingUpdate()).toBeNull()
    expect(installUpdateNow()).toBe(false)
    expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled()
  })

  it('installs and relaunches once the current channel update is downloaded', async () => {
    const stableDownload = deferred<string[]>()
    const cancellationToken = { cancel: vi.fn() }
    autoUpdater.checkForUpdates.mockReset()
    autoUpdater.checkForUpdates.mockResolvedValueOnce({
      isUpdateAvailable: true,
      updateInfo: { version: '2.0.0' },
      cancellationToken
    })
    autoUpdater.downloadUpdate.mockReset()
    autoUpdater.downloadUpdate.mockReturnValueOnce(stableDownload.promise)

    const checking = checkForUpdatesNow()
    await vi.waitFor(() =>
      expect(autoUpdater.downloadUpdate).toHaveBeenCalledWith(cancellationToken)
    )
    const downloaded = autoUpdater.on.mock.calls.find(
      (call) => call[0] === 'update-downloaded'
    )?.[1] as (info: { version: string }) => void
    expect(downloaded).toBeTypeOf('function')
    downloaded({ version: '2.0.0' })
    stableDownload.resolve([])
    await checking

    expect(getPendingUpdate()).toEqual({ version: '2.0.0' })
    expect(installUpdateNow()).toBe(true)
    expect(autoUpdater.quitAndInstall).toHaveBeenCalledWith(true, true)
  })
})
