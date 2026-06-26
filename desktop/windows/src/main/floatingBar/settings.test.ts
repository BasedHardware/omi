import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const electronState = vi.hoisted(() => ({ userData: '' }))

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => electronState.userData)
  }
}))

import {
  getFloatingBarSettings,
  recordFloatingBarAsked,
  recordFloatingBarSummon,
  recordFloatingBarVoiceCaptured,
  setFloatingBarSettings
} from './settings'

const dirs: string[] = []

function useTempUserData(): string {
  const dir = mkdtempSync(join(tmpdir(), 'omi-floating-bar-settings-'))
  dirs.push(dir)
  electronState.userData = dir
  return dir
}

afterEach(() => {
  for (const dir of dirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

describe('floating bar settings', () => {
  it('defaults to the existing shortcut and always-on-top behavior', () => {
    useTempUserData()

    expect(getFloatingBarSettings()).toEqual({
      enabled: true,
      summonOnShortcut: true,
      summonShortcut: 'Shift+Space',
      alwaysOnTop: true,
      voiceAnswersEnabled: false,
      realtimeVoiceEnabled: false,
      realtimeVoiceProvider: 'omi-relay',
      summonCount: 0,
      askCount: 0,
      voiceCaptureCount: 0,
      lastSummonedAt: null,
      lastOpenedAt: null,
      lastAskedAt: null,
      lastVoiceCapturedAt: null
    })
  })

  it('coerces corrupt and out-of-range fields', () => {
    const dir = useTempUserData()
    writeFileSync(
      join(dir, 'floating-bar-settings.json'),
      JSON.stringify({
        enabled: false,
        summonOnShortcut: false,
        summonShortcut: '  ',
        alwaysOnTop: false,
        voiceAnswersEnabled: true,
        realtimeVoiceEnabled: true,
        realtimeVoiceProvider: 'unknown',
        summonCount: -1,
        askCount: 2.8,
        voiceCaptureCount: 3,
        lastSummonedAt: 'yesterday',
        lastOpenedAt: 50
      })
    )

    expect(getFloatingBarSettings()).toMatchObject({
      enabled: false,
      summonOnShortcut: false,
      summonShortcut: 'Shift+Space',
      alwaysOnTop: false,
      voiceAnswersEnabled: true,
      realtimeVoiceEnabled: true,
      realtimeVoiceProvider: 'omi-relay',
      summonCount: 0,
      askCount: 2,
      voiceCaptureCount: 3,
      lastSummonedAt: null,
      lastOpenedAt: 50
    })
  })

  it('records shortcut, ask, and voice usage counters', () => {
    useTempUserData()
    setFloatingBarSettings({
      ...getFloatingBarSettings(),
      summonShortcut: 'Control+Alt+Space'
    })

    recordFloatingBarSummon()
    recordFloatingBarAsked()
    recordFloatingBarVoiceCaptured()

    const saved = getFloatingBarSettings()
    expect(saved.summonShortcut).toBe('Control+Alt+Space')
    expect(saved.summonCount).toBe(1)
    expect(saved.askCount).toBe(1)
    expect(saved.voiceCaptureCount).toBe(1)
    expect(saved.lastSummonedAt).toEqual(expect.any(Number))
    expect(saved.lastAskedAt).toEqual(expect.any(Number))
    expect(saved.lastVoiceCapturedAt).toEqual(expect.any(Number))
  })
})
