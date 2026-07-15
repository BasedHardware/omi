import { describe, expect, it } from 'vitest'
import {
  MAX_PROFILE_CHARS,
  STAGE1_SYSTEM_PROMPT,
  STAGE2_SYSTEM_PROMPT,
  buildStage1Messages,
  buildStage2Messages,
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

describe('buildStage1Messages', () => {
  it('leads with the hardened system prompt (hallucination + third-person guards)', () => {
    const [system] = buildStage1Messages(fullSources)
    expect(system.role).toBe('system')
    expect(system.content).toBe(STAGE1_SYSTEM_PROMPT)
    // Guard clauses present.
    expect(system.content).toContain('third person')
    expect(system.content).toContain('ONLY include facts that are directly evidenced')
    expect(system.content).toContain('NEVER fabricate email addresses')
    expect(system.content).toContain('under 2000 characters')
  })

  it('includes only non-empty sections under their headers', () => {
    const [, user] = buildStage1Messages({ ...emptySources, memories: ['[work] engineer'] })
    expect(user.role).toBe('user')
    expect(user.content).toContain('## Memories about the user')
    expect(user.content).toContain('[work] engineer')
    // Empty sources must not appear.
    expect(user.content).not.toContain('## Recent tasks')
    expect(user.content).not.toContain('## Active goals')
    expect(user.content).not.toContain('## Recent conversations')
    expect(user.content).not.toContain('## Recent AI chat messages')
  })

  it('renders every populated section', () => {
    const [, user] = buildStage1Messages(fullSources)
    expect(user.content).toContain('## Memories about the user')
    expect(user.content).toContain('## Recent tasks')
    expect(user.content).toContain('## Active goals')
    expect(user.content).toContain('## Recent conversations (past 7 days)')
    expect(user.content).toContain('## Recent AI chat messages')
  })
})

describe('buildStage2Messages', () => {
  it('leads with the consolidation system prompt (merge + hallucination guards)', () => {
    const [system] = buildStage2Messages('- User is an engineer', ['- old fact'])
    expect(system.role).toBe('system')
    expect(system.content).toBe(STAGE2_SYSTEM_PROMPT)
    expect(system.content).toContain('MERGE RULES')
    expect(system.content).toContain('Do NOT hallucinate')
    expect(system.content).toContain('under 2000 characters')
  })

  it('includes the fresh profile and every past profile (oldest→newest)', () => {
    const fresh = '- User ships features'
    const past = ['- oldest profile fact', '- middle profile fact', '- newest profile fact']
    const [, user] = buildStage2Messages(fresh, past)
    expect(user.content).toContain('=== NEW PROFILE')
    expect(user.content).toContain(fresh)
    expect(user.content).toContain('=== PAST PROFILES')
    for (const p of past) expect(user.content).toContain(p)
    // Order preserved: oldest appears before newest in the rendered prompt.
    expect(user.content.indexOf(past[0])).toBeLessThan(user.content.indexOf(past[2]))
  })
})

describe('enforceCharCap', () => {
  it('leaves short text untouched', () => {
    expect(enforceCharCap('hello', 2000)).toBe('hello')
  })

  it('truncates to the cap (default 10000 — the hard safety cap; the prompt separately asks the model for <2000)', () => {
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
