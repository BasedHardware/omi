import { describe, expect, it } from 'vitest'
import {
  contentHash,
  dot,
  formatForEmbedding,
  l2Normalize,
  scanTopKBySimilarity,
  EMBED_DIM,
  type VectorRow
} from './embedVector'
import { bufferToVector, vectorToBuffer } from '../ipc/taskEmbeddingVector'

// Port of macOS OCREmbeddingService.formatForEmbedding (OCREmbeddingService.swift:43-50).
// The app name and window title carry retrieval signal the OCR text often does not:
// "that mockup in Figma", "the Slack thread about billing".
describe('formatForEmbedding', () => {
  it('prepends the app and window title, exactly as macOS composes it', () => {
    expect(formatForEmbedding('the deck', 'Figma', 'Q3 mockups')).toBe(
      '[Figma] Q3 mockups\nthe deck'
    )
  })

  it('omits the title when there is none (macOS: "[app]\\n<ocr>")', () => {
    expect(formatForEmbedding('the deck', 'Figma', '')).toBe('[Figma]\nthe deck')
  })

  it('emits no empty brackets when the app name is unknown', () => {
    // macOS always has an app name and would emit a bare "[]"; the Windows
    // foreground reader can come up empty, and "[]" is pure noise in the vector.
    expect(formatForEmbedding('the deck', '', '')).toBe('the deck')
    expect(formatForEmbedding('the deck', '', 'Q3 mockups')).toBe('Q3 mockups\nthe deck')
  })

  it('makes the same screen text in two different apps DISTINCT content', () => {
    // This is the point of hashing the composed string (macOS does the same,
    // OCREmbeddingService.swift:68): two apps showing identical text are two
    // different things, and each earns its own vector...
    const inFigma = formatForEmbedding('shared text', 'Figma', 'design')
    const inSlack = formatForEmbedding('shared text', 'Slack', 'design')
    expect(contentHash(inFigma)).not.toBe(contentHash(inSlack))

    // ...while consecutive screenshots of the SAME window still collapse to one
    // vector, which is where the ~20x dedup saving actually comes from.
    expect(contentHash(inFigma)).toBe(
      contentHash(formatForEmbedding('shared text', 'Figma', 'design'))
    )
  })
})

describe('l2Normalize', () => {
  it('scales a vector to unit length', () => {
    const v = l2Normalize(Float32Array.from([3, 4]))
    expect(v[0]).toBeCloseTo(0.6, 6)
    expect(v[1]).toBeCloseTo(0.8, 6)
    expect(Math.hypot(...v)).toBeCloseTo(1, 6)
  })

  it('leaves an already-normalized vector alone', () => {
    const v = l2Normalize(Float32Array.from([0, 1, 0]))
    expect([...v]).toEqual([0, 1, 0])
  })

  // A zero vector has no direction — dividing by its norm would yield NaNs that
  // then poison every similarity comparison.
  it('returns a zero vector unchanged instead of producing NaN', () => {
    const v = l2Normalize(new Float32Array(4))
    expect([...v]).toEqual([0, 0, 0, 0])
  })
})

describe('dot', () => {
  // The whole reason vectors are normalized before storage: dot == cosine.
  it('equals cosine similarity for normalized vectors', () => {
    const a = l2Normalize(Float32Array.from([1, 1]))
    const b = l2Normalize(Float32Array.from([1, 0]))
    expect(dot(a, a)).toBeCloseTo(1, 6) // identical
    expect(dot(a, b)).toBeCloseTo(Math.SQRT1_2, 6) // 45 degrees
    expect(dot(b, l2Normalize(Float32Array.from([0, 1])))).toBeCloseTo(0, 6) // orthogonal
    expect(dot(b, l2Normalize(Float32Array.from([-1, 0])))).toBeCloseTo(-1, 6) // opposite
  })

  // A stored vector from a different model must not score as a near-match.
  it('scores 0 for mismatched dimensions rather than comparing a prefix', () => {
    expect(dot(Float32Array.from([1, 0, 0]), Float32Array.from([1, 0]))).toBe(0)
  })
})

describe('blob round-trip', () => {
  it('preserves a full-dimension vector through the SQLite BLOB codec', () => {
    const original = l2Normalize(Float32Array.from({ length: EMBED_DIM }, (_, i) => i % 7))
    const blob = vectorToBuffer(original)
    expect(blob.byteLength).toBe(EMBED_DIM * 4) // 12288 bytes
    const restored = bufferToVector(blob)
    expect(restored.length).toBe(EMBED_DIM)
    expect(dot(original, restored)).toBeCloseTo(1, 5)
  })
})

