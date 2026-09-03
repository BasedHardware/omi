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
    const result = await bulkDeleteMemories(fetchImpl, {
      baseURL: 'https://api.example',
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
      { baseURL: 'https://api.example', token: 'tok', ids: ['a', 'b'] },
      { sleep }
    )

    expect(result.deleted).toBe(2)
    expect(result.failed).toBe(0)
    expect(attempts).toBe(2)
    expect(sleep).toHaveBeenCalledWith(2000)
  })

  it('falls back to per-id deletes when the batch is 404 (all-or-nothing missing id)', async () => {
    const fetchImpl: BulkDeleteFetch = async (url) => {
      if (url.endsWith('/v3/memories/batch')) return jsonResponse(404)
      return jsonResponse(200)
    }
    const result = await bulkDeleteMemories(fetchImpl, {
      baseURL: 'https://api.example',
      token: 'tok',
      ids: ['a', 'b']
    })
    expect(result.deleted).toBe(2)
    expect(result.failed).toBe(0)
  })
})
