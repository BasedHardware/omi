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
