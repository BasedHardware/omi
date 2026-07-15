// M-2 regression, pinned END TO END — merge THEN grouping, composed exactly as
// the `rewind:search` handler composes them.
//
// This file exists because the unit tests lied. `vectorSearchMerge.test.ts`
// exercises the pure merge and passes; the merge really does put FTS first and
// append vector hits. But the handler then piped that list through `groupFrames`,
// which re-sorted everything by timestamp — so the contract the merge tests
// asserted was false in the shipped product. A test that stops at the seam is not
// a test of the behavior.
import { describe, expect, it } from 'vitest'
import { groupFrames } from './rewindGrouping'
import { mergeRewindSearchResults, type VectorHit } from './vectorSearchMerge'
import type { RewindFrame } from '../../shared/types'

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 1,
    ts: 0,
    app: 'Code.exe',
    windowTitle: 'a.ts',
    processName: 'Code',
    ocrText: '',
    imagePath: '/x.jpg',
    width: 0,
    height: 0,
    indexed: 1,
    ...over
  }
}

/** Exactly what `rewind:search` does with the two legs' results. */
function search(fts: RewindFrame[], vector: VectorHit[], query: string): number[] {
  return groupFrames(mergeRewindSearchResults(fts, vector), query).map(
    (g) => g.representative.id as number
  )
}

const QUERY = 'invoice'

// Last Tuesday, contains the literal word — BM25 rank 1.
const KEYWORD_HIT = frame({
  id: 1,
  ts: 1_000_000,
  app: 'Mail',
  windowTitle: 'inbox',
  ocrText: 'the invoice for March is attached'
})
// This morning, no keyword overlap at all — reachable ONLY semantically, and only
// just over the 0.5 floor.
const SEMANTIC_HIT = frame({
  id: 2,
  ts: 9_000_000,
  app: 'Chrome',
  windowTitle: 'billing',
  ocrText: 'billing and payment overview'
})

describe('rewind hybrid search ordering (merge -> grouping)', () => {
  it('shows an exact keyword match ABOVE a newer, weaker semantic hit', () => {
    const ids = search([KEYWORD_HIT], [{ frame: SEMANTIC_HIT, similarity: 0.51 }], QUERY)

    // The bug: grouping sorted by ts, so [2, 1] — the fuzzy match from today sat
    // on top of the exact match the user literally typed.
    expect(ids).toEqual([1, 2])
  })

  it('never lets a vector hit displace a keyword hit, however strong it is', () => {
    const ids = search([KEYWORD_HIT], [{ frame: SEMANTIC_HIT, similarity: 0.99 }], QUERY)
    expect(ids[0]).toBe(1) // similarity does not outrank BM25. Ever.
  })

  it('drops vector hits below the similarity floor', () => {
    const ids = search([KEYWORD_HIT], [{ frame: SEMANTIC_HIT, similarity: 0.5 }], QUERY)
    expect(ids).toEqual([1])
  })

  it('preserves BM25 order among keyword hits, even when it is not chronological', () => {
    const older = frame({ id: 10, ts: 1_000, app: 'A', ocrText: 'invoice invoice invoice' })
    const newer = frame({ id: 11, ts: 8_000_000, app: 'B', ocrText: 'an invoice, once' })
    // FTS handed them back best-first; the newer one is the WEAKER match.
    expect(search([older, newer], [], QUERY)).toEqual([10, 11])
  })

  it('degrades to keyword-only when the vector leg returns nothing', () => {
    expect(search([KEYWORD_HIT], [], QUERY)).toEqual([1])
  })

  it('returns semantic hits alone when FTS finds nothing', () => {
    const ids = search([], [{ frame: SEMANTIC_HIT, similarity: 0.8 }], QUERY)
    expect(ids).toEqual([2])
  })
})
