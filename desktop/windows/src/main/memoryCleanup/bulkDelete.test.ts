import { describe, it, expect, vi } from 'vitest'
import {
  classifyStatus,
  backoffMs,
  bulkDeleteMemories,
  MEMORIES_DELETE_BATCH_SIZE,
  type BulkDeleteFetch,
  type BulkDeleteResponse
} from './bulkDelete'

describe('classifyStatus', () => {
  it('treats 2xx as ok', () => {
    expect(classifyStatus(200)).toBe('ok')
    expect(classifyStatus(204)).toBe('ok')
  })
  it('treats 404 as gone (idempotent success)', () => {
    expect(classifyStatus(404)).toBe('gone')
  })
  it('treats 409 as retry so account-gate contention honors Retry-After', () => {
    expect(classifyStatus(409)).toBe('retry')
  })
  it('treats 429 and 5xx as retry', () => {
    expect(classifyStatus(429)).toBe('retry')
    expect(classifyStatus(500)).toBe('retry')
    expect(classifyStatus(503)).toBe('retry')
  })
  it('treats auth/client errors as fail', () => {
    expect(classifyStatus(401)).toBe('fail')
    expect(classifyStatus(400)).toBe('fail')
  })
})

describe('backoffMs', () => {
  it('honors a numeric Retry-After header (seconds -> ms, capped)', () => {
    expect(backoffMs(1, '2')).toBe(2000)
    expect(backoffMs(5, '120')).toBe(60_000) // capped
  })
  it('falls back to exponential backoff with jitter when no header', () => {
    expect(backoffMs(1)).toBeGreaterThanOrEqual(1000)
    expect(backoffMs(1)).toBeLessThan(1400)
    expect(backoffMs(3)).toBeGreaterThanOrEqual(4000)
    expect(backoffMs(99)).toBeLessThan(16_400) // capped at 16s + jitter
  })
  it('ignores a non-numeric Retry-After', () => {
    expect(backoffMs(1, 'soon')).toBeGreaterThanOrEqual(1000)
  })
})

function jsonResponse(status: number, headers: Record<string, string> = {}): BulkDeleteResponse {
  return {
    status,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null },
    text: async () => (status >= 400 ? JSON.stringify({ detail: 'account_gate_busy' }) : '')
  }
}

describe('bulkDeleteMemories', () => {
  it('issues DELETE /v3/memories/batch in chunks of 100 instead of 4-wide single deletes', async () => {
    const calls: { url: string; method: string; body?: string }[] = []
    const fetchImpl: BulkDeleteFetch = async (url, init) => {
      calls.push({ url, method: init.method, body: init.body })
      return jsonResponse(200)
    }
    const ids = Array.from({ length: 101 }, (_, i) => `m${i}`)
    const result = await bulkDeleteMemories(fetchImpl, 'https://api.example', {
      token: 'tok',
      ids
    })

    expect(MEMORIES_DELETE_BATCH_SIZE).toBe(100)
    expect(result).toEqual({ deleted: 101, failed: 0, firstError: undefined })
    expect(calls).toHaveLength(2)
    expect(calls.every((c) => c.method === 'DELETE' && c.url.endsWith('/v3/memories/batch'))).toBe(
      true
    )
    expect(JSON.parse(calls[0].body ?? '{}').memory_ids).toHaveLength(100)
    expect(JSON.parse(calls[1].body ?? '{}').memory_ids).toEqual(['m100'])
    expect(calls.some((c) => /\/v3\/memories\/m\d+$/.test(c.url))).toBe(false)
  })

  it('retries a 409 using the Retry-After header, then completes the batch', async () => {
    const sleep = vi.fn(async () => {})
    let attempts = 0
    const fetchImpl: BulkDeleteFetch = async () => {
      attempts++
      if (attempts === 1) return jsonResponse(409, { 'retry-after': '2' })
      return jsonResponse(200)
    }

    const result = await bulkDeleteMemories(
      fetchImpl,
      'https://api.example',
      { token: 'tok', ids: ['a', 'b'] },
      { sleep }
    )

    expect(result.deleted).toBe(2)
    expect(result.failed).toBe(0)
    expect(attempts).toBe(2)
    expect(sleep).toHaveBeenCalledWith(2000)
  })

  it('bisects a 404 batch instead of fanning out per-id single deletes', async () => {
    // All-or-nothing validation: one stale id 404s the whole chunk. The chunk
    // must be split and retried as batches so only the stale id reaches the
    // single-delete route (the 60/hour per-UID limiter).
    const batchCalls: string[][] = []
    const singleIds: string[] = []
    const fetchImpl: BulkDeleteFetch = async (url, init) => {
      if (url.endsWith('/v3/memories/batch')) {
        const chunk = JSON.parse((init as { body?: string }).body ?? '{}').memory_ids as string[]
        batchCalls.push(chunk)
        // The first chunk contains the stale id 'stale'; once it is bisected
        // away, every remaining batch succeeds.
        return chunk.includes('stale') ? jsonResponse(404) : jsonResponse(200)
      }
      singleIds.push(url.split('/').pop() ?? '')
      // The stale id is already gone server-side; its single delete 404s too,
      // which counts as idempotent success.
      return jsonResponse(404)
    }

    const result = await bulkDeleteMemories(fetchImpl, 'https://api.example', {
      token: 'tok',
      ids: ['a', 'b', 'stale', 'c', 'd']
    })

    expect(result.deleted).toBe(5)
    expect(result.failed).toBe(0)
    expect(singleIds).toEqual(['stale'])
    // First the whole chunk, then at least one bisect round before the stale
    // id is isolated.
    expect(batchCalls.length).toBeGreaterThanOrEqual(3)
    expect(batchCalls[0]).toHaveLength(5)
  })

  it('bisects down to lone ids without any per-id fallback when a whole chunk 404s', async () => {
    // Pathological case: every id stale. Bisection must still resolve via
    // batch calls until chunks are size 1, then single deletes (gone = ok).
    const batchCalls: string[][] = []
    const singleIds: string[] = []
    const fetchImpl: BulkDeleteFetch = async (url, init) => {
      if (url.endsWith('/v3/memories/batch')) {
        const chunk = JSON.parse((init as { body?: string }).body ?? '{}').memory_ids as string[]
        batchCalls.push(chunk)
        return jsonResponse(404)
      }
      singleIds.push(url.split('/').pop() ?? '')
      return jsonResponse(404)
    }

    const result = await bulkDeleteMemories(fetchImpl, 'https://api.example', {
      token: 'tok',
      ids: ['x', 'y']
    })

    expect(result.deleted).toBe(2)
    expect(result.failed).toBe(0)
    expect(singleIds.sort()).toEqual(['x', 'y'])
    // ['x','y'] -> 404 -> bisect into ['x'] and ['y'], each 404 -> singles.
    expect(batchCalls).toEqual([['x', 'y'], ['x'], ['y']])
  })
})
