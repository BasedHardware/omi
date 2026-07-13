import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Memory } from '../hooks/useMemories'

const omiApiGet = vi.fn()
vi.mock('./apiClient', () => ({ omiApi: { get: (...args: unknown[]) => omiApiGet(...args) } }))

import { fetchAllMemories } from './memoriesBulk'

function page(ids: string[]): { data: Partial<Memory>[] } {
  return { data: ids.map((id) => ({ id, uid: 'u', content: id, created_at: '', updated_at: '' })) }
}

beforeEach(() => {
  omiApiGet.mockReset()
})

// Fakes the REAL GET /v3/memories contract (backend/routers/memories.py, both
// the legacy and canonical read paths): `limit` is clamped to at most 5000,
// AND offset === 0 FORCES limit to 5000 regardless of the requested limit.
// Only at a non-zero offset does the server honor the caller's requested limit.
function fakeBackend(
  total: number
): (
  path: string,
  config: { params: { limit: number; offset: number } }
) => Promise<{ data: Partial<Memory>[] }> {
  return async (_path, config) => {
    const { limit, offset } = config.params
    const effectiveLimit = offset === 0 ? Math.min(total, 5000) : limit
    const end = Math.min(offset + effectiveLimit, total)
    if (offset >= total) return page([])
    return page(Array.from({ length: end - offset }, (_, i) => `m${offset + i}`))
  }
}

// Minor fix (memory pagination dupes): appMemories.ts and AdvancedTab.tsx each
// used to duplicate this pager with their own, smaller caps (5000, in
// appMemories.ts's purgeAppMemories) — silently missing memories past offset
// 5000. Both now call this single implementation instead.
describe('fetchAllMemories', () => {
  it('fetches all 5200 memories despite the server forcing limit=5000 on the first (offset=0) page', async () => {
    // Regression: the OLD implementation advanced offset by a fixed +200 per
    // call. Since offset=0 really returns 5000 items (not the requested 200),
    // the second call still asked for offset=200 — entirely inside the
    // already-collected first page — added nothing new, and silently stopped
    // at 5000, missing the last 200 memories. The pager must advance by the
    // number of items it actually received.
    omiApiGet.mockImplementation(fakeBackend(5200))

    const all = await fetchAllMemories()

    expect(all).toHaveLength(5200)
    expect(all.some((m) => m.id === 'm5199')).toBe(true)
    // First call gets the forced 5000-item page; the follow-up call correctly
    // resumes at offset=5000 (not offset=200).
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', { params: { limit: 200, offset: 0 } })
    expect(omiApiGet).toHaveBeenCalledWith('/v3/memories', { params: { limit: 200, offset: 5000 } })
  })

  it('dedupes by id and stops once a full page adds nothing new (server ignoring offset)', async () => {
    // A full 200-item page keeps the loop going; a repeat of the same 200 ids
    // (added === 0) is the "server ignored offset" guard that ends it.
    const ids = Array.from({ length: 200 }, (_, i) => `id${i}`)
    omiApiGet.mockResolvedValueOnce(page(ids)).mockResolvedValueOnce(page(ids))

    const all = await fetchAllMemories()

    expect(all).toHaveLength(200)
    expect(omiApiGet).toHaveBeenCalledTimes(2)
  })
})
