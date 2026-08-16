// The single-phase multi-tool extraction loop, driven by scripted tool-call
// sequences. All impure edges (the two wire send functions, the two search
// backends, the context assembler) are injected, so these tests assert the pure
// dispatch: the terminal rules, the multi-task "look again" flow, the REJECTED
// retry, and the 8-call iteration cap — plus the exact functionResponse text the
// loop sends back on each turn.
//
// The module-level mocks below exist only so importing loop.ts (which statically
// imports geminiWire/electron, context/db, and the profile service) doesn't drag
// in the native DB or Electron. The loop never CALLS them here — every dependency
// is overridden per test via `deps`.
import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({ net: { fetch: vi.fn() } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined }))
vi.mock('../aiUserProfile/service', () => ({ getLatestProfileText: () => null }))
vi.mock('../../ipc/db', () => ({
  getTopRelevanceActionItems: () => [],
  getRecentActiveActionItems: () => [],
  getAllStagedTasks: () => [],
  getLocalActionItems: () => []
}))

import { runExtractionLoop, TASK_MAX_ITERS, type ExtractionLoopDeps } from './loop'
import type { Content, ToolTurn } from './geminiWire'
import type { ToolCall } from '../insight/models'
import type { BackendSession } from '../core/session'

// --- Verbatim functionResponse strings (Mac TaskAssistant.swift), asserted below.
const REJECT_LOOK_AGAIN =
  'REJECTED that candidate (duplicate / already tracked). ' +
  'Look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment that is NOT a duplicate of any existing task? ' +
  'If yes, search_similar for it and extract it. ' +
  'If no other commitment remains, call no_task_found.'

function lookAgain(title: string): string {
  return (
    `EXTRACTED: "${title}". ` +
    'Now look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment from a different request or different deliverable? ' +
    '(Same person asking for two different things counts as two tasks.) ' +
    'If yes, search_similar for the next one and extract it. ' +
    'If no other commitment remains, call no_task_found.'
  )
}

function rejected(error: string, title: string, words: number): string {
  return (
    `REJECTED: ${error}. ` +
    `Your title was: "${title}" (${words} words). ` +
    'Either rewrite with 6+ words including a specific person/project name and concrete action, ' +
    'or call no_task_found if you cannot be more specific.'
  )
}

// A title that passes validateTaskTitle: 7 words, a proper noun after the verb.
const VALID_TITLE = 'Send Sarah the Q4 budget spreadsheet today'
const VALID_TITLE_2 = 'Review Thinh PR for the auth refactor'

const session = (): BackendSession => ({ apiBase: 'a', desktopApiBase: 'd', token: 't' })

function turn(name: string, args: Record<string, unknown> = {}): ToolTurn {
  return { toolCalls: [{ name, args }], text: '' }
}
function noCallTurn(): ToolTurn {
  return { toolCalls: [], text: '' }
}

/** Scripts a wire conversation: sendInitial yields script[0]; the i-th sendResponse
 *  yields script[i+1] (or a no-call turn when the script runs out), capturing every
 *  {call, result} pair the loop hands the round-trip. */
function harness(script: ToolTurn[]): {
  deps: Partial<ExtractionLoopDeps>
  sent: { call: ToolCall; result: string }[]
  sendInitial: ReturnType<typeof vi.fn>
  sendResponse: ReturnType<typeof vi.fn>
  vector: ReturnType<typeof vi.fn>
  keyword: ReturnType<typeof vi.fn>
} {
  const sent: { call: ToolCall; result: string }[] = []
  let idx = 0
  const sendInitial = vi.fn(async () => ({ turn: script[0], contents: [] as Content[] }))
  const sendResponse = vi.fn(async (opts: { call: ToolCall; result: string }) => {
    sent.push({ call: opts.call, result: opts.result })
    idx += 1
    return script[idx] ?? noCallTurn()
  })
  const vector = vi.fn(async () => [])
  const keyword = vi.fn(async () => [])
  return {
    deps: {
      sendInitial: sendInitial as unknown as ExtractionLoopDeps['sendInitial'],
      sendResponse: sendResponse as unknown as ExtractionLoopDeps['sendResponse'],
      executeVectorSearch: vector,
      executeKeywordSearch: keyword,
      assembleContext: async () => ''
    },
    sent,
    sendInitial,
    sendResponse,
    vector,
    keyword
  }
}

