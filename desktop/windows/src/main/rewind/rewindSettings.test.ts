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

import { getPersistedRewindSettings, persistRewindSettings } from './rewindSettings'

const dirs: string[] = []

function useTempUserData(): string {
  const dir = mkdtempSync(join(tmpdir(), 'omi-rewind-settings-'))
  dirs.push(dir)
  electronState.userData = dir
  return dir
}

afterEach(() => {
  for (const dir of dirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

describe('rewind settings', () => {
  it('defaults screen capture off when no settings file exists', () => {
    useTempUserData()

    expect(getPersistedRewindSettings()).toEqual({
      captureEnabled: false,
      intervalMs: 1000,
      retentionDays: 14,
      excludedApps: []
    })
  })

  it('keeps screen capture off unless explicitly enabled', () => {
    const dir = useTempUserData()
    writeFileSync(join(dir, 'rewind-settings.json'), JSON.stringify({ intervalMs: 5000 }))

    expect(getPersistedRewindSettings().captureEnabled).toBe(false)
  })

  it('persists an explicit screen capture opt-in', () => {
    useTempUserData()

    persistRewindSettings({
      captureEnabled: true,
      intervalMs: 2000,
      retentionDays: 30,
      excludedApps: ['Banking']
    })

    expect(getPersistedRewindSettings()).toEqual({
      captureEnabled: true,
      intervalMs: 2000,
      retentionDays: 30,
      excludedApps: ['Banking']
    })
  })
})
