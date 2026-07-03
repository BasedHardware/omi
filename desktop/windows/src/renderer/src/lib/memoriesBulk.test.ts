import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchAllMemories, deleteMemoriesPaced } from './memoriesBulk'
import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

vi.mock('./apiClient', () => ({
  omiApi: {
    get: vi.fn(),
    delete: vi.fn()
  }
}))

const mockedGet = vi.mocked(omiApi.get)
const mockedDelete = vi.mocked(omiApi.delete)

function mem(id: string): Memory {
  return { id, uid: 'u', content: `memory ${id}`, created_at: '', updated_at: '' } as Memory
}

// Mirror of the backend's pagination semantics (backend/routers/memories.py
// _legacy_get_memories): offset=0 EXPANDS the limit to 5000 regardless of the
// requested page size; any other offset serves the clamped requested limit.
function serveFrom(rows: Memory[]): void {
  mockedGet.mockImplementation(
    async (_url: string, config?: { params?: { limit?: number; offset?: number } }) => {
      const limit = config?.params?.limit ?? 100
      const offset = config?.params?.offset ?? 0
      const effectiveLimit = offset === 0 ? 5000 : Math.max(1, Math.min(limit, 5000))
      return { data: rows.slice(offset, offset + effectiveLimit) }
    }
  )
}

beforeEach(() => {
  mockedGet.mockReset()
  mockedDelete.mockReset()
})

describe('fetchAllMemories', () => {
  it('fetches an account larger than the 5000-row first page completely, without duplicates', async () => {
    const total = 5200
    serveFrom(Array.from({ length: total }, (_, i) => mem(`m${i}`)))
    const out = await fetchAllMemories()
    expect(out).toHaveLength(total)
    expect(new Set(out.map((m) => m.id)).size).toBe(total)
  })

  it('handles a small account in one short page', async () => {
    serveFrom(Array.from({ length: 150 }, (_, i) => mem(`m${i}`)))
    const out = await fetchAllMemories()
    expect(out).toHaveLength(150)
    expect(mockedGet).toHaveBeenCalledTimes(1)
  })

  it('handles exactly one expanded first page (no phantom extra rows)', async () => {
    serveFrom(Array.from({ length: 5000 }, (_, i) => mem(`m${i}`)))
    const out = await fetchAllMemories()
    expect(out).toHaveLength(5000)
  })

  it('terminates against a server that ignores offset (dedupe guard)', async () => {
    const rows = Array.from({ length: 5000 }, (_, i) => mem(`m${i}`))
    mockedGet.mockImplementation(async () => ({ data: rows }))
    const out = await fetchAllMemories()
    expect(out).toHaveLength(5000)
    expect(mockedGet.mock.calls.length).toBeLessThan(5)
  })
})

describe('deleteMemoriesPaced', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not delete another memory when Stop arrives during a rate-limit wait', async () => {
    let stop = false
    mockedDelete.mockRejectedValue({
      response: { status: 429, headers: { 'retry-after': '30' } }
    })
    const done = deleteMemoriesPaced(
      ['a', 'b'],
      () => {},
      () => stop
    )
    // First delete fires immediately, gets a 429, and the 30s wait begins.
    await vi.advanceTimersByTimeAsync(1000)
    expect(mockedDelete).toHaveBeenCalledTimes(1)
    // User presses Stop mid-wait. No further delete may go out — neither a
    // retry of 'a' nor a first attempt at 'b'.
    stop = true
    await vi.advanceTimersByTimeAsync(1_200_000)
    const res = await done
    expect(mockedDelete).toHaveBeenCalledTimes(1)
    expect(res.deleted).toBe(0)
    expect(res.failed).toBe(0)
  })

  it('retries through a 429 and completes when not stopped', async () => {
    const waits: number[] = []
    mockedDelete
      .mockRejectedValueOnce({ response: { status: 429, headers: { 'retry-after': '2' } } })
      .mockResolvedValue({ data: {} })
    const done = deleteMemoriesPaced(
      ['a', 'b'],
      () => {},
      undefined,
      (s) => waits.push(s)
    )
    await vi.advanceTimersByTimeAsync(60_000)
    const res = await done
    expect(res).toMatchObject({ deleted: 2, failed: 0 })
    expect(mockedDelete).toHaveBeenCalledTimes(3) // a (429), a (ok), b (ok)
    expect(waits).toEqual([2, 0]) // pause reported, then cleared
  })

  it('honors Stop between ids (pre-existing behavior)', async () => {
    let stop = false
    mockedDelete.mockResolvedValue({ data: {} })
    const done = deleteMemoriesPaced(
      ['a', 'b', 'c'],
      (_id, _ok, t) => {
        if (t.deleted === 1) stop = true
      },
      () => stop
    )
    await vi.advanceTimersByTimeAsync(60_000)
    const res = await done
    expect(res.deleted).toBe(1)
    expect(mockedDelete).toHaveBeenCalledTimes(1)
  })

  it('treats 404 as already gone and keeps going', async () => {
    mockedDelete
      .mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValue({ data: {} })
    const done = deleteMemoriesPaced(['a', 'b'], () => {})
    await vi.advanceTimersByTimeAsync(60_000)
    const res = await done
    expect(res).toMatchObject({ deleted: 2, failed: 0 })
  })
})
