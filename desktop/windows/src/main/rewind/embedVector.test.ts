import { describe, expect, it } from 'vitest'
import { contentHash, dot, l2Normalize, topKBySimilarity, EMBED_DIM } from './embedVector'
import { bufferToVector, vectorToBuffer } from '../ipc/taskEmbeddingVector'

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

describe('topKBySimilarity', () => {
  const entry = (frameId: number, vec: number[]): { frameId: number; vec: Float32Array } => ({
    frameId,
    vec: l2Normalize(Float32Array.from(vec))
  })
  const query = l2Normalize(Float32Array.from([1, 0]))

  it('returns the most similar entries, strongest first', () => {
    const top = topKBySimilarity([entry(1, [0, 1]), entry(2, [1, 0]), entry(3, [1, 1])], query, 2)
    expect(top.map((t) => t.frameId)).toEqual([2, 3]) // exact match, then 45 degrees
    expect(top[0].similarity).toBeCloseTo(1, 6)
    expect(top[1].similarity).toBeCloseTo(Math.SQRT1_2, 6)
  })

  it('keeps the best K when there are more candidates than slots', () => {
    const entries = Array.from({ length: 50 }, (_, i) => entry(i, [i, 100 - i]))
    const top = topKBySimilarity(entries, query, 3)
    expect(top.map((t) => t.frameId)).toEqual([49, 48, 47]) // most x-aligned
  })

  it('handles fewer candidates than K, and an empty scan', () => {
    expect(topKBySimilarity([entry(1, [1, 0])], query, 10)).toHaveLength(1)
    expect(topKBySimilarity([], query, 5)).toEqual([])
    expect(topKBySimilarity([entry(1, [1, 0])], query, 0)).toEqual([])
  })

  // A vector written by a different model must not be ranked against this query.
  it('scores a wrong-dimension vector 0 instead of matching on a prefix', () => {
    const top = topKBySimilarity([entry(1, [1, 0, 0]), entry(2, [1, 0])], query, 2)
    expect(top[0].frameId).toBe(2)
    expect(top[1]).toEqual({ frameId: 1, similarity: 0 })
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
