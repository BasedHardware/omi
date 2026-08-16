import { describe, expect, it } from 'vitest'
import { VECTOR_SIM_THRESHOLD, mergeRewindSearchResults, type VectorHit } from './vectorSearchMerge'
import type { RewindFrame } from '../../shared/types'

const frame = (id: number, ts = id * 1000): RewindFrame => ({
  id,
  ts,
  app: 'Code',
  windowTitle: 'window',
  processName: 'code.exe',
  ocrText: `frame ${id}`,
  imagePath: `C:\\frames\\${id}.jpg`,
  width: 1920,
  height: 1080,
  indexed: 1
})

const hit = (id: number, similarity: number, ts?: number): VectorHit => ({
  frame: frame(id, ts),
  similarity
})

const ids = (frames: RewindFrame[]): (number | undefined)[] => frames.map((f) => f.id)

describe('mergeRewindSearchResults', () => {
  it('keeps FTS results first, in their original BM25 order', () => {
    const fts = [frame(3), frame(1), frame(2)]
    const merged = mergeRewindSearchResults(fts, [hit(9, 0.99)])
    // The 0.99 semantic hit does NOT jump the queue — keyword always leads.
    expect(ids(merged)).toEqual([3, 1, 2, 9])
  })

  it('adds a vector hit only when it clears the similarity floor', () => {
    const merged = mergeRewindSearchResults(
      [],
      [hit(1, VECTOR_SIM_THRESHOLD + 0.01), hit(2, VECTOR_SIM_THRESHOLD), hit(3, 0.1)]
    )
    // Strictly greater than 0.5 — a hit exactly at the floor is dropped.
    expect(ids(merged)).toEqual([1])
  })

  it('never duplicates a frame FTS already returned, however strong the vector score', () => {
    const merged = mergeRewindSearchResults([frame(1), frame(2)], [hit(1, 0.99), hit(3, 0.8)])
    expect(ids(merged)).toEqual([1, 2, 3])
  })

  it('orders the additive hits strongest-first, breaking ties by recency', () => {
    const merged = mergeRewindSearchResults([], [hit(1, 0.7), hit(2, 0.9), hit(3, 0.7, 999_999)])
    expect(ids(merged)).toEqual([2, 3, 1])
  })

  // The non-fatal contract: a dead embedding backend hands the merge an empty
  // list, and keyword results must still render.
  it('returns FTS results unchanged when vector search yielded nothing', () => {
    const fts = [frame(1), frame(2)]
    expect(ids(mergeRewindSearchResults(fts, []))).toEqual([1, 2])
  })

  it('returns nothing when neither leg matched', () => {
    expect(mergeRewindSearchResults([], [])).toEqual([])
  })
})
