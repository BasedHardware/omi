// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock only the network boundary (apiClient); the real extractMemories / heuristic
// dedup / batched-import logic runs, so this exercises the shipped orchestration
// rather than a re-declared copy of it.
const { desktopPost, omiPost } = vi.hoisted(() => ({ desktopPost: vi.fn(), omiPost: vi.fn() }))
vi.mock('./apiClient', () => ({
  desktopApi: { post: desktopPost },
  omiApi: { post: omiPost }
}))

import {
  extractPasteMemories,
  importPasteMemories,
  MAX_HEURISTIC_IMPORT_ITEMS
} from './pasteImport'

function aiReply(obj: unknown): { data: unknown } {
  return { data: { choices: [{ message: { content: JSON.stringify(obj) } }] } }
}

beforeEach(() => {
  desktopPost.mockReset()
  omiPost.mockReset()
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    memoryImportParse: vi.fn()
  }
})

describe('extractPasteMemories — AI path', () => {
  it('returns the synthesized memories + profile with via=ai', async () => {
    desktopPost.mockResolvedValue(
      aiReply({ memories: ['Likes tea', 'Lives in NY'], profile: 'A summary.' })
    )
    const r = await extractPasteMemories('log', 'chatgpt', [])
    expect(r.via).toBe('ai')
    expect(r.memories).toEqual(['Likes tea', 'Lives in NY'])
    expect(r.profile).toBe('A summary.')
    // The heuristic parser must NOT have been consulted on the AI happy path.
    expect(
      (window as unknown as { omi: { memoryImportParse: ReturnType<typeof vi.fn> } }).omi
        .memoryImportParse
    ).not.toHaveBeenCalled()
  })

  it('drops memories already present (exact-match dedup)', async () => {
    desktopPost.mockResolvedValue(aiReply({ memories: ['Likes tea', 'Likes Tea!'], profile: '' }))
    const r = await extractPasteMemories('log', 'claude', ['likes tea'])
    expect(r.memories).toEqual([]) // both normalize to an existing memory
  })
})

describe('extractPasteMemories — heuristic fallback', () => {
  it('falls back to the line split when the AI call throws, deduping existing', async () => {
    desktopPost.mockRejectedValue(new Error('gateway down'))
    ;(
      window as unknown as { omi: { memoryImportParse: ReturnType<typeof vi.fn> } }
    ).omi.memoryImportParse.mockResolvedValue(['Fact one', 'Fact two', 'Fact one'])
    const r = await extractPasteMemories('a\nb', 'chatgpt', ['fact two'])
    if (r.via !== 'heuristic') throw new Error('expected heuristic fallback')
    expect(r.fallbackReason).toBe('gateway down')
    // 'Fact two' is filtered (existing); the parser's raw list is passed through as-is
    // otherwise (no within-list dedup — that's the parser's job).
    expect(r.memories).toEqual(['Fact one', 'Fact one'])
    expect(r.truncated).toBe(false)
  })

  it('caps the heuristic list at MAX_HEURISTIC_IMPORT_ITEMS and reports the pre-cap total', async () => {
    desktopPost.mockRejectedValue(new Error('boom'))
    const many = Array.from({ length: MAX_HEURISTIC_IMPORT_ITEMS + 25 }, (_, i) => `fact ${i}`)
    ;(
      window as unknown as { omi: { memoryImportParse: ReturnType<typeof vi.fn> } }
    ).omi.memoryImportParse.mockResolvedValue(many)
    const r = await extractPasteMemories('x', 'chatgpt', [])
    if (r.via !== 'heuristic') throw new Error('expected heuristic fallback')
    expect(r.truncated).toBe(true)
    expect(r.memories).toHaveLength(MAX_HEURISTIC_IMPORT_ITEMS)
    expect(r.totalBeforeCap).toBe(MAX_HEURISTIC_IMPORT_ITEMS + 25)
  })
})

describe('importPasteMemories', () => {
  it('batches to /v3/memories/batch and tallies created_count', async () => {
    omiPost.mockResolvedValue({ data: { created_count: 3 } })
    const r = await importPasteMemories(['a', 'b', 'c'])
    expect(omiPost).toHaveBeenCalledWith('/v3/memories/batch', {
      memories: [{ content: 'a' }, { content: 'b' }, { content: 'c' }]
    })
    expect(r).toEqual({ ok: 3, failed: 0, firstError: undefined })
  })
})
