import { describe, it, expect } from 'vitest'
import { chunkTts, nextChunkBoundary, FIRST_CHUNK, FOLLOW_CHUNK } from './ttsChunker'

describe('chunkTts — sizing', () => {
  it('returns a single chunk for text shorter than the first-chunk minimum', () => {
    expect(chunkTts('Hi there.')).toEqual(['Hi there.'])
    expect(chunkTts('   ')).toEqual([])
    expect(chunkTts('')).toEqual([])
  })

  it('keeps the FIRST chunk within the 40–200 window when there is no early sentence break', () => {
    // 500 space-separated word chars, no sentence punctuation → the first chunk
    // is cut at whitespace inside the 200-char emergency window.
    const text = 'word '.repeat(100).trim() // "word word word …" (499 chars)
    const chunks = chunkTts(text)
    expect(chunks.length).toBeGreaterThan(1)
    expect(chunks[0].length).toBeGreaterThanOrEqual(FIRST_CHUNK.min)
    expect(chunks[0].length).toBeLessThanOrEqual(FIRST_CHUNK.emergency)
  })

  it('cuts the first chunk at the last sentence break inside the preferred window', () => {
    const first = 'This is the first sentence and it is plenty long.'
    const text = first + ' ' + 'x'.repeat(400)
    const chunks = chunkTts(text)
    expect(chunks[0]).toBe(first)
  })

  it('sizes FOLLOW chunks in the 320–800 window for very long text', () => {
    const text = 'word '.repeat(600).trim() // ~3000 chars, no punctuation
    const chunks = chunkTts(text)
    expect(chunks.length).toBeGreaterThan(2)
    // Every chunk except the last is a full follow chunk (>= min, <= emergency).
    for (const chunk of chunks.slice(1, -1)) {
      expect(chunk.length).toBeGreaterThanOrEqual(FOLLOW_CHUNK.min)
      expect(chunk.length).toBeLessThanOrEqual(FOLLOW_CHUNK.emergency)
    }
    // The whole reply is preserved (modulo the dropped whitespace at cuts).
    expect(chunks.join(' ')).toBe(text)
  })
})

describe('nextChunkBoundary — priority (sentence > clause > whitespace > hard)', () => {
  it('prefers a sentence break over a later clause break in the same window', () => {
    // Sentence '.' at index 9; a comma later — the sentence wins.
    const text = 'Sentence. then a clause, and more filler text to exceed the minimum length here'
    const b = nextChunkBoundary(text, true)
    expect(b).toBe(text.indexOf('.') + 1)
  })

  it('falls back to a clause break when no sentence break exists in the window', () => {
    // No . ! ? \n anywhere; a comma at the emergency window → clause boundary.
    const first = 'a'.repeat(150) + ', ' + 'b'.repeat(400)
    const b = nextChunkBoundary(first, true)
    expect(b).toBe(first.indexOf(',') + 1)
  })

  it('falls back to whitespace when neither sentence nor clause punctuation exists', () => {
    const text = 'word '.repeat(100).trim()
    const b = nextChunkBoundary(text, true)!
    expect(b).toBeGreaterThan(0)
    // Cut is a whitespace index (the char at the cut is a space, dropped).
    expect(text[b]).toBe(' ')
    expect(b).toBeLessThanOrEqual(FIRST_CHUNK.emergency)
  })

  it('hard-cuts at the emergency length when a single unbroken token overflows', () => {
    const text = 'z'.repeat(900) // no punctuation, no whitespace, longer than either emergency
    expect(nextChunkBoundary(text, true)).toBe(FIRST_CHUNK.emergency)
    expect(nextChunkBoundary(text, false)).toBe(FOLLOW_CHUNK.emergency)
  })

  it('returns null (buffer more) below the minimum length', () => {
    expect(nextChunkBoundary('short', true)).toBeNull()
    expect(nextChunkBoundary('a'.repeat(100), false)).toBeNull()
  })
})