describe('scanTopKBySimilarity', () => {
  const row = (hash: string, vec: number[]): VectorRow => ({
    hash,
    vec: l2Normalize(Float32Array.from(vec))
  })
  const query = l2Normalize(Float32Array.from([1, 0]))

  /** Serve `rows` as pages, recording every yield between them. */
  const pager = (rows: VectorRow[], yields: string[]) => ({
    fetchChunk: (offset: number, limit: number) => rows.slice(offset, offset + limit),
    yieldToEventLoop: async () => {
      yields.push('yield')
    }
  })

  const scan = async (rows: VectorRow[], limit: number, chunk = 2, yields: string[] = []) => {
    const p = pager(rows, yields)
    return scanTopKBySimilarity(p.fetchChunk, query, limit, p.yieldToEventLoop, chunk)
  }

  it('returns the most similar entries, strongest first', async () => {
    const top = await scan([row('a', [0, 1]), row('b', [1, 0]), row('c', [1, 1])], 2)
    expect(top.map((t) => t.hash)).toEqual(['b', 'c']) // exact match, then 45 degrees
    expect(top[0].similarity).toBeCloseTo(1, 6)
    expect(top[1].similarity).toBeCloseTo(Math.SQRT1_2, 6)
  })

  it('keeps the best K when there are more candidates than slots', async () => {
    const rows = Array.from({ length: 50 }, (_, i) => row(`h${i}`, [i, 100 - i]))
    const top = await scan(rows, 3)
    expect(top.map((t) => t.hash)).toEqual(['h49', 'h48', 'h47']) // most x-aligned
  })

  // C2: better-sqlite3 is synchronous, so a single scan over every vector would
  // freeze the main process. The scan MUST page and yield between pages — this is
  // the assertion that the freeze is structurally impossible, not merely unlikely.
  it('reads in bounded pages and yields the event loop between them', async () => {
    const yields: string[] = []
    const rows = Array.from({ length: 10 }, (_, i) => row(`h${i}`, [i, 1]))
    const pages: number[] = []
    const top = await scanTopKBySimilarity(
      (offset, limit) => {
        pages.push(limit)
        return rows.slice(offset, offset + limit)
      },
      query,
      3,
      async () => {
        yields.push('yield')
      },
      2
    )
    expect(pages.every((p) => p === 2)).toBe(true) // never asks for the whole table
    expect(yields.length).toBeGreaterThanOrEqual(4) // yielded between pages
    expect(top).toHaveLength(3) // and still ranked everything correctly
    expect(top[0].hash).toBe('h9')
  })

  it('stops at a short page instead of scanning forever', async () => {
    const yields: string[] = []
    // 4 rows with a page size of 2: the second page is full, the third is empty
    // and ends the scan. A bug here would loop on an infinite tail of empty pages.
    const top = await scan(
      [row('a', [1, 0]), row('b', [0, 1]), row('c', [1, 1]), row('d', [2, 0])],
      4,
      2,
      yields
    )
    expect(top).toHaveLength(4)
  })

  it('handles fewer candidates than K, and an empty store', async () => {
    expect(await scan([row('a', [1, 0])], 10)).toHaveLength(1)
    expect(await scan([], 5)).toEqual([])
    expect(await scan([row('a', [1, 0])], 0)).toEqual([])
  })

  // A vector written by a different model must not be ranked against this query.
  it('scores a wrong-dimension vector 0 instead of matching on a prefix', async () => {
    const top = await scan([row('a', [1, 0, 0]), row('b', [1, 0])], 2)
    expect(top[0].hash).toBe('b')
    expect(top[1]).toEqual({ hash: 'a', similarity: 0 })
  })
})

describe('contentHash', () => {
  it('is a stable 32-char key (first 16 bytes of SHA-256)', () => {
    expect(contentHash('hello')).toHaveLength(32)
    expect(contentHash('hello')).toBe(contentHash('hello'))
  })

  it('differs for different content, including whitespace-only differences', () => {
    expect(contentHash('hello')).not.toBe(contentHash('hello '))
    expect(contentHash('a')).not.toBe(contentHash('b'))
  })
})
