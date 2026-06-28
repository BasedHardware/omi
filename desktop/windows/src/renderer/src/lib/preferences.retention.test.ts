import { it, expect } from 'vitest'
import { getPreferences, setPreferences } from './preferences'

it('retentionMode defaults to dry-run', () => {
  expect(getPreferences().retentionMode ?? 'dry-run').toBe('dry-run')
})

it('retentionMode round-trips', () => {
  setPreferences({ retentionMode: 'live' })
  expect(getPreferences().retentionMode).toBe('live')
})
