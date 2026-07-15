// The Task Gemini wire layer, exercised with a scripted proxy. Each net.fetch
// resolves the next queued response (or an HTTP error / a hang); the wire layer
// carries no dispatch, so tests assert on the exact request bodies it sends and
// its retry/fallback/timeout transport behavior.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ fetch: vi.fn() }))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined }))

import { sendInitialTurn, sendToolResponseTurn, GeminiHttpError, TASK_MODEL } from './geminiWire'
import type { BackendSession } from '../core/session'
import type { GeminiTool } from '../insight/models'

const session = (): BackendSession => ({ apiBase: 'a', desktopApiBase: 'd', token: 't' })

const TOOL: GeminiTool = {
  function_declarations: [
    {
      name: 'extract_task',
      description: 'x',
      parameters: { type: 'object', properties: {}, required: [] }
    }
  ]
}

/** A response part carrying one functionCall. */
function fc(name: string, args: Record<string, unknown>): unknown {
  return { candidates: [{ content: { parts: [{ functionCall: { name, args } }] } }] }
}
/** Same, plus an opaque thoughtSignature the wire layer must echo back. */
function fcSig(name: string, args: Record<string, unknown>, sig: string): unknown {
  return {
    candidates: [{ content: { parts: [{ functionCall: { name, args }, thoughtSignature: sig }] } }]
  }
}
function ok(json: unknown): unknown {
  return { ok: true, json: async () => json }
}
function httpErr(status: number): unknown {
  return { ok: false, status }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function bodyOf(i: number): any {
  return JSON.parse(h.fetch.mock.calls[i][1].body)
}
function urlOf(i: number): string {
  return h.fetch.mock.calls[i][0]
}

const initial = {
  session: session(),
  systemPrompt: 'sys',
  tool: TOOL,
  prompt: 'look',
  imageBase64: 'IMG'
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('geminiWire', () => {
  it('forcing turn: tool_config mode ANY, the inlineData frame, flash model, thinkingBudget 1024', async () => {
    h.fetch.mockResolvedValueOnce(ok(fc('no_task_found', {})))
    const { turn } = await sendInitialTurn(initial)

    expect(turn.toolCalls[0].name).toBe('no_task_found')
    const body = bodyOf(0)
    expect(body.tool_config).toEqual({ function_calling_config: { mode: 'ANY' } })
    expect(body.contents[0]).toEqual({
      role: 'user',
      parts: [{ text: 'look' }, { inlineData: { mimeType: 'image/jpeg', data: 'IMG' } }]
    })
    expect(body.generation_config.thinking_config.thinking_budget).toBe(1024)
    expect(urlOf(0)).toContain(`/models/${TASK_MODEL}:generateContent`)
  })

  it('subsequent turn omits tool_config and appends the exact functionCall/functionResponse round-trip', async () => {
    h.fetch.mockResolvedValueOnce(ok(fcSig('search_similar', { query: 'deck' }, 'SIG123')))
    const { turn, contents } = await sendInitialTurn(initial)
    const call = turn.toolCalls[0]

    h.fetch.mockResolvedValueOnce(ok(fc('no_task_found', {})))
    const next = await sendToolResponseTurn({
      session: session(),
      systemPrompt: 'sys',
      tool: TOOL,
      contents,
      call,
      result: '[]'
    })

    expect(next.toolCalls[0].name).toBe('no_task_found')
    const body = bodyOf(1)
    expect(body.tool_config).toBeUndefined()
    // Transcript: [initial user+frame, model functionCall (sig preserved), user functionResponse].
    expect(body.contents).toHaveLength(3)
    expect(body.contents[1]).toEqual({
      role: 'model',
      parts: [
        {
          functionCall: { name: 'search_similar', args: { query: 'deck' } },
          thoughtSignature: 'SIG123'
        }
      ]
    })
    expect(body.contents[2]).toEqual({
      role: 'user',
      parts: [{ functionResponse: { name: 'search_similar', response: { result: '[]' } } }]
    })
  })

  it('retries a transient (5xx) error, then succeeds', async () => {
    vi.useFakeTimers()
    h.fetch.mockResolvedValueOnce(httpErr(500)).mockResolvedValueOnce(ok(fc('no_task_found', {})))

    let res: Awaited<ReturnType<typeof sendInitialTurn>> | undefined
    const p = sendInitialTurn(initial).then((r) => {
      res = r
    })
    await vi.advanceTimersByTimeAsync(2_000) // the first backoff
    await p

    expect(res?.turn.toolCalls[0].name).toBe('no_task_found')
    expect(h.fetch).toHaveBeenCalledTimes(2)
  })

  it('throws GeminiHttpError on a non-transient (4xx) error, with no retry', async () => {
    h.fetch.mockResolvedValueOnce(httpErr(400))
    let err: unknown
    await sendInitialTurn(initial).catch((e) => {
      err = e
    })
    expect(err).toBeInstanceOf(GeminiHttpError)
    expect((err as GeminiHttpError).status).toBe(400)
    // A 4xx never retries — a single fetch.
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })

  it('runs the fallback round after the primary exhausts its 3 attempts', async () => {
    vi.useFakeTimers()
    h.fetch
      .mockResolvedValueOnce(httpErr(500)) // primary attempt 1
      .mockResolvedValueOnce(httpErr(500)) // primary attempt 2
      .mockResolvedValueOnce(httpErr(500)) // primary attempt 3 — exhausts the round
      .mockResolvedValueOnce(ok(fc('no_task_found', {}))) // fallback round, attempt 1

    let res: Awaited<ReturnType<typeof sendInitialTurn>> | undefined
    const p = sendInitialTurn(initial).then((r) => {
      res = r
    })
    await vi.advanceTimersByTimeAsync(2_000 + 8_000) // the two in-round backoffs
    await p

    expect(res?.turn.toolCalls[0].name).toBe('no_task_found')
    // 4 calls proves the loop went past the primary's 3-attempt cap into the fallback.
    expect(h.fetch).toHaveBeenCalledTimes(4)
  })

  it('surfaces a per-call timeout (transient) after exhausting both rounds', async () => {
    vi.useFakeTimers()
    // Never settles until its request is aborted — the way net.fetch behaves.
    h.fetch.mockImplementation(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener(
            'abort',
            () => reject(new DOMException('aborted', 'AbortError')),
            {
              once: true
            }
          )
        })
    )

    let err: unknown
    const p = sendInitialTurn(initial).catch((e) => {
      err = e
    })
    // 2 rounds × 3 attempts × 300s + the in-round backoffs — advance well past it.
    await vi.advanceTimersByTimeAsync(2_100_000)
    await p

    expect(err).toBeInstanceOf(DOMException)
    expect((err as DOMException).name).toBe('TimeoutError')
    expect(h.fetch).toHaveBeenCalledTimes(6)
  })
})
