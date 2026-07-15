// The Gemini call's retry classification: a per-request TIMEOUT is transient and
// must be retried to the max attempt count, while a genuine session sign-out (the
// external abort signal firing) is terminal and must NOT be retried. Same
// machinery as focus/gemini.test.ts.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  abortSignal: undefined as AbortSignal | undefined
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => h.abortSignal }))

import { extractMemory } from './gemini'
import type { BackendSession } from '../core/session'

const session = (): BackendSession => ({ apiBase: 'a', desktopApiBase: 'd', token: 't' })

// A fetch that never resolves on its own — it only rejects when the signal it was
// handed aborts, mirroring real fetch abort semantics (rejects with the reason).
function fetchThatAbortsWithSignal(): void {
  h.fetch.mockImplementation((_url: string, opts: { signal: AbortSignal }) => {
    const s = opts.signal
    return new Promise((_resolve, reject) => {
      const fail = (): void => reject(s.reason ?? new DOMException('aborted', 'AbortError'))
      if (s.aborted) return fail()
      s.addEventListener('abort', fail, { once: true })
    })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  h.abortSignal = undefined
})

afterEach(() => {
  vi.useRealTimers()
})

describe('extractMemory — retry classification', () => {
  it('retries a per-request timeout up to the max (3 attempts, 2s/8s backoff)', async () => {
    vi.useFakeTimers()
    h.abortSignal = undefined // no session abort in flight
    fetchThatAbortsWithSignal()

    const promise = extractMemory(session(), 'sys', 'prompt', 'BASE64')
    // Attach the rejection expectation synchronously so the rejection is handled.
    const assertion = expect(promise).rejects.toMatchObject({ name: 'TimeoutError' })

    await vi.advanceTimersByTimeAsync(30_000) // attempt 1 times out
    await vi.advanceTimersByTimeAsync(2_000) // backoff #1
    await vi.advanceTimersByTimeAsync(30_000) // attempt 2 times out
    await vi.advanceTimersByTimeAsync(8_000) // backoff #2
    await vi.advanceTimersByTimeAsync(30_000) // attempt 3 times out → throw

    await assertion
    expect(h.fetch).toHaveBeenCalledTimes(3)
  })

  it('does NOT retry a genuine session sign-out (single attempt, AbortError)', async () => {
    const ctrl = new AbortController()
    ctrl.abort() // the user signed out before the request went out
    h.abortSignal = ctrl.signal
    fetchThatAbortsWithSignal()

    await expect(extractMemory(session(), 'sys', 'prompt', 'BASE64')).rejects.toMatchObject({
      name: 'AbortError'
    })
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })

  it('returns the parsed result on a 200 (single attempt, no retry)', async () => {
    h.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        candidates: [
          {
            content: {
              parts: [
                {
                  text: JSON.stringify({
                    has_new_memory: true,
                    memories: [
                      { content: 'm', category: 'system', source_app: 'App', confidence: 0.9 }
                    ],
                    context_summary: 's',
                    current_activity: 'a'
                  })
                }
              ]
            }
          }
        ]
      })
    })
    const r = await extractMemory(session(), 'sys', 'prompt', 'BASE64')
    expect(r?.memories[0]).toEqual({
      content: 'm',
      category: 'system',
      sourceApp: 'App',
      confidence: 0.9
    })
    expect(h.fetch).toHaveBeenCalledTimes(1)
  })
})
