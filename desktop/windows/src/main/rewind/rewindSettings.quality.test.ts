import { describe, it, expect, vi } from 'vitest'
import { mkdtempSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Real read/write against a throwaway userData dir — the persisted round trip is
// the behavior that matters (#10489: an existing install has no captureQuality
// in its settings file and must still land on a valid tier).
const dir = mkdtempSync(join(tmpdir(), 'rewind-settings-'))
vi.mock('electron', () => ({ app: { getPath: () => dir } }))

import { getPersistedRewindSettings, persistRewindSettings } from './rewindSettings'

const base = { captureEnabled: true, intervalMs: 1000, retentionDays: 14, excludedApps: [] }

describe('rewind capture quality', () => {
  it('defaults to standard when nothing is persisted', () => {
    expect(getPersistedRewindSettings().captureQuality).toBe('standard')
  })

  it('persists a chosen tier', () => {
    persistRewindSettings({ ...base, captureQuality: 'max' })
    expect(getPersistedRewindSettings().captureQuality).toBe('max')
  })

  it('falls back to standard for a settings file written before the tier existed', () => {
    persistRewindSettings({ ...base, captureQuality: undefined } as never)
    expect(getPersistedRewindSettings().captureQuality).toBe('standard')
  })

  it('falls back to standard for an unknown tier', () => {
    persistRewindSettings({ ...base, captureQuality: 'ultra' } as never)
    expect(getPersistedRewindSettings().captureQuality).toBe('standard')
  })
})
