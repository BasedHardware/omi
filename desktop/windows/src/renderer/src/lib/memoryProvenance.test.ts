import { describe, expect, it } from 'vitest'
import type { Memory } from '../hooks/useMemories'
import { APP_INDEX_TAG } from './memoryCleanup'
import { memorySource, memorySourceLabel } from './memoryProvenance'
import { SCREEN_TAG } from './screenTag'

function memory(overrides: Partial<Memory> = {}): Memory {
  return {
    id: 'memory-1',
    uid: 'user-1',
    content: 'A memory',
    created_at: '2026-07-31T00:00:00Z',
    updated_at: '2026-07-31T00:00:00Z',
    ...overrides
  }
}

describe('memorySource', () => {
  it('uses explicit provenance tags before weaker record fields', () => {
    expect(memorySource(memory({ tags: [SCREEN_TAG], conversation_id: 'conversation-1' }))).toBe(
      'screen'
    )
    expect(memorySource(memory({ tags: [APP_INDEX_TAG] }))).toBe('file-index')
    expect(memorySource(memory({ tags: ['gmail/import/note'] }))).toBe('gmail')
    expect(memorySource(memory({ tags: ['sticky_notes/import/profile'] }))).toBe('sticky-notes')
  })

  it('uses explicit record fields and recorded evidence without guessing', () => {
    expect(memorySource(memory({ manually_added: true }))).toBe('manual')
    expect(memorySource(memory({ category: 'manual' }))).toBe('manual')
    expect(memorySource(memory({ conversation_id: 'conversation-1' }))).toBe('conversation')
    expect(memorySource(memory({ app_id: 'app-1' }))).toBe('app')
    expect(memorySource(memory({ evidence: [{ source_type: 'manual' }] }))).toBe('manual')
    expect(memorySource(memory({ evidence: [{ source_type: 'voice_transcript' }] }))).toBe(
      'conversation'
    )
    expect(memorySource(memory({ evidence: [{ source_type: 'screenshot_ocr' }] }))).toBe('screen')
    expect(memorySource(memory({ evidence: [{ source_type: 'api' }] }))).toBe('app')
    expect(memorySource(memory({ evidence: [{ source_type: 'developer_api' }] }))).toBe('app')
    expect(memorySource(memory({ evidence: [{ source_type: 'mcp' }] }))).toBe('app')
    expect(memorySource(memory({ evidence: [{ source_type: 'integration:gmail' }] }))).toBe('app')
    expect(memorySource(memory({ evidence: [{ source_type: 'unknown' }] }))).toBe('unknown')
    expect(memorySource(memory())).toBe('unknown')
  })

  it('uses recorded API evidence before legacy source flags', () => {
    expect(
      memorySource(memory({ manually_added: true, evidence: [{ source_type: 'developer_api' }] }))
    ).toBe('app')
  })

  it('returns an honest fallback label when no origin was recorded', () => {
    expect(memorySourceLabel(memory())).toBe('Origin not recorded')
  })
})
