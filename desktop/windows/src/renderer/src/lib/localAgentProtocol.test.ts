import { describe, it, expect, vi } from 'vitest'
import {
  parseAction,
  formatContextBlock,
  GUARD_LINE,
  CONTEXT_BUDGET,
  raceWithBudget
} from './localAgentProtocol'

describe('parseAction', () => {
  it('parses query_kg with input', () => {
    expect(parseAction('{"action":"query_kg","input":"projects"}')).toEqual({
      action: 'query_kg',
      input: 'projects'
    })
  })
  it('parses search_files with optional fileType', () => {
    expect(parseAction('{"action":"search_files","input":"omi","fileType":"code"}')).toEqual({
      action: 'search_files',
      input: 'omi',
      fileType: 'code'
    })
  })
  it('parses search_memories with input', () => {
    expect(parseAction('{"action":"search_memories","input":"omi windows"}')).toEqual({
      action: 'search_memories',
      input: 'omi windows'
    })
  })
  it('parses execute_sql with input', () => {
    expect(
      parseAction('{"action":"execute_sql","input":"SELECT 1 FROM local_kg_nodes"}')
    ).toEqual({ action: 'execute_sql', input: 'SELECT 1 FROM local_kg_nodes' })
  })
  it('parses final', () => {
    expect(parseAction('```json\n{"action":"final"}\n```')).toEqual({ action: 'final' })
  })
  it('returns null for unknown/missing action or blank input', () => {
    expect(parseAction('{"action":"delete_all"}')).toBeNull()
    expect(parseAction('{"action":"query_kg","input":"  "}')).toBeNull()
    expect(parseAction('not json')).toBeNull()
  })
  // Real-world haiku output: prose + Claude's native <function_calls> tag +
  // a JSON array wrapper, with trailing characters after the object.
  it('parses an action wrapped in prose, <function_calls>, and an array', () => {
    const raw =
      'I\'ll search your files.\n<function_calls>\n[{"action": "query_kg", "input": "projects work"}]'
    expect(parseAction(raw)).toEqual({ action: 'query_kg', input: 'projects work' })
  })
  it('parses a bare object preceded by prose and followed by trailing text', () => {
    expect(parseAction('Sure! {"action":"final"} done')).toEqual({ action: 'final' })
  })
})

describe('formatContextBlock', () => {
  it('returns empty string when there is nothing to show (short-circuit)', () => {
    expect(formatContextBlock([])).toBe('')
    expect(formatContextBlock([{ heading: 'X', items: [] }])).toBe('')
  })

  it('renders sections, omits empty ones, and appends the guard line', () => {
    const out = formatContextBlock([
      { heading: 'Projects', items: ['omi-windows: Electron app'] },
      { heading: 'Empty', items: [] }
    ])
    expect(out).toContain('Local context:')
    expect(out).toContain('Projects:')
    expect(out).toContain('- omi-windows: Electron app')
    expect(out).not.toContain('Empty:')
    expect(out.endsWith(GUARD_LINE)).toBe(true)
  })

  it('truncates the body to the budget but still appends the guard line', () => {
    const items = Array.from({ length: 500 }, (_, i) => `item-${i} ${'x'.repeat(40)}`)
    const out = formatContextBlock([{ heading: 'Files', items }])
    expect(out.length).toBeLessThanOrEqual(CONTEXT_BUDGET + GUARD_LINE.length + 4)
    expect(out.endsWith(GUARD_LINE)).toBe(true)
  })
})

describe('raceWithBudget', () => {
  it('resolves with the value when the promise settles before the budget', async () => {
    const out = await raceWithBudget(Promise.resolve('v'), 1000, 'fallback')
    expect(out).toBe('v')
  })

  it('resolves with the fallback when the budget expires first', async () => {
    vi.useFakeTimers()
    const never = new Promise<string>(() => {})
    const p = raceWithBudget(never, 1000, 'fallback')
    await vi.advanceTimersByTimeAsync(1000)
    expect(await p).toBe('fallback')
    vi.useRealTimers()
  })

  it('resolves with the fallback when the promise rejects (never throws)', async () => {
    const out = await raceWithBudget(Promise.reject(new Error('boom')), 1000, [] as string[])
    expect(out).toEqual([])
  })
})
