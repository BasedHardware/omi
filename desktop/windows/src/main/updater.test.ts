import { describe, it, expect, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Point the real app-settings store at a throwaway userData dir so the beta
// opt-in genuinely persists + fires onAppSettingsChanged into the updater's live
// listener — this test exercises the real glue in updater.ts (init reads the
// pref; a live flip moves the channel + re-checks), not a re-declared copy.
const dir = mkdtempSync(join(tmpdir(), 'omi-updater-'))

// Fake electron-updater: a plain object we inspect. checkForUpdates resolves an
// (unused) result so the listener's re-check is harmless under fake timers.
// vi.hoisted so the object exists both for the (hoisted) mock factory and the
// test-body assertions.
const autoUpdater = vi.hoisted(() => ({
  allowPrerelease: false,
  autoDownload: false,
  autoInstallOnAppQuit: false,
  forceDevUpdateConfig: false,
  on: vi.fn(),
  checkForUpdates: vi.fn().mockResolvedValue({ updateInfo: { version: '9.9.9' } }),
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
  }
}))
vi.mock('./tray', () => ({ setTrayUpdateReady: vi.fn() }))

import { initAutoUpdater, installUpdateNow, getPendingUpdate } from './updater'
import { setAppSettings } from './appSettings'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

describe('updater beta channel wiring', () => {
  it('reads the persisted opt-in at init and flips allowPrerelease on live changes', () => {
    // Fake timers so init's 45s/4h checks stay dormant — the only checkForUpdates
    // calls we assert on come from the beta-toggle listener.
    vi.useFakeTimers()

    // Persist the opt-in BEFORE init so initAutoUpdater picks up beta at startup.
    setAppSettings({ betaUpdatesEnabled: true })
    initAutoUpdater(() => null)
    expect(autoUpdater.allowPrerelease).toBe(true)

    // Live opt-out → stable + an immediate re-check.
    autoUpdater.checkForUpdates.mockClear()
    setAppSettings({ betaUpdatesEnabled: false })
    expect(autoUpdater.allowPrerelease).toBe(false)
    expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1)

    // Live opt-in again → beta + re-check.
    autoUpdater.checkForUpdates.mockClear()
    setAppSettings({ betaUpdatesEnabled: true })
    expect(autoUpdater.allowPrerelease).toBe(true)
    expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1)

    // An UNRELATED settings write must not touch the lever or re-check.
    autoUpdater.checkForUpdates.mockClear()
    setAppSettings({ closeToTrayNoticeShown: true })
    expect(autoUpdater.allowPrerelease).toBe(true)
    expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled()

    vi.useRealTimers()
  })
})

// #10509: "Restart to update" used to just quit the app and trust
// autoInstallOnAppQuit, which installs without ever relaunching — and does
// nothing at all when no update is staged, so users reopened on the old version.
describe('installUpdateNow', () => {
  it('does nothing when no update is staged', () => {
    expect(getPendingUpdate()).toBeNull()
    expect(installUpdateNow()).toBe(false)
    expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled()
  })

  it('installs and relaunches once an update is downloaded', () => {
    const downloaded = autoUpdater.on.mock.calls.find(
      (c) => c[0] === 'update-downloaded'
    )?.[1] as (info: { version: string }) => void
    expect(downloaded).toBeTypeOf('function')
    downloaded({ version: '2.0.0' })

    expect(getPendingUpdate()).toEqual({ version: '2.0.0' })
    expect(installUpdateNow()).toBe(true)
    // isSilent + isForceRunAfter: install without a wizard, come back up on the
    // new version instead of leaving the user with a closed app.
    expect(autoUpdater.quitAndInstall).toHaveBeenCalledWith(true, true)
  })
})
