import { describe, expect, it } from 'vitest'
import {
  MAX_PROFILE_CHARS,
  enforceCharCap,
  shouldGenerate,
  totalSourceItems,
  usedSourceNames,
  type ProfileSources
} from './synthesis'

const emptySources: ProfileSources = {
  memories: [],
  tasks: [],
  goals: [],
  conversations: [],
  messages: []
}

const fullSources: ProfileSources = {
  memories: ['[work] User is a software engineer', '[personal] User lives in Seattle'],
  tasks: ['[todo] Ship the Windows profile feature'],
  goals: ['Ship 2 features per week (50% complete)'],
  conversations: ['Standup: discussed the parity audit'],
  messages: ['[human] what do you know about me']
}

describe('shouldGenerate', () => {
  const now = 1_000_000_000_000

  it('returns true when never generated (null)', () => {
    expect(shouldGenerate(null, now)).toBe(true)
  })

  it('returns true when the last profile is older than 24h', () => {
    expect(shouldGenerate(now - 86_400_001, now)).toBe(true)
  })

  it('returns false when the last profile is within 24h', () => {
    expect(shouldGenerate(now - 86_400_000, now)).toBe(false)
    expect(shouldGenerate(now - 1000, now)).toBe(false)
  })
})

describe('totalSourceItems / usedSourceNames', () => {
  it('counts all items across sources (this is the exact value sent as the backend data_sources_used int)', () => {
    expect(totalSourceItems(fullSources)).toBe(6)
    expect(totalSourceItems(emptySources)).toBe(0)
  })

  it('names only the non-empty sources (the rich local array)', () => {
    expect(usedSourceNames(fullSources)).toEqual([
      'memories',
      'tasks',
      'goals',
      'conversations',
      'messages'
    ])
    expect(usedSourceNames(emptySources)).toEqual([])
    expect(usedSourceNames({ ...emptySources, goals: ['g'] })).toEqual(['goals'])
  })
})

describe('enforceCharCap', () => {
  it('leaves short text untouched', () => {
    expect(enforceCharCap('hello', 2000)).toBe('hello')
  })

  it('truncates to the cap (default 10000 — the hard safety cap; the backend prompt separately asks the model for <2000)', () => {
    const long = 'x'.repeat(12_000)
    expect(enforceCharCap(long).length).toBe(MAX_PROFILE_CHARS)
    expect(enforceCharCap(long, 100).length).toBe(100)
  })

  it('trims trailing whitespace left by the cut', () => {
    const text = 'a'.repeat(98) + '   tail'
    // cap 100 → slice is 98 'a's + '  ' (two spaces) → trimmed back to 98 'a's.
    expect(enforceCharCap(text, 100)).toBe('a'.repeat(98))
  })
})
