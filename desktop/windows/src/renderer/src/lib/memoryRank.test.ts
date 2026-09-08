import { describe, it, expect } from 'vitest'
import { rankMemories } from './memoryRank'
import type { Memory } from '../hooks/useMemories'

const m = (id: string, content: string, created_at = '2026-01-01T00:00:00Z'): Memory => ({
  id,
  uid: 'u',
  content,
  created_at,
  updated_at: created_at
})

describe('rankMemories', () => {
  it('ranks by overlap with query tokens and drops zero-overlap memories', () => {
    const mems = [
      m('1', 'I am building the official Omi Windows desktop port'),
      m('2', 'I enjoy cooking pasta on the weekends'),
      m('3', 'The Omi knowledge graph uses local files')
    ]
    const out = rankMemories(mems, 'omi-windows knowledge graph', 5)
    expect(out.some((c) => c.includes('Omi Windows'))).toBe(true)
    expect(out).not.toContain('I enjoy cooking pasta on the weekends')
  })

  it('tokenizes folder-style slugs (hyphens/underscores)', () => {
    const mems = [m('1', 'Working on the sandbox chat kg feature')]
    expect(rankMemories(mems, 'sandbox-chat-kg', 5)).toHaveLength(1)
  })

  it('returns at most `limit` results', () => {
    const mems = [
      m('1', 'omi alpha'),
      m('2', 'omi beta'),
      m('3', 'omi gamma'),
      m('4', 'omi delta')
    ]
    expect(rankMemories(mems, 'omi', 2)).toHaveLength(2)
  })

  it('breaks ties toward the more recent memory', () => {
    const mems = [
      m('old', 'omi sonda', '2025-01-01T00:00:00Z'),
      m('new', 'omi sonda', '2026-06-01T00:00:00Z')
    ]
    expect(rankMemories(mems, 'omi sonda', 1)).toEqual(['omi sonda'])
    // Both equal content; assert ordering via distinct content
    const mems2 = [
      m('old', 'omi project OLD', '2025-01-01T00:00:00Z'),
      m('new', 'omi project NEW', '2026-06-01T00:00:00Z')
    ]
    expect(rankMemories(mems2, 'omi', 1)).toEqual(['omi project NEW'])
  })

  it('returns [] for an empty or all-filler query', () => {
    const mems = [m('1', 'Omi Windows port')]
    expect(rankMemories(mems, '', 5)).toEqual([])
    expect(rankMemories(mems, 'what are the projects you have', 5)).toEqual([])
  })
})
