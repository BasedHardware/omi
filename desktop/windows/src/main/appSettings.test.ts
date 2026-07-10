import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Point the store at a throwaway userData dir so the round-trip touches a real
// file without hitting the developer's actual profile.
const dir = mkdtempSync(join(tmpdir(), 'omi-appsettings-'))
vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  globalShortcut: {
    register: (): boolean => true,
    unregister: (): void => {},
    isRegistered: (): boolean => false
  }
}))

import { getAppSettings, setAppSettings, sanitizeAppSettings, _resetForTests } from './appSettings'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

describe('appSettings', () => {
  beforeEach(() => {
    // Reset to defaults between tests by clearing the file AND the in-memory
    // cache (getAppSettings reads disk at most once per process).
    _resetForTests()
    try {
      rmSync(join(dir, 'app-settings.json'), { force: true })
    } catch {
      /* ignore */
    }
  })

  it('returns defaults when no file exists', () => {
    const s = getAppSettings()
    expect(s.closeToTrayNoticeShown).toBe(false)
    expect(s.recordHotkey).toBe('Ctrl+Space')
  })

  it('round-trips a patched flag and preserves untouched fields', () => {
    setAppSettings({ closeToTrayNoticeShown: true })
    // Drop the cache so the assertion proves the value persisted to disk.
    _resetForTests()
    const s = getAppSettings()
    expect(s.closeToTrayNoticeShown).toBe(true)
    expect(s.recordHotkey).toBe('Ctrl+Space')
  })

  it('round-trips a rebound record hotkey', () => {
    setAppSettings({ recordHotkey: 'Ctrl+Shift+O' })
    _resetForTests()
    expect(getAppSettings().recordHotkey).toBe('Ctrl+Shift+O')
  })

  it('sanitizes bad input back to safe defaults', () => {
    expect(sanitizeAppSettings({} as never)).toEqual({
      closeToTrayNoticeShown: false,
      recordHotkey: 'Ctrl+Space',
      hudContentProtection: true,
      meeting: { mode: 'ask', endGraceMinutes: 2, perApp: {}, firstRunToastShown: false }
    })
    expect(sanitizeAppSettings({ recordHotkey: '  ' } as never).recordHotkey).toBe('Ctrl+Space')
    expect(sanitizeAppSettings({ recordHotkey: 42 } as never).recordHotkey).toBe('Ctrl+Space')
    expect(
      sanitizeAppSettings({ closeToTrayNoticeShown: 'yes' } as never).closeToTrayNoticeShown
    ).toBe(false)
    expect(sanitizeAppSettings(null).recordHotkey).toBe('Ctrl+Space')
    // HUD capture-exclusion defaults ON and only an explicit false disables it.
    expect(sanitizeAppSettings(null).hudContentProtection).toBe(true)
    expect(sanitizeAppSettings({ hudContentProtection: false }).hudContentProtection).toBe(false)
    expect(
      sanitizeAppSettings({ hudContentProtection: 'nope' } as never).hudContentProtection
    ).toBe(true)
  })

  it('meeting settings default to ask/2min and sanitize bad values', () => {
    const d = sanitizeAppSettings(null).meeting
    expect(d).toEqual({ mode: 'ask', endGraceMinutes: 2, perApp: {}, firstRunToastShown: false })

    const m = sanitizeAppSettings({
      meeting: {
        mode: 'auto',
        endGraceMinutes: 999,
        perApp: { zoom: 'off', bogus: 'sideways' as never },
        firstRunToastShown: true
      }
    } as never).meeting
    expect(m.mode).toBe('auto')
    expect(m.endGraceMinutes).toBe(30) // clamped
    expect(m.perApp).toEqual({ zoom: 'off' }) // invalid override dropped
    expect(m.firstRunToastShown).toBe(true)

    expect(sanitizeAppSettings({ meeting: { mode: 'loud' } } as never).meeting.mode).toBe('ask')
    expect(
      sanitizeAppSettings({ meeting: { endGraceMinutes: 0 } } as never).meeting.endGraceMinutes
    ).toBe(1)
  })

  it('round-trips meeting settings', () => {
    setAppSettings({
      meeting: {
        mode: 'auto',
        endGraceMinutes: 5,
        perApp: { discord: 'off' },
        firstRunToastShown: true
      }
    })
    _resetForTests()
    expect(getAppSettings().meeting).toEqual({
      mode: 'auto',
      endGraceMinutes: 5,
      perApp: { discord: 'off' },
      firstRunToastShown: true
    })
  })
})
