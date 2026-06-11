import { describe, it, expect } from 'vitest'
import { appMemoryIdsToDelete, APP_MEMORY_TAG } from './appMemories'
import type { Memory } from '../hooks/useMemories'

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
