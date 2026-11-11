import { describe, it, expect } from 'vitest'
import { GOAL_SUGGESTION_SCHEMA, GOAL_SYSTEM_PROMPT, fillPrompt } from './prompt'
import type { GoalContextData } from './context'

const base: GoalContextData = {
  persona: null,
  memories: [],
  conversations: [],
  tasks: [],
  activeGoals: [],
  completedGoals: [],
  activeGoalCount: 0
}

describe('fillPrompt', () => {
  it('substitutes every section and prefixes tasks with [id]', () => {
    const out = fillPrompt({
      ...base,
      persona: 'Ada: builder',
      memories: ['likes tea', 'ships weekly'],
      conversations: ['Planned roadmap'],
      tasks: [
        { id: 'a1', description: 'write spec' },
        { id: 'b2', description: 'review PR' }
      ],
      activeGoals: ['- Read 12 books (3/12)'],
      completedGoals: ['- Ship v1 (achieved 1/1)']
    })
    expect(out).toContain('Ada: builder')
    expect(out).toContain('likes tea\nships weekly')
    expect(out).toContain('Planned roadmap')
    expect(out).toContain('[a1] write spec')
    expect(out).toContain('[b2] review PR')
    expect(out).toContain('- Read 12 books (3/12)')
    expect(out).toContain('- Ship v1 (achieved 1/1)')
    // No placeholder should survive substitution.
    expect(out).not.toMatch(/\{[a-z_]+\}/)
  })

  it('applies Mac empty-state fallbacks when sections are empty', () => {
    const out = fillPrompt(base)
    expect(out).toContain('No persona set')
    expect(out).toContain('No memories yet')
    expect(out).toContain('No recent conversations')
    expect(out).toContain('No active tasks')
    // Active, completed, AND abandoned goals all read "None" when empty.
    expect(out.match(/None/g)?.length).toBeGreaterThanOrEqual(3)
    expect(out).not.toMatch(/\{[a-z_]+\}/)
  })

  it('always leaves abandoned goals as None (no backend signal)', () => {
    const out = fillPrompt({ ...base, activeGoals: ['- G (0/1)'] })
    expect(out).toContain('ABANDONED GOALS')
    // The abandoned block specifically is None even when active goals exist.
    const abandoned = out.slice(out.indexOf('ABANDONED GOALS'))
    expect(abandoned).toContain('None')
  })
})

describe('GOAL_SUGGESTION_SCHEMA', () => {
  it('requires the seven core fields and leaves linked_task_ids optional', () => {
    expect(GOAL_SUGGESTION_SCHEMA.required).toEqual([
      'suggested_title',
      'suggested_description',
      'suggested_type',
      'suggested_target',
      'suggested_min',
      'suggested_max',
      'reasoning'
    ])
    expect(GOAL_SUGGESTION_SCHEMA.required).not.toContain('linked_task_ids')
    expect(GOAL_SUGGESTION_SCHEMA.properties.suggested_type.enum).toEqual([
      'boolean',
      'scale',
      'numeric'
    ])
  })

  it('has a non-empty system prompt', () => {
    expect(GOAL_SYSTEM_PROMPT.length).toBeGreaterThan(10)
  })
})
