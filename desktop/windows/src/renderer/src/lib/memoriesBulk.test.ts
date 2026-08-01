import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { Memory } from '../hooks/useMemories'

const omiApiGet = vi.fn()
const omiApiDelete = vi.fn()
vi.mock('./apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => omiApiGet(...args),
    delete: (...args: unknown[]) => omiApiDelete(...args)
  }
}))

import { fetchAllMemories, deleteMemoriesPaced } from './memoriesBulk'

function page(ids: string[]): { data: Partial<Memory>[] } {
  return { data: ids.map((id) => ({ id, uid: 'u', content: id, created_at: '', updated_at: '' })) }
}

beforeEach(() => {
  omiApiGet.mockReset()
  omiApiDelete.mockReset()
})

// Fakes GET /v3/memories: hard page cap 500, no first-page expansion.
function fakeBackend(
  total: number
): (
  path: string,
  config: { params: { limit: number; offset: number } }
) => Promise<{ data: Partial<Memory>[] }> {
  return async (_path, config) => {
    const { limit, offset } = config.params
    const effectiveLimit = Math.min(limit, 500)
    const end = Math.min(offset + effectiveLimit, total)
    if (offset >= total) return page([])
    return page(Array.from({ length: end - offset }, (_, i) => `m${offset + i}`))
  }
}

describe('fetchAllMemories', () => {
  it('fetches all 1200 memories in 500-row strides', async () => {
    omiApiGet.mockImplementation(fakeBackend(1200))

    const all = await fetchAllMemories()

    expect(all).toHaveLength(1200)
    expect(all.some((m) => m.id === 'm1199')).toBe(true)
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', { params: { limit: 500, offset: 0 } })
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', {
      params: { limit: 500, offset: 500 }
    })
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', {
      params: { limit: 500, offset: 1000 }
    })
  })

  it('pages a large account without small hops', async () => {
    omiApiGet.mockImplementation(fakeBackend(2500))

    const all = await fetchAllMemories()

    expect(all).toHaveLength(2500)
    expect(omiApiGet.mock.calls.length).toBeLessThan(8)
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', {
      params: { limit: 500, offset: 2000 }
    })
  })

  it('dedupes by id and stops once a full page adds nothing new (server ignoring offset)', async () => {
    const ids = Array.from({ length: 200 }, (_, i) => `id${i}`)
    omiApiGet.mockResolvedValueOnce(page(ids)).mockResolvedValueOnce(page(ids))

    const all = await fetchAllMemories()

    expect(all).toHaveLength(200)
    expect(omiApiGet).toHaveBeenCalledTimes(2)
  })
})

