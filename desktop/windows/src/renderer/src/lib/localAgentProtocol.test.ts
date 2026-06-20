import { describe, it, expect, vi } from 'vitest'
import {
  parseAction,
  formatContextBlock,
  GUARD_LINE,
  CONTEXT_BUDGET,
  raceWithBudget
} from './localAgentProtocol'

describe('parseAction', () => {
  it('parses local status without input', () => {
    expect(parseAction('{"action":"get_local_status","input":{}}')).toEqual({
      action: 'get_local_status',
      input: {}
    })
  })
  it('parses screen history search with object input', () => {
    expect(
      parseAction('{"action":"search_screen_history","input":{"query":"roadmap","days":3}}')
    ).toEqual({
      action: 'search_screen_history',
      input: { query: 'roadmap', days: 3 }
    })
  })
  it('normalizes screen history string input for tolerant model output', () => {
    expect(parseAction('{"action":"search_screen_history","input":"omi windows"}')).toEqual({
      action: 'search_screen_history',
      input: { query: 'omi windows' }
    })
  })
  it('parses execute_sql with input', () => {
    expect(parseAction('{"action":"execute_sql","input":"SELECT 1 FROM local_kg_nodes"}')).toEqual({
      action: 'execute_sql',
      input: { query: 'SELECT 1 FROM local_kg_nodes' }
    })
  })
  it('parses screenshot ids from object and scalar input', () => {
    expect(parseAction('{"action":"get_screenshot","input":{"screenshot_id":42}}')).toEqual({
      action: 'get_screenshot',
      input: { screenshot_id: 42 }
    })
    expect(parseAction('{"action":"get_screenshot","input":"43"}')).toEqual({
      action: 'get_screenshot',
      input: { screenshot_id: 43 }
    })
  })
  it('parses final', () => {
    expect(parseAction('```json\n{"action":"final"}\n```')).toEqual({ action: 'final' })
  })
  it('returns null for unknown, destructive, missing, or blank actions', () => {
    expect(parseAction('{"action":"delete_all"}')).toBeNull()
    expect(parseAction('{"action":"delete_task","input":{"task_id":"task-1"}}')).toBeNull()
    expect(parseAction('{"action":"complete_task","input":{"task_id":"task-1"}}')).toBeNull()
    expect(parseAction('{"action":"execute_sql","input":"  "}')).toBeNull()
    expect(parseAction('{"action":"search_screen_history","input":{}}')).toBeNull()
    expect(parseAction('{"action":"get_screenshot","input":{}}')).toBeNull()
    expect(parseAction('not json')).toBeNull()
  })
  // Real-world haiku output: prose + Claude's native <function_calls> tag +
  // a JSON array wrapper, with trailing characters after the object.
  it('parses an action wrapped in prose, <function_calls>, and an array', () => {
    const raw =
      'I\'ll search your screen.\n<function_calls>\n[{"action":"search_screen_history","input":{"query":"projects work"}}]'
    expect(parseAction(raw)).toEqual({
      action: 'search_screen_history',
      input: { query: 'projects work' }
    })
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
