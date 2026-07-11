import { describe, it, expect, vi } from 'vitest'

// Force the non-win32 path regardless of the host OS the test runs on.
vi.stubGlobal('process', { ...process, platform: 'linux' })

// Linux X11 must read as unavailable here so the linux branch falls through to
// the degraded contract this test pins.
vi.mock('./linuxForeground', () => ({
  linuxAvailable: () => false,
  getLinuxForegroundExePath: () => null,
  getLinuxForegroundInfo: () => ({ handle: null, exePath: null, className: null }),
  getLinuxForegroundTitle: () => null
}))

import {
  getForegroundExePath,
  getForegroundWindowInfo,
  getForegroundWindowTitle,
  subscribeForegroundChange
} from './nativeForeground'

describe('nativeForeground off-Windows degradation', () => {
  it('getForegroundExePath returns null, never throws', () => {
    expect(() => getForegroundExePath()).not.toThrow()
    expect(getForegroundExePath()).toBeNull()
  })
  it('getForegroundWindowInfo returns an all-null shape', () => {
    expect(getForegroundWindowInfo()).toEqual({ handle: null, exePath: null, className: null })
  })
  it('getForegroundWindowTitle returns null', () => {
    expect(getForegroundWindowTitle()).toBeNull()
  })
  it('subscribeForegroundChange returns a no-op unsubscribe', () => {
    const off = subscribeForegroundChange(() => {})
    expect(typeof off).toBe('function')
    expect(() => off()).not.toThrow()
  })
})
