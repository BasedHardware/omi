import { describe, it, expect } from 'vitest'
import {
  canRotateKnows,
  composeKnowsRows,
  knowsActionTip,
  MAX_KNOWS_ROWS,
  type KnowsSources
} from './knowsComposer'

const sources = (over: Partial<KnowsSources> = {}): KnowsSources => ({
  tasks: [
    { id: 't1', text: 'Task one' },
    { id: 't2', text: 'Task two' },
    { id: 't3', text: 'Task three' }
  ],
  insights: [
    { id: 'i1', text: 'Insight one' },
    { id: 'i2', text: 'Insight two' }
  ],
  tip: 'Recap what I got done today',
  questions: ['What should I do today?', 'What changed this week?'],
  dismissedTaskIds: new Set<string>(),
  rotation: 0,
  ...over
})

describe('slot rules', () => {
  it('composes task, insight, second task, ask — capped at four diverse rows', () => {
    const rows = composeKnowsRows(sources())
    expect(rows.map((r) => r.kind)).toEqual(['task', 'insight', 'task', 'question'])
    expect(rows).toHaveLength(MAX_KNOWS_ROWS)
    expect(rows[0].id).toBe('task-t1')
    expect(rows[1].id).toBe('insight-i1')
    expect(rows[2].id).toBe('task-t2')
    expect(rows[3].id).toBe('question-What should I do today?')
  })

  it('falls back to the tip as a question row when there are no insights', () => {
    const rows = composeKnowsRows(sources({ insights: [] }))
    expect(rows[1]).toEqual({
      id: 'question-Recap what I got done today',
      kind: 'question',
      text: 'Recap what I got done today'
    })
  })

  it('the ask never equals the tip', () => {
    const rows = composeKnowsRows(
      sources({ insights: [], questions: ['Recap what I got done today', 'Different ask'] })
    )
    const questions = rows.filter((r) => r.kind === 'question').map((r) => r.text)
    expect(questions[0]).toBe('Recap what I got done today') // the tip slot
    expect(questions[1]).toBe('Different ask') // the ask skipped the tip duplicate
  })

  it('dismissed task ids never appear and the next fresh task takes the slot', () => {
    const rows = composeKnowsRows(sources({ dismissedTaskIds: new Set(['t1']) }))
    expect(rows[0].id).toBe('task-t2')
    expect(rows.some((r) => r.id === 'task-t1')).toBe(false)
  })

  it('questions dedupe by trimmed text because the text is the id', () => {
    const rows = composeKnowsRows(
      sources({ tasks: [], insights: [], questions: [' Same ask ', 'Same ask'] })
    )
    const questionRows = rows.filter((r) => r.kind === 'question' && r.text === 'Same ask')
    expect(questionRows).toHaveLength(1)
  })
})

describe('rotation', () => {
  it('rotates each source independently by the shared counter', () => {
    const rows = composeKnowsRows(sources({ rotation: 1 }))
    expect(rows[0].id).toBe('task-t2')
    expect(rows[1].id).toBe('insight-i2')
    expect(rows[2].id).toBe('task-t3')
  })

  it('normalizes any rotation value into range, including huge ones', () => {
    const base = composeKnowsRows(sources({ rotation: 0 }))
    const wrapped = composeKnowsRows(sources({ rotation: 3 * 2 * 2 * 1000 }))
    expect(wrapped.map((r) => r.id)).toEqual(base.map((r) => r.id))
  })

  it('canRotate requires an alternative somewhere', () => {
    expect(canRotateKnows(2, 1, 1)).toBe(false)
    expect(canRotateKnows(3, 0, 0)).toBe(true)
    expect(canRotateKnows(0, 2, 0)).toBe(true)
    expect(canRotateKnows(0, 0, 2)).toBe(true)
  })
})

describe('action tip', () => {
  it('gets pushy at five open tasks', () => {
    expect(knowsActionTip(4)).toBe('Recap what I got done today')
    expect(knowsActionTip(5)).toBe('Sort my open tasks — which 3 actually matter today?')
  })
})
