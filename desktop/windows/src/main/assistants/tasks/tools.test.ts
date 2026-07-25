import { describe, expect, it } from 'vitest'
import { TASK_TOOLS, type TaskFunctionDeclaration } from './tools'

/** Look a declaration up by name without a non-null assertion. */
function decl(name: string): TaskFunctionDeclaration {
  const d = TASK_TOOLS.function_declarations.find((x) => x.name === name)
  if (!d) throw new Error(`no such tool declaration: ${name}`)
  return d
}

describe('TaskAssistant tool declarations', () => {
  it('offers the 5 tools in Mac order', () => {
    const names = TASK_TOOLS.function_declarations.map((d) => d.name)
    expect(names).toEqual([
      'search_similar',
      'search_keywords',
      'no_task_found',
      'extract_task',
      'reject_task'
    ])
  })

  it('search_similar / search_keywords each require only { query: string }', () => {
    for (const name of ['search_similar', 'search_keywords']) {
      const t = decl(name)
      expect(Object.keys(t.parameters.properties)).toEqual(['query'])
      expect(t.parameters.required).toEqual(['query'])
      expect(t.parameters.properties.query.type).toBe('string')
    }
  })

  it('no_task_found / reject_task require their summary fields', () => {
    expect(decl('no_task_found').parameters.required).toEqual([
      'context_summary',
      'current_activity'
    ])
    expect(decl('reject_task').parameters.required).toEqual([
      'reason',
      'context_summary',
      'current_activity'
    ])
  })
})

describe('extract_task schema', () => {
  const extract = decl('extract_task')

  // The 19 fields in Mac's declared order (TA:1005–1026).
  const EXPECTED_FIELDS = [
    'title',
    'description',
    'priority',
    'tags',
    'source_app',
    'inferred_deadline',
    'confidence',
    'context_summary',
    'current_activity',
    'source_category',
    'source_subcategory',
    'capture_kind',
    'owner',
    'concrete_deliverable',
    'public_broadcast',
    'direct_mention',
    'duplicate_of',
    'refines_task',
    'ownership_confidence'
  ]

  it('declares exactly 19 fields, in Mac order, and every one is required', () => {
    expect(EXPECTED_FIELDS).toHaveLength(19)
    expect(Object.keys(extract.parameters.properties)).toEqual(EXPECTED_FIELDS)
    expect(extract.parameters.required).toEqual(EXPECTED_FIELDS)
  })

  it('carries the right primitive types (incl. the tags array with a string items spec)', () => {
    const p = extract.parameters.properties
    expect(p.title.type).toBe('string')
    expect(p.description.type).toBe('string')
    expect(p.source_app.type).toBe('string')
    expect(p.inferred_deadline.type).toBe('string')
    expect(p.context_summary.type).toBe('string')
    expect(p.current_activity.type).toBe('string')
    expect(p.duplicate_of.type).toBe('string')
    expect(p.refines_task.type).toBe('string')
    expect(p.confidence.type).toBe('number')
    expect(p.ownership_confidence.type).toBe('number')
    expect(p.concrete_deliverable.type).toBe('boolean')
    expect(p.public_broadcast.type).toBe('boolean')
    expect(p.direct_mention.type).toBe('boolean')
    expect(p.tags.type).toBe('array')
    expect(p.tags.items).toEqual({ type: 'string' })
  })

  it('declares the exact enum sets, and only on the enum fields', () => {
    const p = extract.parameters.properties
    expect(p.priority.enum).toEqual(['high', 'medium', 'low'])
    expect(p.owner.enum).toEqual(['user', 'other', 'unknown'])
    expect(p.source_category.enum).toEqual([
      'direct_request',
      'self_generated',
      'calendar_driven',
      'reactive',
      'external_system',
      'other'
    ])
    expect(p.capture_kind.enum).toEqual([
      'explicit_command',
      'clear_commitment',
      'direct_request',
      'inferred_next_step',
      'already_done'
    ])
    expect(p.source_subcategory.enum).toEqual([
      'message',
      'meeting',
      'mention',
      'commitment',
      'idea',
      'reminder',
      'goal_subtask',
      'event_prep',
      'recurring',
      'deadline',
      'error',
      'notification',
      'observation',
      'project_tool',
      'alert',
      'documentation',
      'other'
    ])
    // A non-enum field must not carry a stray enum.
    expect(p.title.enum).toBeUndefined()
    expect(p.tags.enum).toBeUndefined()
  })

  it('keeps the verbatim title guardrail (6–15 words, name a specific person/project)', () => {
    expect(extract.parameters.properties.title.description).toBe(
      "Verb-first task title, 6–15 words. MUST name a specific person/project/artifact and a concrete action. If you can't write 6+ specific words, call no_task_found instead."
    )
  })
})
