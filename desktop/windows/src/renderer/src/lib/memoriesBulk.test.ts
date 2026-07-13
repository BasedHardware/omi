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

// Minor fix (memory pagination dupes): appMemories.ts and AdvancedTab.tsx each
// used to duplicate this pager with their own, smaller caps (5000, in
// appMemories.ts's purgeAppMemories) — silently missing memories past offset
// 5000. Both now call this single implementation instead.
describe('fetchAllMemories', () => {
  it('pages past the old 5000-offset cap that appMemories.ts used to stop at', async () => {
    const FULL_PAGES = 26 // 26 * 200 = 5200 memories — one page beyond the old cap
    let call = 0
    omiApiGet.mockImplementation(async () => {
      const start = call * 200
      call++
      if (call > FULL_PAGES) return { data: [] }
      return page(Array.from({ length: 200 }, (_, i) => `m${start + i}`))
    })

    const all = await fetchAllMemories()

    expect(all).toHaveLength(5200)
    expect(all.some((m) => m.id === 'm5199')).toBe(true)
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
