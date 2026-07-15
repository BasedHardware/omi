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

import {
  getAppSettings,
  setAppSettings,
  sanitizeAppSettings,
  onAppSettingsChanged,
  _resetForTests
} from './appSettings'

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

  it('round-trips the record-hotkey enabled flag (default on)', () => {
    expect(getAppSettings().recordHotkeyEnabled).toBe(true)
    setAppSettings({ recordHotkeyEnabled: false })
    _resetForTests()
    expect(getAppSettings().recordHotkeyEnabled).toBe(false)
  })

  // The proactive coordinator's master toggle would otherwise be one-way: it
  // re-reads the setting each tick (so OFF works), but only a listener can
  // re-arm the loop when it goes back ON.
  it('notifies listeners on every write, and a throwing listener does not lose the write', () => {
    const seen: boolean[] = []
    onAppSettingsChanged(() => {
      throw new Error('boom')
    })
    onAppSettingsChanged((s) => seen.push(s.screenAnalysisEnabled))
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    setAppSettings({ screenAnalysisEnabled: false })
    setAppSettings({ screenAnalysisEnabled: true })

    expect(seen).toEqual([false, true])
    expect(getAppSettings().screenAnalysisEnabled).toBe(true)
  })

  it('sanitizes bad input back to safe defaults', () => {
    expect(sanitizeAppSettings({} as never)).toEqual({
      closeToTrayNoticeShown: false,
      recordHotkey: 'Ctrl+Space',
      recordHotkeyEnabled: true,
      summonHotkey: 'Shift+Space',
      hudContentProtection: true,
      meeting: { mode: 'ask', endGraceMinutes: 2, perApp: {}, firstRunToastShown: false },
      lastShownChangelogVersion: null,
      aiProfileEnabled: true,
      focusEnabled: true,
      focusNotificationsEnabled: true,
      focusCooldownMinutes: 10,
      focusExcludedApps: [],
      glowOverlayEnabled: true,
      screenAnalysisEnabled: true,
      notificationsEnabled: true,
      notificationFrequency: 0,
      memoryEnabled: false,
      memoryExtractionIntervalMin: 10,
      memoryMinConfidence: 0.7,
      memoryExcludedApps: []
    })
    // Proactive notifications default to Off (level 0) — an assistant may only
    // interrupt once the user has chosen a frequency. Anything that is not a
    // valid level falls back to Off, never to the NEAREST level: clamping a
    // corrupt file (or a backend sync sending 10) up to 5 would mean "no
    // throttle" — unthrottled toasts for a user whose default was silence.
    expect(sanitizeAppSettings({ notificationFrequency: 4 }).notificationFrequency).toBe(4)
    expect(sanitizeAppSettings({ notificationFrequency: 9 }).notificationFrequency).toBe(0)
    expect(sanitizeAppSettings({ notificationFrequency: -2 }).notificationFrequency).toBe(0)
    expect(sanitizeAppSettings({ notificationFrequency: 2.5 }).notificationFrequency).toBe(0)
    expect(
      sanitizeAppSettings({ notificationFrequency: 'max' } as never).notificationFrequency
    ).toBe(0)
    // Screen analysis is opt-OUT: on unless the user turns it off.
    expect(sanitizeAppSettings({ screenAnalysisEnabled: false }).screenAnalysisEnabled).toBe(false)
    // The focus halo is opt-OUT (on unless explicitly disabled) — it only ever
    // appears in response to a Focus verdict, and it is click-through.
    expect(sanitizeAppSettings({ glowOverlayEnabled: false }).glowOverlayEnabled).toBe(false)
    // The AI user profile is opt-OUT now that Focus consumes it: on unless the
    // user explicitly turns it off.
    expect(sanitizeAppSettings({ aiProfileEnabled: false }).aiProfileEnabled).toBe(false)
    expect(sanitizeAppSettings({ aiProfileEnabled: 'yes' } as never).aiProfileEnabled).toBe(true)
    // Focus master flags are opt-OUT; cooldown and excluded-apps sanitize.
    expect(sanitizeAppSettings({ focusEnabled: false }).focusEnabled).toBe(false)
    expect(
      sanitizeAppSettings({ focusNotificationsEnabled: false }).focusNotificationsEnabled
    ).toBe(false)
    expect(sanitizeAppSettings({ focusCooldownMinutes: 5 }).focusCooldownMinutes).toBe(5)
    // Zero/negative/junk cooldown falls back to 10 (never disables the cooldown).
    expect(sanitizeAppSettings({ focusCooldownMinutes: 0 }).focusCooldownMinutes).toBe(10)
    expect(sanitizeAppSettings({ focusCooldownMinutes: -3 }).focusCooldownMinutes).toBe(10)
    expect(sanitizeAppSettings({ focusCooldownMinutes: 2.5 }).focusCooldownMinutes).toBe(10)
    // Excluded apps: only non-empty strings survive.
    expect(
      sanitizeAppSettings({ focusExcludedApps: ['Slack', '', '  Discord  ', 5] as never })
        .focusExcludedApps
    ).toEqual(['Slack', 'Discord'])
    expect(sanitizeAppSettings({ focusExcludedApps: 'nope' as never }).focusExcludedApps).toEqual(
      []
    )
    // Memory: master flag opt-OUT; interval reuses the cooldown sanitizer (positive
    // integer minutes, junk → 10); min-confidence clamps to [0,1] (junk → 0.7).
    expect(sanitizeAppSettings({ memoryEnabled: false }).memoryEnabled).toBe(false)
    expect(
      sanitizeAppSettings({ memoryExtractionIntervalMin: 15 }).memoryExtractionIntervalMin
    ).toBe(15)
    expect(
      sanitizeAppSettings({ memoryExtractionIntervalMin: 0 }).memoryExtractionIntervalMin
    ).toBe(10)
    expect(sanitizeAppSettings({ memoryMinConfidence: 0.85 }).memoryMinConfidence).toBe(0.85)
    expect(sanitizeAppSettings({ memoryMinConfidence: 2 }).memoryMinConfidence).toBe(1)
    expect(sanitizeAppSettings({ memoryMinConfidence: -1 }).memoryMinConfidence).toBe(0)
    expect(sanitizeAppSettings({ memoryMinConfidence: 'high' } as never).memoryMinConfidence).toBe(
      0.7
    )
    expect(
      sanitizeAppSettings({ memoryExcludedApps: ['Zoom', '', '  Music  '] as never })
        .memoryExcludedApps
    ).toEqual(['Zoom', 'Music'])
    expect(sanitizeAppSettings({ summonHotkey: '  ' } as never).summonHotkey).toBe('Shift+Space')
    expect(sanitizeAppSettings({ summonHotkey: 'Alt+K' } as never).summonHotkey).toBe('Alt+K')
    expect(sanitizeAppSettings({ recordHotkey: '  ' } as never).recordHotkey).toBe('Ctrl+Space')
    expect(sanitizeAppSettings({ recordHotkey: 42 } as never).recordHotkey).toBe('Ctrl+Space')
    expect(
      sanitizeAppSettings({ closeToTrayNoticeShown: 'yes' } as never).closeToTrayNoticeShown
    ).toBe(false)
    expect(sanitizeAppSettings(null).recordHotkey).toBe('Ctrl+Space')
    // recordHotkeyEnabled defaults ON; only an explicit false disables it.
    expect(sanitizeAppSettings(null).recordHotkeyEnabled).toBe(true)
    expect(sanitizeAppSettings({ recordHotkeyEnabled: false }).recordHotkeyEnabled).toBe(false)
    expect(sanitizeAppSettings({ recordHotkeyEnabled: 'nope' } as never).recordHotkeyEnabled).toBe(
      true
    )
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
