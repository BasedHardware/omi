import { describe, it, expect, vi } from 'vitest'
import { createMemoryBody, type Memory } from './useMemories'
import { memorySource } from '../lib/memoryProvenance'

vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

// What the server stores for a given POST /v3/memories body — mirrored from
// backend/routers/memories.py create_memory + models/memories.py
// MemoryDB.from_memory: `category` defaults to 'interesting' (Memory model),
// `manually_added` is DERIVED from category === 'manual', and the evidence
// record gets source_signal 'manual' when manually_added else 'transcription'
// (source_type 'developer_api' since there is no conversation). If the backend
// contract changes, update this mirror alongside it.
function storedByBackend(body: { content: string; category?: string; tags?: string[] }): Memory {
  const category = body.category ?? 'interesting'
  const manually_added = category === 'manual'
  return {
    id: 'm-created',
    uid: 'u',
    content: body.content,
    category,
    manually_added,
    tags: body.tags,
    created_at: '2026-07-01T10:00:00Z',
    updated_at: '2026-07-01T10:00:00Z',
    evidence: [
      {
        evidence_id: 'e1',
        source_id: 'external:m-created',
        source_type: 'developer_api',
        source_signal: manually_added ? 'manual' : 'transcription',
        extractor_id: 'memory_extractor',
        extractor_version: 'v1',
        redaction_status: 'active',
        created_at: '2026-07-01T10:00:00Z'
      }
    ]
  }
}

describe('createMemoryBody (page create flow)', () => {
  it('stamps category manual so a memory typed on the Memories page classifies as Manual', () => {
    // Without the stamp the backend derives manually_added=false and emits
    // source_signal 'transcription' — and our own provenance UI would then
    // label the user's typed memory "Heard in a conversation".
    const body = createMemoryBody('I prefer window seats')
    expect(body.category).toBe('manual')
    expect(memorySource(storedByBackend(body))).toBe('manual')
  })

  it('lets an importer override the category and keep its provenance tags', () => {
    const body = createMemoryBody('note text', {
      category: 'interesting',
      tags: ['gmail/import/note']
    })
    expect(body.category).toBe('interesting')
    expect(body.tags).toEqual(['gmail/import/note'])
    expect(memorySource(storedByBackend(body))).toBe('gmail')
  })
})
