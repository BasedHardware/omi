import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Throwaway userData dir for the app-settings store; app.getVersion is swapped
// per test to drive the "did the build increase?" decision.
const dir = mkdtempSync(join(tmpdir(), 'omi-whatsnew-'))
let version = '1.0.0'
vi.mock('electron', () => ({
  app: { getPath: (): string => dir, getVersion: (): string => version },
  globalShortcut: {
    register: (): boolean => true,
    unregister: (): void => {},
    isRegistered: (): boolean => false
  }
}))

import { maybeGetWhatsNew } from './whatsNew'
import { getAppSettings, setAppSettings, _resetForTests } from './appSettings'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

function withStored(stored: string | null): void {
  _resetForTests()
  rmSync(join(dir, 'app-settings.json'), { force: true })
  if (stored !== null) setAppSettings({ lastShownChangelogVersion: stored })
}

describe('maybeGetWhatsNew', () => {
  beforeEach(() => {
    version = '1.0.0'
  })

  it('baselines silently on a fresh install (no stored version) and records the build', () => {
    withStored(null)
    expect(maybeGetWhatsNew()).toBeNull()
    expect(getAppSettings().lastShownChangelogVersion).toBe('1.0.0')
  })

  it('shows the changelog once after an update (stored < current), then records + no re-show', () => {
    withStored('0.9.0')
    const p = maybeGetWhatsNew()
    expect(p).not.toBeNull()
    expect(p?.version).toBe('1.0.0')
    expect(p?.changes.length ?? 0).toBeGreaterThan(0)
    expect(getAppSettings().lastShownChangelogVersion).toBe('1.0.0')
    // Same version on the next launch → no toast.
    expect(maybeGetWhatsNew()).toBeNull()
  })

  it('does not show when the current build was already shown', () => {
    withStored('1.0.0')
    expect(maybeGetWhatsNew()).toBeNull()
  })
})
