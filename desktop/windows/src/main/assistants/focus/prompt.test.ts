// Prompt assembly. Pure: inject the grounding data + history, assert the exact
// text. The system prompt itself is Mac's verbatim (asserted by anchor phrases).
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SYSTEM_PROMPT,
  buildContextBlock,
  buildFocusPrompt,
  formatHistory,
  type FocusContextData
} from './prompt'
import type { ScreenAnalysis } from './models'

const NOW = new Date('2026-07-14T15:07:00')

function ctx(over: Partial<FocusContextData> = {}): FocusContextData {
  return {
    profileText: null,
    goals: [],
    tasks: [],
    memories: [],
    now: NOW,
    ...over
  }
}

describe('DEFAULT_SYSTEM_PROMPT', () => {
  it("is Mac's copy verbatim — the anchor rules are present", () => {
    expect(DEFAULT_SYSTEM_PROMPT).toContain('You are a focus coach.')
    expect(DEFAULT_SYSTEM_PROMPT).toContain('PRIMARY/MAIN window')
    expect(DEFAULT_SYSTEM_PROMPT).toContain('When in doubt, lean toward "distracted"')
    expect(DEFAULT_SYSTEM_PROMPT).toContain('100 characters max')
  })
})

describe('buildContextBlock', () => {
  it('always includes a TIME CONTEXT line, formatted like Mac', () => {
    const block = buildContextBlock(ctx())
    expect(block).toContain('TIME CONTEXT:')
    expect(block).toContain('Tuesday, July 14, 2026 at 3:07 PM')
  })

  it('omits empty sections entirely (no bare header)', () => {
    const block = buildContextBlock(ctx())
    expect(block).not.toContain('ACTIVE GOALS')
    expect(block).not.toContain('CURRENT TASKS')
    expect(block).not.toContain('RECENT MEMORIES')
    expect(block).not.toContain('USER PROFILE')
  })

  it('includes the profile, goals, tasks and memories when present', () => {
    const block = buildContextBlock(
      ctx({
        profileText: 'A senior engineer who ships Windows desktop apps.',
        goals: [{ title: 'Ship Focus', description: 'the assistant' }, { title: 'No purple' }],
        tasks: [
          { description: 'Wire the coordinator', priority: 'high' },
          { description: 'Test it' }
        ],
        memories: ['Prefers dark mode', 'Dislikes AI slop']
      })
    )
    expect(block).toContain('USER PROFILE (who this user is):\nA senior engineer')
    expect(block).toContain('ACTIVE GOALS:\n1. Ship Focus - the assistant\n2. No purple')
    expect(block).toContain(
      'CURRENT TASKS (by importance):\n1. [high] Wire the coordinator\n2. [medium] Test it'
    )
    expect(block).toContain('RECENT MEMORIES:\n1. Prefers dark mode\n2. Dislikes AI slop')
  })

  it('caps goals at 10, tasks at 50, memories at 50', () => {
    const block = buildContextBlock(
      ctx({
        goals: Array.from({ length: 15 }, (_, i) => ({ title: `G${i}` })),
        tasks: Array.from({ length: 60 }, (_, i) => ({ description: `T${i}` })),
        memories: Array.from({ length: 60 }, (_, i) => `M${i}`)
      })
    )
    expect(block).toContain('10. G9')
    expect(block).not.toContain('11. G10')
    expect(block).toContain('50. [medium] T49')
    expect(block).not.toContain('51. [medium] T50')
    expect(block).toContain('50. M49')
    expect(block).not.toContain('51. M50')
  })
})

describe('formatHistory', () => {
  const a = (over: Partial<ScreenAnalysis>): ScreenAnalysis => ({
    status: 'focused',
    appOrSite: 'VS Code',
    description: 'editing',
    message: null,
    ...over
  })

  it('is empty when there is no history', () => {
    expect(formatHistory([])).toBe('')
  })

  it('formats each entry, with a Message line only when present', () => {
    const out = formatHistory([
      a({ status: 'distracted', appOrSite: 'YouTube', description: 'a video', message: 'refocus' }),
      a({ status: 'focused', appOrSite: 'VS Code', description: 'coding' })
    ])
    expect(out).toBe(
      'Recent activity (oldest to newest):\n' +
        '1. [distracted] YouTube: a video\n' +
        '   Message: refocus\n' +
        '2. [focused] VS Code: coding'
    )
  })

  it('keeps only the last 10 entries', () => {
    const many = Array.from({ length: 14 }, (_, i) => a({ description: `d${i}` }))
    const out = formatHistory(many)
    expect(out).toContain('1. [focused] VS Code: d4') // 14 - 10 = first shown is d4
    expect(out).not.toContain(': d3')
    expect(out).toContain('10. [focused] VS Code: d13')
  })
})

describe('buildFocusPrompt', () => {
  it('joins context + history + the closing instruction', () => {
    const prompt = buildFocusPrompt(ctx({ goals: [{ title: 'Ship it' }] }), [
      { status: 'focused', appOrSite: 'VS Code', description: 'coding', message: null }
    ])
    expect(prompt).toContain('ACTIVE GOALS:\n1. Ship it')
    expect(prompt).toContain('Recent activity (oldest to newest):')
    expect(prompt.endsWith('Now analyze this new screenshot:')).toBe(true)
  })

  it('still ends with the instruction when there is no context or history', () => {
    // Time context always exists, so the block is never fully empty — but history
    // can be, and the closing line must always be last.
    const prompt = buildFocusPrompt(ctx(), [])
    expect(prompt.endsWith('Now analyze this new screenshot:')).toBe(true)
    expect(prompt).not.toContain('Recent activity')
  })
})
