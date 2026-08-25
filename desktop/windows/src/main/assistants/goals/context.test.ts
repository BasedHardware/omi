import { describe, it, expect } from 'vitest'
import {
  assembleGoalContext,
  hasSufficientContext,
  type GoalContextFetchers,
  type GoalContextData,
  type RawGoal
} from './context'

// Fetchers are injected, so assembly + the goal split are tested with zero network.
function fetchers(over: Partial<GoalContextFetchers> = {}): GoalContextFetchers {
  return {
    fetchMemories: async () => [],
    fetchConversations: async () => [],
    fetchTasks: async () => [],
    fetchPersona: async () => null,
    fetchGoals: async () => [],
    ...over
  }
}

describe('assembleGoalContext', () => {
  it('passes each source through into the bundle', async () => {
    const data = await assembleGoalContext(
      fetchers({
        fetchPersona: async () => 'Ada: builds things',
        fetchMemories: async () => ['likes tea', 'ships weekly'],
        fetchConversations: async () => ['Planned Q3 roadmap'],
        fetchTasks: async () => [{ id: 'a1', description: 'write spec' }]
      })
    )
    expect(data.persona).toBe('Ada: builds things')
    expect(data.memories).toEqual(['likes tea', 'ships weekly'])
    expect(data.conversations).toEqual(['Planned Q3 roadmap'])
    expect(data.tasks).toEqual([{ id: 'a1', description: 'write spec' }])
  })

  it('splits goals into active vs progress-complete and counts active', async () => {
    const goals: RawGoal[] = [
      { title: 'Read books', targetValue: 12, currentValue: 3 }, // active
      { title: 'Ship v1', targetValue: 1, currentValue: 1 }, // complete (>=target)
      { title: 'Run miles', targetValue: 100, currentValue: 100 }, // complete
      { title: 'No target', targetValue: 0, currentValue: 0 } // target 0 → active
    ]
    const data = await assembleGoalContext(fetchers({ fetchGoals: async () => goals }))
    expect(data.activeGoals).toEqual(['- Read books (3/12)', '- No target (0/0)'])
    expect(data.completedGoals).toEqual([
      '- Ship v1 (achieved 1/1)',
      '- Run miles (achieved 100/100)'
    ])
    expect(data.activeGoalCount).toBe(2)
  })

  it('trims float noise in rendered goal values', async () => {
    const data = await assembleGoalContext(
      fetchers({ fetchGoals: async () => [{ title: 'X', targetValue: 10, currentValue: 2.5 }] })
    )
    expect(data.activeGoals).toEqual(['- X (2.5/10)'])
  })
})

describe('hasSufficientContext', () => {
  const base: GoalContextData = {
    persona: null,
    memories: [],
    conversations: [],
    tasks: [],
    activeGoals: [],
    completedGoals: [],
    activeGoalCount: 0
  }

  it('is false when memories, conversations, and tasks are all empty', () => {
    // Persona + goals alone are not enough to reason from (Mac's guard).
    expect(hasSufficientContext({ ...base, persona: 'Ada', activeGoals: ['- g (0/1)'] })).toBe(
      false
    )
  })

  it('is true when any of memories / conversations / tasks is non-empty', () => {
    expect(hasSufficientContext({ ...base, memories: ['x'] })).toBe(true)
    expect(hasSufficientContext({ ...base, conversations: ['x'] })).toBe(true)
    expect(hasSufficientContext({ ...base, tasks: [{ id: '1', description: 'x' }] })).toBe(true)
  })
})
