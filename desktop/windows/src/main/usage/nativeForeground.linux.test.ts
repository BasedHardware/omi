import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.stubGlobal('process', { ...process, platform: 'linux' })

// Mock the Linux unit so the test needs no real X server.
vi.mock('./linuxForeground', () => ({
  linuxAvailable: () => true,
  getLinuxForegroundExePath: () => '/usr/bin/code',
  getLinuxForegroundInfo: () => ({ handle: '0x1', exePath: '/usr/bin/code', className: null }),
  getLinuxForegroundTitle: () => 'plan.md — Code'
}))

beforeEach(() => vi.resetModules())

describe('nativeForeground on linux with X11 available', () => {
  it('returns the real exe path', async () => {
    const m = await import('./nativeForeground')
    expect(m.getForegroundExePath()).toBe('/usr/bin/code')
  })
  it('returns the real window info', async () => {
    const m = await import('./nativeForeground')
    expect(m.getForegroundWindowInfo()).toEqual({
      handle: '0x1',
      exePath: '/usr/bin/code',
      className: null
    })
  })
  it('returns the real title', async () => {
    const m = await import('./nativeForeground')
    expect(m.getForegroundWindowTitle()).toBe('plan.md — Code')
  })
})
