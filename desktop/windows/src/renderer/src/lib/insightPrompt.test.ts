// src/renderer/src/lib/insightPrompt.test.ts
import { describe, it, expect } from 'vitest'
import { buildInsightPrompt, parseInsightResponse } from './insightPrompt'

describe('buildInsightPrompt', () => {
  it('includes the activity summary and recent insight headlines', () => {
    const p = buildInsightPrompt('## Code — plan.md\nwriting', ['Use a debugger'])
    expect(p).toContain('writing')
    expect(p).toContain('Use a debugger')
  })

  it('lets the model decline by default (selective)', () => {
    const p = buildInsightPrompt('## Code — plan.md\nwriting', [])
    expect(p).toContain('has_insight=false')
  })

  it('forces an insight in force mode (never declines)', () => {
    const p = buildInsightPrompt('## Code — plan.md\nwriting', [], { force: true })
    expect(p).toContain('ALWAYS return')
    expect(p).not.toContain('has_insight=false')
  })
})

describe('parseInsightResponse', () => {
  it('parses a fenced insight', () => {
    const raw =
      '```json\n{"has_insight":true,"insight":{"headline":"Try a debugger","advice":"Step through it","reasoning":"r","category":"productivity","source_app":"Code","confidence":0.9}}\n```'
    expect(parseInsightResponse(raw)).toEqual({
      headline: 'Try a debugger',
      advice: 'Step through it',
      reasoning: 'r',
      category: 'productivity',
      sourceApp: 'Code',
      confidence: 0.9
    })
  })
  it('returns null when has_insight is false', () => {
    expect(parseInsightResponse('{"has_insight":false}')).toBeNull()
  })
  it('returns null on malformed JSON', () => {
    expect(parseInsightResponse('nope')).toBeNull()
  })
  it('coerces an unknown category to other', () => {
    const raw =
      '{"has_insight":true,"insight":{"headline":"h","advice":"a","reasoning":"","category":"weird","source_app":"X","confidence":0.8}}'
    expect(parseInsightResponse(raw)?.category).toBe('other')
  })
})
