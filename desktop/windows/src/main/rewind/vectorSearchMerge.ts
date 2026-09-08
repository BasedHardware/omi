// Merge rule for Rewind hybrid search — pure, no I/O.
//
// The macOS contract, ported exactly: keyword (FTS5/BM25) and vector search run
// in parallel, but they are NOT peers.
//
//   * FTS leads. Its results keep their BM25 order and are never reordered,
//     dropped, or demoted by a vector score. A user who types an exact string
//     gets the exact-string hits first, always.
//   * Vector is additive recall ONLY. A semantic hit is appended if — and only
//     if — it clears the similarity floor AND names a frame FTS did not already
//     return. It can never displace a keyword hit.
//   * Vector failure is non-fatal. macOS wraps the whole vector leg in `try?`;
//     the caller here does the same, passing an empty list, so a dead embedding
//     backend silently degrades to keyword-only results instead of an error.
import type { RewindFrame } from '../../shared/types'

/** Minimum cosine similarity for a semantic hit to be worth showing (macOS: 0.5). */
export const VECTOR_SIM_THRESHOLD = 0.5

/** One vector-search hit: the frame, and its cosine similarity to the query. */
export type VectorHit = { frame: RewindFrame; similarity: number }

/**
 * FTS results, followed by the vector hits that add recall. Vector hits are
 * appended strongest-first; ties keep the newer frame first, matching the
 * recency bias everywhere else in Rewind.
 */
export function mergeRewindSearchResults(fts: RewindFrame[], vector: VectorHit[]): RewindFrame[] {
  const seen = new Set<number>()
  for (const frame of fts) {
    if (frame.id != null) seen.add(frame.id)
  }

  const additive = vector
    .filter((hit) => hit.similarity > VECTOR_SIM_THRESHOLD)
    // An id-less frame can't be checked against the FTS set, so it can't be
    // proven to be new — keep it out rather than risk a duplicate row in the UI.
    .filter((hit) => hit.frame.id != null && !seen.has(hit.frame.id))
    .sort((a, b) => b.similarity - a.similarity || b.frame.ts - a.frame.ts)
    .map((hit) => hit.frame)

  return [...fts, ...additive]
}
