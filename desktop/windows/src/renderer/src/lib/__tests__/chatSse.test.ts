import { describe, it, expect } from 'vitest'
import { parseDonePayload, parseSseLine } from '../chatSse'

// Encode a JS object as a base64 done: payload the same way the Omi backend does.
// Uses Buffer (Node / vitest environment) for encoding.
function encodeDone(payload: unknown): string {
  return `done:${Buffer.from(JSON.stringify(payload)).toString('base64')}`
}

// ---------------------------------------------------------------------------
// parseDonePayload
// ---------------------------------------------------------------------------

describe('parseDonePayload', () => {
  it('returns [] for an empty string', () => {
    expect(parseDonePayload('')).toEqual([])
  })

  it('returns [] for a bare "done:" with no payload', () => {
    expect(parseDonePayload('done:')).toEqual([])
  })

  it('returns [] for malformed base64', () => {
    expect(parseDonePayload('done:!!!not-valid-base64!!!')).toEqual([])
  })

  it('returns [] for valid base64 that is not JSON', () => {
    const b64 = Buffer.from('hello world').toString('base64')
    expect(parseDonePayload(`done:${b64}`)).toEqual([])
  })

  it('returns [] when the payload has no memories/citations/sources key', () => {
    expect(parseDonePayload(encodeDone({ text: 'some response' }))).toEqual([])
  })

  it('parses the memories key', () => {
    const line = encodeDone({
      memories: [{ id: 'abc', title: 'Meeting notes', emoji: '📝' }]
    })
    const result = parseDonePayload(line)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('abc')
    expect(result[0].title).toBe('Meeting notes')
    expect(result[0].emoji).toBe('📝')
  })

  it('falls back to the citations key when memories is absent', () => {
    const line = encodeDone({
      citations: [{ id: 'xyz', title: 'Project plan' }]
    })
    expect(parseDonePayload(line)[0].id).toBe('xyz')
  })

  it('falls back to the sources key when memories and citations are absent', () => {
    const line = encodeDone({
      sources: [{ id: 'src1', title: 'Source doc' }]
    })
    expect(parseDonePayload(line)[0].id).toBe('src1')
  })

  it('accepts raw base64 without the done: prefix', () => {
    const b64 = Buffer.from(JSON.stringify({ memories: [{ id: 'raw', title: 'Raw' }] })).toString('base64')
    expect(parseDonePayload(b64)[0].id).toBe('raw')
  })

  it('falls back to memory_id as id', () => {
    const line = encodeDone({ memories: [{ memory_id: 'mid-1', title: 'Fallback' }] })
    expect(parseDonePayload(line)[0].id).toBe('mid-1')
  })

  it('falls back to conversation_id as id', () => {
    const line = encodeDone({ memories: [{ conversation_id: 'cid-1', title: 'Conv' }] })
    expect(parseDonePayload(line)[0].id).toBe('cid-1')
  })

  it('filters out entries with no resolvable id', () => {
    const line = encodeDone({ memories: [{ title: 'No id here' }] })
    expect(parseDonePayload(line)).toHaveLength(0)
  })

  it('reads title from structured.title when top-level title is missing', () => {
    const line = encodeDone({
      memories: [{ id: 'st1', structured: { title: 'Structured title' } }]
    })
    expect(parseDonePayload(line)[0].title).toBe('Structured title')
  })

  it('falls back to "Conversation source" when title is entirely absent', () => {
    const line = encodeDone({ memories: [{ id: 'nt1' }] })
    expect(parseDonePayload(line)[0].title).toBe('Conversation source')
  })

  it('reads emoji from structured.emoji when top-level emoji is missing', () => {
    const line = encodeDone({
      memories: [{ id: 'e1', title: 'T', structured: { emoji: '🚀' } }]
    })
    expect(parseDonePayload(line)[0].emoji).toBe('🚀')
  })

  it('preserves emoji in title correctly through UTF-8 roundtrip', () => {
    // This is the regression: atob() treats bytes as Latin-1, garbling multi-byte
    // emoji. parseDonePayload uses TextDecoder for correct UTF-8 decoding.
    const line = encodeDone({
      memories: [{ id: 'emoji-id', title: 'Coffee ☕ and code 💻' }]
    })
    expect(parseDonePayload(line)[0].title).toBe('Coffee ☕ and code 💻')
  })

  it('preserves emoji in the citation id field', () => {
    const line = encodeDone({
      memories: [{ id: 'id-😄', title: 'Happy' }]
    })
    expect(parseDonePayload(line)[0].id).toBe('id-😄')
  })

  it('reads preview from structured.overview', () => {
    const line = encodeDone({
      memories: [{ id: 'p1', title: 'T', structured: { overview: 'An overview of the meeting' } }]
    })
    expect(parseDonePayload(line)[0].preview).toBe('An overview of the meeting')
  })

  it('reads preview from top-level text as fallback', () => {
    const line = encodeDone({ memories: [{ id: 'p2', title: 'T', text: 'Some text' }] })
    expect(parseDonePayload(line)[0].preview).toBe('Some text')
  })

  it('truncates preview to 120 characters', () => {
    const longText = 'a'.repeat(200)
    const line = encodeDone({ memories: [{ id: 'p3', title: 'T', text: longText }] })
    expect(parseDonePayload(line)[0].preview).toHaveLength(120)
  })

  it('omits preview when source text is empty or whitespace', () => {
    const line = encodeDone({ memories: [{ id: 'p4', title: 'T', text: '   ' }] })
    expect(parseDonePayload(line)[0].preview).toBeUndefined()
  })

  it('passes through created_at', () => {
    const line = encodeDone({
      memories: [{ id: 'ts1', title: 'T', created_at: '2025-01-01T00:00:00Z' }]
    })
    expect(parseDonePayload(line)[0].created_at).toBe('2025-01-01T00:00:00Z')
  })

  it('handles multiple citations and preserves order', () => {
    const line = encodeDone({
      memories: [
        { id: 'a', title: 'Alpha' },
        { id: 'b', title: 'Beta' },
        { id: 'c', title: 'Gamma' }
      ]
    })
    const result = parseDonePayload(line)
    expect(result.map((c) => c.id)).toEqual(['a', 'b', 'c'])
  })

  it('ignores null/primitive entries in the list without throwing', () => {
    const line = encodeDone({ memories: [null, 42, { id: 'valid', title: 'OK' }, undefined] })
    const result = parseDonePayload(line)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('valid')
  })
})

