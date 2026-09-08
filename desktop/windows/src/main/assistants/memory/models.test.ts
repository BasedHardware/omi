// Response parse/validation: a structured-output model still occasionally returns
// prose, an empty part, or a category outside the enum — a bad top-level answer
// must become null (no extraction), never a thrown error; a bad ENTRY inside the
// memories array is filtered out, never coerced to a fake category.
import { describe, expect, it } from 'vitest'
import { parseMemoryExtraction } from './models'

describe('parseMemoryExtraction', () => {
  it('parses a complete, valid response', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: true,
        memories: [
          {
            content: 'User works at Acme Corp',
            category: 'system',
            source_app: 'Slack',
            confidence: 0.9
          }
        ],
        context_summary: 'Viewing a Slack workspace',
        current_activity: 'Reading messages'
      })
    )
    expect(r).toEqual({
      hasNewMemory: true,
      memories: [
        {
          content: 'User works at Acme Corp',
          category: 'system',
          sourceApp: 'Slack',
          confidence: 0.9
        }
      ],
      contextSummary: 'Viewing a Slack workspace',
      currentActivity: 'Reading messages'
    })
  })

  it('defaults missing optional top-level strings to empty (only the array is load-bearing)', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: true,
        memories: [{ content: 'x', category: 'interesting', source_app: 'X', confidence: 0.8 }]
      })
    )
    expect(r?.contextSummary).toBe('')
    expect(r?.currentActivity).toBe('')
    expect(r?.hasNewMemory).toBe(true)
    expect(r?.memories).toHaveLength(1)
  })

  it('filters out a memory whose category is outside the enum (never coerces it)', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: true,
        memories: [{ content: 'x', category: 'wisdom', source_app: 'X', confidence: 0.9 }],
        context_summary: 's',
        current_activity: 'a'
      })
    )
    // Bad entry dropped → empty array, but a valid (empty) result, not null.
    expect(r).not.toBeNull()
    expect(r?.memories).toEqual([])
  })

  it('filters out a memory with a non-numeric confidence (the gate needs a number)', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: true,
        memories: [{ content: 'x', category: 'system', source_app: 'X', confidence: 'high' }],
        context_summary: 's',
        current_activity: 'a'
      })
    )
    expect(r?.memories).toEqual([])
  })

  it('keeps the valid memory when the array mixes good and bad entries', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: true,
        memories: [
          { content: 'bad', category: 'nope', source_app: 'X', confidence: 0.9 },
          { content: 'good', category: 'system', source_app: 'Notion', confidence: 0.95 }
        ],
        context_summary: 's',
        current_activity: 'a'
      })
    )
    expect(r?.memories).toEqual([
      { content: 'good', category: 'system', sourceApp: 'Notion', confidence: 0.95 }
    ])
  })

  it('returns an empty memories array (not null) when memories is empty', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({
        has_new_memory: false,
        memories: [],
        context_summary: 'nothing notable',
        current_activity: 'idle'
      })
    )
    expect(r).not.toBeNull()
    expect(r?.memories).toEqual([])
    expect(r?.hasNewMemory).toBe(false)
  })

  it('rejects non-JSON prose', () => {
    expect(parseMemoryExtraction('The user appears to work at Acme.')).toBeNull()
  })

  it('rejects a JSON array / non-object at the top level', () => {
    expect(parseMemoryExtraction('[]')).toBeNull()
    expect(parseMemoryExtraction('null')).toBeNull()
    expect(parseMemoryExtraction('42')).toBeNull()
  })

  it('treats a missing memories array as empty rather than throwing', () => {
    const r = parseMemoryExtraction(
      JSON.stringify({ has_new_memory: false, context_summary: 's', current_activity: 'a' })
    )
    expect(r?.memories).toEqual([])
  })
})