const params = {
  session: session(),
  app: 'Slack',
  today: '2026-07-15 (Wednesday)',
  isMessaging: true,
  imageBase64: 'IMG'
}

describe('runExtractionLoop', () => {
  it('(a) search_similar → extract_task → no_task_found: one task + the search round-trip', async () => {
    const h = harness([
      turn('search_similar', { query: 'q4 budget' }),
      turn('extract_task', { title: VALID_TITLE }),
      turn('no_task_found', {})
    ])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toHaveLength(1)
    expect(results[0].title).toBe(VALID_TITLE)
    // The vector backend ran with the model's query, and its (empty) result was
    // round-tripped back as the search functionResponse.
    expect(h.vector).toHaveBeenCalledWith('q4 budget')
    expect(h.sent[0].call).toEqual({ name: 'search_similar', args: { query: 'q4 budget' } })
    expect(h.sent[0].result).toBe('[]')
    // Then the extract acknowledged with the "look again" text.
    expect(h.sent[1].result).toBe(lookAgain(VALID_TITLE))
    // no_task_found is terminal → no further turn.
    expect(h.sendResponse).toHaveBeenCalledTimes(2)
  })

  it('(b) two extract_tasks then no_task_found: multi-task, verbatim look-again text sent', async () => {
    const h = harness([
      turn('extract_task', { title: VALID_TITLE }),
      turn('extract_task', { title: VALID_TITLE_2 }),
      turn('no_task_found', {})
    ])
    const results = await runExtractionLoop(params, h.deps)

    expect(results.map((t) => t.title)).toEqual([VALID_TITLE, VALID_TITLE_2])
    expect(h.sent[0].result).toBe(lookAgain(VALID_TITLE))
    expect(h.sent[1].result).toBe(lookAgain(VALID_TITLE_2))
  })

  it('(c) invalid title → verbatim REJECTED retry → valid extract → success', async () => {
    const h = harness([
      turn('extract_task', { title: 'Investigate' }), // 1 word → too short
      turn('extract_task', { title: VALID_TITLE }),
      turn('no_task_found', {})
    ])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toHaveLength(1)
    expect(results[0].title).toBe(VALID_TITLE)
    expect(h.sent[0].result).toBe(
      rejected('Title too short (1 words, minimum 6)', 'Investigate', 1)
    )
    expect(h.sent[1].result).toBe(lookAgain(VALID_TITLE))
  })

  it('reject_task is per-candidate (not terminal): feeds the reject look-again and continues', async () => {
    const h = harness([
      turn('reject_task', { reason: 'duplicate of existing active task' }),
      turn('extract_task', { title: VALID_TITLE }),
      turn('no_task_found', {})
    ])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toHaveLength(1)
    expect(h.sent[0].result).toBe(REJECT_LOOK_AGAIN)
    expect(h.sent[1].result).toBe(lookAgain(VALID_TITLE))
  })

  it('(d) no_task_found immediately → [] and no response turn', async () => {
    const h = harness([turn('no_task_found', {})])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toEqual([])
    expect(h.sendResponse).not.toHaveBeenCalled()
  })

  it('unknown tool → terminal, returns what it had, no further turn', async () => {
    const h = harness([turn('extract_task', { title: VALID_TITLE }), turn('some_future_tool', {})])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toHaveLength(1)
    // After the extract (turn 1 → sendResponse #1), the unknown tool on turn 2 is
    // terminal: no functionResponse for it.
    expect(h.sendResponse).toHaveBeenCalledTimes(1)
  })

  it('(e) iteration cap: 8 model calls total, stops cleanly with accumulated results', async () => {
    // Every turn is a search → never terminal. The loop must stop at the budget.
    const alwaysSearch: ToolTurn[] = Array.from({ length: TASK_MAX_ITERS + 5 }, () =>
      turn('search_similar', { query: 'q' })
    )
    const h = harness(alwaysSearch)
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toEqual([])
    // 1 initial call + (TASK_MAX_ITERS - 1) response turns = TASK_MAX_ITERS calls; no 9th.
    expect(h.sendResponse).toHaveBeenCalledTimes(TASK_MAX_ITERS - 1)
  })

  it('no tool call on the initial turn → [] immediately', async () => {
    const h = harness([noCallTurn()])
    const results = await runExtractionLoop(params, h.deps)

    expect(results).toEqual([])
    expect(h.sendResponse).not.toHaveBeenCalled()
  })
})
