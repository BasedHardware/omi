import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.stubGlobal('process', { ...process, platform: 'linux' })

const pruneAppUsage = vi.fn()
const addAppUsage = vi.fn()
const getForegroundExePath = vi.fn(() => '/usr/bin/code')
const subscribeForegroundChange = vi.fn(() => () => {})

vi.mock('../ipc/db', () => ({
  pruneAppUsage: (...args: unknown[]) => pruneAppUsage(...args),
  addAppUsage: (...args: unknown[]) => addAppUsage(...args)
}))
vi.mock('./nativeForeground', () => ({
  getForegroundExePath: () => getForegroundExePath(),
  subscribeForegroundChange: (cb: () => void) => subscribeForegroundChange(cb)
}))
vi.mock('./usageSettings', () => ({
  getUsageSettings: () => ({ enabled: true, retentionDays: 30 })
}))
vi.mock('./usageRetention', () => ({
  usageCutoff: () => 0
}))

beforeEach(() => {
  vi.resetModules()
  pruneAppUsage.mockClear()
  addAppUsage.mockClear()
  getForegroundExePath.mockClear()
  subscribeForegroundChange.mockClear()
})

afterEach(async () => {
  const m = await import('./foregroundMonitor')
  m.stopForegroundMonitor()
})

describe('foregroundMonitor on linux', () => {
  it('starts (does not win32-gate) and prunes', async () => {
    const m = await import('./foregroundMonitor')
    m.startForegroundMonitor()
    expect(pruneAppUsage).toHaveBeenCalledTimes(1)
    expect(subscribeForegroundChange).toHaveBeenCalledTimes(1)
    m.stopForegroundMonitor()
  })
})
