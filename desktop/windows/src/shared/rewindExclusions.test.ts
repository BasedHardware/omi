import { describe, it, expect } from 'vitest'
import { BUILT_IN_EXCLUDED_APPS } from './rewindExclusions'

// Mirror the documented matcher in captureDecision.isExcluded: a case-insensitive
// substring against "<app> <process>".
const excluded = (app: string, proc: string): boolean => {
  const hay = `${app} ${proc}`.toLowerCase()
  return BUILT_IN_EXCLUDED_APPS.some((e) => {
    const n = e.trim().toLowerCase()
    return n.length > 0 && hay.includes(n)
  })
}

describe('BUILT_IN_EXCLUDED_APPS', () => {
  it('excludes OBS Studio by its process name', () => {
    expect(excluded('OBS Studio', 'obs64')).toBe(true)
  })

  it('does not exclude Obsidian (the short-token "OBS" substring trap)', () => {
    expect(excluded('Obsidian', 'Obsidian')).toBe(false)
  })

  it('still excludes a password manager', () => {
    expect(excluded('1Password', '1Password')).toBe(true)
  })
})
