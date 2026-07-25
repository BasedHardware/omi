// The two-phase tool loop, exercised end to end with a scripted proxy. Each
// net.fetch resolves the next queued Gemini response; the loop's execute_sql and
// request_screenshot backends are injected fakes.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  queue: [] as unknown[]
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined }))

import { runTwoPhasePipeline } from './gemini'
import type { BackendSession } from '../core/session'

const session = (): BackendSession => ({ apiBase: 'a', desktopApiBase: 'd', token: 't' })

/** A response part carrying one functionCall. */
function fc(name: string, args: Record<string, unknown>): unknown {
  return { candidates: [{ content: { parts: [{ functionCall: { name, args } }] } }] }
}
/** A response with only text (no tool call). */
function textOnly(text: string): unknown {
  return { candidates: [{ content: { parts: [{ text }] } }] }
}

function queueResponses(responses: unknown[]): void {
  h.queue = [...responses]
  h.fetch.mockImplementation(async () => {
    const next = h.queue.shift()
    if (next === undefined)
      throw new Error('proxy queue exhausted — loop called more than scripted')
    return { ok: true, json: async () => next }
  })
}

const deps = (over: Partial<Parameters<typeof runTwoPhasePipeline>[0]> = {}) => ({
  session: session(),
  systemPrompt: 'sys',
  phase1Prompt: 'p1',
  buildPhase2Prompt: (f: string) => `p2:${f}`,
  execSql: vi.fn(() => 'SQL_RESULT'),
  loadScreenshot: vi.fn(async () => 'IMG_B64'),
  ...over
})

beforeEach(() => {
  vi.clearAllMocks()
  h.queue = []
})
afterEach(() => vi.restoreAllMocks())

describe('runTwoPhasePipeline', () => {
  it('happy path: SQL → request_screenshot → provide_advice', async () => {
    queueResponses([
      fc('execute_sql', { query: 'SELECT id FROM rewind_frames' }),
      fc('request_screenshot', { screenshot_id: 99, findings: 'token on screen' }),
      fc('provide_advice', {
        advice: 'Mask the token',
        headline: 'Token visible',
        category: 'productivity',
        source_app: 'Terminal',
        confidence: 0.92,
        context_summary: 'c',
        current_activity: 'a'
      })
    ])
    const d = deps()
    const result = await runTwoPhasePipeline(d)

    expect(d.execSql).toHaveBeenCalledWith('SELECT id FROM rewind_frames')
    expect(d.loadScreenshot).toHaveBeenCalledWith(99)
    expect(result.sqlCount).toBe(1)
    expect(result.insight).not.toBeNull()
    expect(result.insight?.advice).toBe('Mask the token')
    expect(result.insight?.confidence).toBe(0.92)
  })

  it('no_advice in Phase 1 exits early — no Phase 2, no screenshot load', async () => {
    queueResponses([fc('no_advice', { context_summary: 'c', current_activity: 'a' })])
    const d = deps()
    const result = await runTwoPhasePipeline(d)
    expect(result.insight).toBeNull()
    expect(d.loadScreenshot).not.toHaveBeenCalled()
    // one iteration only
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })

  it('Phase 1 TOLERATES an unknown tool (continues); Phase 2 still reachable', async () => {
    queueResponses([
      fc('bogus_tool', { whatever: 1 }), // unknown in phase 1 → continue
      fc('request_screenshot', { screenshot_id: 5, findings: 'f' }),
      fc('provide_advice', {
        advice: 'x',
        headline: 'h',
        category: 'learning',
        source_app: 'App',
        confidence: 0.9,
        context_summary: 'c',
        current_activity: 'a'
      })
    ])
    const result = await runTwoPhasePipeline(deps())
    expect(result.insight?.advice).toBe('x')
  })

  it('Phase 2 ENDS on an unknown tool (returns null)', async () => {
    queueResponses([
      fc('request_screenshot', { screenshot_id: 5, findings: 'f' }),
      fc('bogus_tool', { whatever: 1 }) // unknown in phase 2 → end
    ])
    const d = deps()
    const result = await runTwoPhasePipeline(d)
    expect(result.insight).toBeNull()
    // phase 2 stopped after the single unknown-tool response
    expect(h.fetch).toHaveBeenCalledTimes(2)
  })

  it('aborts Phase 2 when the screenshot cannot be loaded', async () => {
    queueResponses([fc('request_screenshot', { screenshot_id: 5, findings: 'f' })])
    const d = deps({ loadScreenshot: vi.fn(async () => null) })
    const result = await runTwoPhasePipeline(d)
    expect(result.insight).toBeNull()
  })

  it('breaks when the model returns no tool call at all', async () => {
    queueResponses([textOnly('just chatting')])
    const result = await runTwoPhasePipeline(deps())
    expect(result.insight).toBeNull()
  })
})
