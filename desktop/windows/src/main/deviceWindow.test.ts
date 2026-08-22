import { describe, it, expect, vi } from 'vitest'

vi.mock('electron', () => ({ BrowserWindow: class {} }))
vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }))
vi.mock('../../resources/icon.png?asset', () => ({ default: 'icon.png' }))
vi.mock('./rendererServer', () => ({ rendererBaseUrl: () => null }))
vi.mock('./lifecycle', () => ({ isQuitting: () => false }))
vi.mock('./ipc/deviceBridge', () => ({ emitDeviceEventFromMain: vi.fn() }))
vi.mock('./ipc/omiListen', () => ({ killSessionsForOwner: vi.fn() }))

const { decideDeviceRespawn } = await import('./deviceWindow')

describe('decideDeviceRespawn', () => {
  it('allows respawns until three happen inside the window', () => {
    const now = 100_000
    expect(decideDeviceRespawn([], now).allow).toBe(true)
    expect(decideDeviceRespawn([now - 1_000], now).allow).toBe(true)
    expect(decideDeviceRespawn([now - 2_000, now - 1_000], now).allow).toBe(true)
    // A renderer crash-looping on a bad Bluetooth stack must not respawn forever.
    expect(decideDeviceRespawn([now - 3_000, now - 2_000, now - 1_000], now).allow).toBe(false)
  })

  it('forgets spawns older than the window', () => {
    const now = 100_000
    const old = [now - 61_000, now - 62_000, now - 63_000]
    const decision = decideDeviceRespawn(old, now)
    expect(decision.allow).toBe(true)
    expect(decision.times).toEqual([])
  })

  it('keeps only the in-window timestamps to carry forward', () => {
    const now = 100_000
    const decision = decideDeviceRespawn([now - 70_000, now - 30_000], now)
    expect(decision.times).toEqual([now - 30_000])
  })
})
