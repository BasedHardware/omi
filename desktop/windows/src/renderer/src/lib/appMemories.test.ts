import { describe, it, expect, vi, beforeEach } from 'vitest'
import { appMemoryIdsToDelete, APP_MEMORY_TAG, purgeAppMemories } from './appMemories'
import type { Memory } from '../hooks/useMemories'

const omiApiGet = vi.fn()
const omiApiDelete = vi.fn()

vi.mock('./apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => omiApiGet(...args),
    delete: (...args: unknown[]) => omiApiDelete(...args)
  }
}))

function mem(id: string, tags?: string[]): Memory {
  return { id, uid: 'u', content: 'Uses Whatever', tags, created_at: '', updated_at: '' } as Memory
}

describe('appMemoryIdsToDelete', () => {
  it('selects only memories carrying the app-index provenance tag', () => {
    const out = appMemoryIdsToDelete([
      mem('1', [APP_MEMORY_TAG]),
      mem('2', [APP_MEMORY_TAG, 'app-category:browser']),
      mem('3', ['user-note']),
      mem('4', undefined)
    ])
    expect(out.sort()).toEqual(['1', '2'])
  })

  it('returns empty when nothing is tagged (never touches user memories)', () => {
    expect(appMemoryIdsToDelete([mem('1'), mem('2', ['x'])])).toEqual([])
  })

  it('handles empty input', () => {
    expect(appMemoryIdsToDelete([])).toEqual([])
  })
})

// Regression for the pagination-cap Minor fix: purgeAppMemories used to page
// with its own 5000-offset cap and silently missed app-index memories beyond
// it. It now delegates to the shared fetchAllMemories pager (memoriesBulk.ts),
// which has no such cap.
describe('purgeAppMemories', () => {
  beforeEach(() => {
    omiApiGet.mockReset()
    omiApiDelete.mockReset().mockResolvedValue({})
  })

  it('finds and deletes an app-index memory beyond the old 5000-offset cap', async () => {
    const FULL_PAGES = 26 // 26 * 200 = 5200 — one page past the old cap
    let call = 0
    omiApiGet.mockImplementation(async () => {
      const start = call * 200
      call++
      if (call > FULL_PAGES) return { data: [] }
      // One tagged app-index memory lands on the very last page (offset 5000-5199).
      const isLastPage = call === FULL_PAGES
      const page = Array.from({ length: 200 }, (_, i) => ({
        id: `m${start + i}`,
        uid: 'u',
        content: 'x',
        tags: isLastPage && i === 0 ? [APP_MEMORY_TAG] : undefined,
        created_at: '',
        updated_at: ''
      }))
      return { data: page }
    })

    const deleted = await purgeAppMemories()

    expect(deleted).toBe(1)
    expect(omiApiDelete).toHaveBeenCalledWith('/v3/memories/m5000')
  })
})
