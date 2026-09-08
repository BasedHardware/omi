import { describe, it, expect } from 'vitest'
import { windowsBuildNumber, supportsMica, MICA_MIN_BUILD } from './windowsVersion'

describe('windowsBuildNumber', () => {
  it('parses the build segment of os.release()', () => {
    expect(windowsBuildNumber('10.0.26100')).toBe(26100)
    expect(windowsBuildNumber('10.0.22621')).toBe(22621)
    expect(windowsBuildNumber('10.0.19045')).toBe(19045)
  })

  it('returns 0 for unparseable strings', () => {
    expect(windowsBuildNumber('weird')).toBe(0)
    expect(windowsBuildNumber('')).toBe(0)
  })
})

describe('supportsMica', () => {
  it('requires win32 AND build >= 22H2 (22621)', () => {
    expect(supportsMica('win32', MICA_MIN_BUILD)).toBe(true)
    expect(supportsMica('win32', 26100)).toBe(true)
    expect(supportsMica('win32', 22000)).toBe(false) // Win11 21H2 — no DWM backdrop attr
    expect(supportsMica('win32', 19045)).toBe(false) // Win10
    expect(supportsMica('darwin', 26100)).toBe(false)
    expect(supportsMica('linux', 26100)).toBe(false)
  })
})