// A 429 pause is a normal part of any real bulk delete here, and Retry-After is
// measured in tens of seconds, so the pause has to stay cancellable.
describe('deleteMemoriesPaced Stop responsiveness', () => {
  const RETRY_AFTER_S = 30
  const rateLimited = (): unknown => ({
    response: { status: 429, headers: { 'retry-after': String(RETRY_AFTER_S) } }
  })

  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('does not delete one more memory when Stop is pressed during a rate-limit pause', async () => {
    // First attempt on 'a' is rate-limited; every later attempt would succeed.
    omiApiDelete.mockRejectedValueOnce(rateLimited()).mockResolvedValue({ data: {} })
    let stop = false
    const onResult = vi.fn()

    const run = deleteMemoriesPaced(['a', 'b'], onResult, () => stop)

    await vi.advanceTimersByTimeAsync(250) // first slice of the pause
    stop = true
    await vi.advanceTimersByTimeAsync(250) // next slice observes the Stop
    const tally = await run

    // Only the initial attempt on 'a' ever reached the server.
    expect(omiApiDelete).toHaveBeenCalledTimes(1)
    expect(omiApiDelete).toHaveBeenCalledWith('/v3/memories/a', expect.anything())
    // 'a' was cancelled mid-retry, so it is neither deleted nor failed, and its
    // row must not be dropped from the UI.
    expect(tally).toEqual({ deleted: 0, failed: 0, firstError: undefined })
    expect(onResult).not.toHaveBeenCalled()
  })

  it('ends the rate-limit pause within a poll interval instead of serving it out', async () => {
    omiApiDelete.mockRejectedValueOnce(rateLimited()).mockResolvedValue({ data: {} })
    let stop = false
    let settled = false

    const run = deleteMemoriesPaced(
      ['a'],
      () => {},
      () => stop
    )
    void run.then(() => {
      settled = true
    })

    // Prove the run actually reached the 429 pause before advancing any timer,
    // so the assertions below cannot pass on mock-flush ordering alone.
    await vi.advanceTimersByTimeAsync(0)
    expect(omiApiDelete).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(250)
    expect(settled).toBe(false) // still waiting out the 429, as it should be
    stop = true

    await vi.advanceTimersByTimeAsync(250)
    expect(settled).toBe(true) // returned on the next slice, not after 30s

    await run
  })

  it('returns without serving the pacing tail when Stop is already set', async () => {
    omiApiDelete.mockResolvedValue({ data: {} })
    let stop = false
    let settled = false

    const run = deleteMemoriesPaced(
      ['a', 'b'],
      () => {
        stop = true // user hits Stop the moment the first row disappears
      },
      () => stop
    )
    void run.then(() => {
      settled = true
    })

    // Stop is already set when the tail begins, so no tail timer is ever
    // scheduled and the run settles without virtual time passing at all.
    await vi.advanceTimersByTimeAsync(0)
    expect(settled).toBe(true)
    expect(vi.getTimerCount()).toBe(0)

    const tally = await run
    expect(omiApiDelete).toHaveBeenCalledTimes(1)
    expect(tally).toEqual({ deleted: 1, failed: 0, firstError: undefined })
  })

  it('cuts the pacing tail short when Stop lands after the wait has begun', async () => {
    omiApiDelete.mockResolvedValue({ data: {} })
    let stop = false
    let settled = false

    const run = deleteMemoriesPaced(
      ['a', 'b'],
      () => {},
      () => stop
    )
    void run.then(() => {
      settled = true
    })

    await vi.advanceTimersByTimeAsync(250) // tail underway, Stop not yet pressed
    expect(settled).toBe(false)
    stop = true

    await vi.advanceTimersByTimeAsync(250) // next slice observes it
    expect(settled).toBe(true) // not after the full 1100ms

    const tally = await run
    expect(omiApiDelete).toHaveBeenCalledTimes(1) // 'b' never attempted
    expect(tally).toEqual({ deleted: 1, failed: 0, firstError: undefined })
  })

  // retentionSweep.ts calls this with no `shouldStop`, so that path keeps its
  // single unsliced timer rather than polling it can never use.
  it('does not slice its waits for a caller that passes no shouldStop', async () => {
    omiApiDelete.mockResolvedValue({ data: {} })
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout')

    const run = deleteMemoriesPaced(['a'], () => {})
    await vi.advanceTimersByTimeAsync(1100)
    await run

    expect(setTimeoutSpy).toHaveBeenCalledTimes(1) // one 1100ms wait, not five slices
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1100)
  })

  it('still deletes every id and paces between them when Stop is never pressed', async () => {
    omiApiDelete.mockResolvedValue({ data: {} })
    const onResult = vi.fn()

    const run = deleteMemoriesPaced(['a', 'b'], onResult, () => false)
    await vi.advanceTimersByTimeAsync(1100 * 2 + 250)
    const tally = await run

    expect(omiApiDelete).toHaveBeenCalledTimes(2)
    expect(tally).toEqual({ deleted: 2, failed: 0, firstError: undefined })
    expect(onResult).toHaveBeenNthCalledWith(1, 'a', true, { deleted: 1, failed: 0 })
    expect(onResult).toHaveBeenNthCalledWith(2, 'b', true, { deleted: 2, failed: 0 })
  })

  it('waits out a rate limit and completes when the user lets it run', async () => {
    omiApiDelete.mockRejectedValueOnce(rateLimited()).mockResolvedValue({ data: {} })

    const run = deleteMemoriesPaced(
      ['a'],
      () => {},
      () => false
    )
    await vi.advanceTimersByTimeAsync(RETRY_AFTER_S * 1000 + 1100 + 250)
    const tally = await run

    expect(omiApiDelete).toHaveBeenCalledTimes(2) // rate-limited, then retried
    expect(tally).toEqual({ deleted: 1, failed: 0, firstError: undefined })
  })
})
