import { describe, it, expect } from 'vitest'
import {
  readCanonicalGoal,
  readGoalDetail,
  readRecommendationSubjectKind,
  readWmnProjection,
  readWorkflowControl
} from './wireTypes'

describe('lenient enum decode', () => {
  it('maps unknown wire strings to _unknown instead of throwing', () => {
    expect(readRecommendationSubjectKind('agent_open_loop')).toBe('agent_open_loop')
    expect(readRecommendationSubjectKind('hologram')).toBe('_unknown')
    expect(readRecommendationSubjectKind(7)).toBe('_unknown')
    expect(readWorkflowControl({ workflow_mode: 'future_mode' }).workflowMode).toBe('_unknown')
  })
})

describe('projection reader', () => {
  it('rejects a payload missing its envelope identifiers', () => {
    expect(readWmnProjection(null)).toBeNull()
    expect(readWmnProjection({ recommendations: [] })).toBeNull()
  })

  it('skips malformed rows and keeps well-formed ones', () => {
    const projection = readWmnProjection({
      evaluation_id: 'ev',
      output_version: 'out',
      expires_at: '2026-08-16T18:00:00Z',
      recommendations: [
        { headline: 'missing everything else' },
        {
          intervention_id: 'iv',
          output_version: 'out',
          subject_kind: 'task',
          subject_id: 's',
          feedback_subject_kind: 'task',
          feedback_subject_id: 's',
          headline: 'Good row',
          dedupe_key: 'dk',
          expires_at: '2026-08-16T18:00:00Z'
        }
      ]
    })
    expect(projection?.recommendations.map((r) => r.headline)).toEqual(['Good row'])
  })
})

describe('goal readers', () => {
  it('falls back to id when goal_id is absent and defaults is_active to true', () => {
    const goal = readCanonicalGoal({ id: 'g-1', title: 'T', status: 'background' })
    expect(goal?.goalId).toBe('g-1')
    expect(goal?.isActive).toBe(true)
    expect(readCanonicalGoal({ title: 'no id' })).toBeNull()
  })

  it('reads the detail projection with thread summaries preferring current state', () => {
    const detail = readGoalDetail({
      goal: { goal_id: 'g-1', title: 'T', status: 'focused' },
      tasks: [{ id: 't1', description: 'Do it', completed: false }, { description: 'no id' }],
      active_threads: [
        { workstream_id: 'ws1', current_state_summary: 'Halfway', objective: 'Obj' },
        { workstream_id: 'ws2', objective: 'Only objective' }
      ],
      progress_events: [{ summary: 'Shipped step one' }, { nope: true }]
    })
    expect(detail?.tasks).toEqual([{ id: 't1', description: 'Do it', completed: false }])
    expect(detail?.activeThreads.map((t) => t.summary)).toEqual(['Halfway', 'Only objective'])
    expect(detail?.progressEvents).toEqual([{ summary: 'Shipped step one' }])
  })
})
