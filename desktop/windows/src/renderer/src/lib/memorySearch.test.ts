import { describe, expect, it } from 'vitest'
import type { Memory } from '../hooks/useMemories'
import { filterMemories, memoryMatchesSearch } from './memorySearch'

const memory = (id: string, patch: Partial<Memory>): Memory => ({
  id,
  uid: 'u',
  content: '',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...patch
})

describe('memorySearch', () => {
  it('matches content, headline, category, and tags case-insensitively', () => {
    const m = memory('1', {
      headline: 'Prefers quiet dashboards',
      content: 'Uses Omi on Windows for daily planning',
      category: 'work',
      tags: ['desktop-parity']
    })

    expect(memoryMatchesSearch(m, 'omi windows')).toBe(true)
    expect(memoryMatchesSearch(m, 'QUIET')).toBe(true)
    expect(memoryMatchesSearch(m, 'desktop-parity')).toBe(true)
    expect(memoryMatchesSearch(m, 'work')).toBe(true)
  })

  it('requires every query term to match the same memory', () => {
    const memories = [
      memory('1', { content: 'Uses Omi on Windows' }),
      memory('2', { content: 'Uses Omi on macOS' })
    ]

    expect(filterMemories(memories, 'omi windows').map((m) => m.id)).toEqual(['1'])
  })

  it('returns the original list for blank queries', () => {
    const memories = [memory('1', { content: 'A' })]
    expect(filterMemories(memories, '   ')).toBe(memories)
  })
})