// ---------------------------------------------------------------------------
// parseSseLine
// ---------------------------------------------------------------------------

describe('parseSseLine', () => {
  it('returns null for an empty string', () => {
    expect(parseSseLine('')).toBeNull()
  })

  it('returns null for a think: line', () => {
    expect(parseSseLine('think:Working on it...')).toBeNull()
  })

  it('returns null for a done: line', () => {
    expect(parseSseLine('done:abc123==')).toBeNull()
  })

  it('strips the "data: " prefix (with space)', () => {
    expect(parseSseLine('data: hello world')).toBe('hello world')
  })

  it('strips the "data:" prefix (no space)', () => {
    expect(parseSseLine('data:hello')).toBe('hello')
  })

  it('only strips one leading space after data:', () => {
    // SSE spec: strip exactly one space after the colon
    expect(parseSseLine('data:  two spaces')).toBe(' two spaces')
  })

  it('returns a bare line (no prefix) as-is', () => {
    expect(parseSseLine('bare chunk')).toBe('bare chunk')
  })

  it('replaces __CRLF__ tokens with newlines', () => {
    expect(parseSseLine('data: line1__CRLF__line2')).toBe('line1\nline2')
  })

  it('replaces multiple __CRLF__ tokens', () => {
    expect(parseSseLine('a__CRLF__b__CRLF__c')).toBe('a\nb\nc')
  })

  it('returns null for data: with no content after stripping', () => {
    expect(parseSseLine('data: ')).toBeNull()
    expect(parseSseLine('data:')).toBeNull()
  })

  it('returns null when data: content itself starts with think:', () => {
    // Handles the edge case where the chunk content begins with "think:"
    expect(parseSseLine('data:think:internal status')).toBeNull()
  })
})
