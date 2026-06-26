import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const electronState = vi.hoisted(() => ({ userData: '' }))

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => electronState.userData)
  }
}))

import {
  getWindowsNotificationSettings,
  sanitizeStoredWindowsNotificationSettings,
  updateWindowsNotificationSettings
} from './settings'

const dirs: string[] = []

function useTempUserData(): string {
  const dir = mkdtempSync(join(tmpdir(), 'omi-notification-settings-'))
  dirs.push(dir)
  electronState.userData = dir
  return dir
}

afterEach(() => {
  for (const dir of dirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

describe('Windows notification settings', () => {
  it('sanitizes malformed persisted values', () => {
    expect(
      sanitizeStoredWindowsNotificationSettings({
        nativeEnabled: false,
        focus: { enabled: 'yes' },
        tasks: { enabled: true },
        memories: null,
        dailySummary: { enabled: false, hour: 99 }
      })
    ).toEqual({
      nativeEnabled: false,
      focus: { enabled: true },
      tasks: { enabled: true },
      memories: { enabled: false },
      dailySummary: { enabled: false, hour: 22 }
    })
  })

  it('persists category settings and bridges insight settings', () => {
    const dir = useTempUserData()

    const saved = updateWindowsNotificationSettings({
      nativeEnabled: false,
      tasks: { enabled: true },
      dailySummary: { enabled: false, hour: 9 },
      insights: {
        enabled: false,
        intervalMin: 30,
        notificationStyle: 'native',
        denylist: [' Slack ', '']
      }
    })

    expect(saved).toMatchObject({
      nativeEnabled: false,
      focus: { enabled: true },
      tasks: { enabled: true },
      memories: { enabled: false },
      dailySummary: { enabled: false, hour: 9 },
      insights: {
        enabled: false,
        intervalMin: 30,
        notificationStyle: 'native',
        denylist: ['Slack']
      }
    })
    expect(JSON.parse(readFileSync(join(dir, 'notification-settings.json'), 'utf-8'))).toEqual({
      nativeEnabled: false,
      focus: { enabled: true },
      tasks: { enabled: true },
      memories: { enabled: false },
      dailySummary: { enabled: false, hour: 9 }
    })
    expect(getWindowsNotificationSettings().insights.notificationStyle).toBe('native')
  })
})
