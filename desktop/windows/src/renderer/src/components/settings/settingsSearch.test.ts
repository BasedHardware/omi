import { describe, expect, it } from 'vitest'
import { matchesSettingsQuery } from './settingsSearch'

describe('matchesSettingsQuery', () => {
  it('matches empty queries', () => {
    expect(matchesSettingsQuery('Local Agent Access', '')).toBe(true)
    expect(matchesSettingsQuery('Local Agent Access', '   ')).toBe(true)
  })

  it('matches multi-word queries without requiring an exact substring', () => {
    expect(matchesSettingsQuery('Local Agent Access local agent api loopback', 'local api')).toBe(
      true
    )
    expect(matchesSettingsQuery('Agent settings for local API tools', 'agent settings')).toBe(true)
  })

  it('requires every word to be present', () => {
    expect(matchesSettingsQuery('Rewind screen capture settings', 'rewind local')).toBe(false)
  })
})
