// Vector primitives for Rewind semantic search — pure, no I/O.
//
// Mirrors the macOS implementation: Gemini `gemini-embedding-001` returns 3072
// floats, which we L2-normalize BEFORE storage so a plain dot product IS the
// cosine similarity at query time (no per-query magnitude math). Vectors are
// persisted as a raw little-endian Float32 BLOB — 3072 * 4 = 12288 bytes — using
// the same codec as Track 3's task embeddings (`ipc/taskEmbeddingVector.ts`).
import { createHash } from 'node:crypto'

/** Dimension of a `gemini-embedding-001` vector. */
export const EMBED_DIM = 3072

/** Byte length of a stored vector BLOB (Float32 little-endian). */
export const EMBED_BLOB_BYTES = EMBED_DIM * 4

/** Model id sent to the proxy and recorded in `rewind_embeddings.model`. */
export const EMBED_MODEL = 'gemini-embedding-001'

/**
 * Scale `v` to unit length. A zero (or non-finite) vector has no direction, so
 * it is returned unchanged rather than producing NaNs — the caller treats an
 * all-zero vector as "no signal" and it can never win a similarity ranking.
 */
export function l2Normalize(v: Float32Array): Float32Array {
  let sumSq = 0
  for (let i = 0; i < v.length; i++) sumSq += v[i] * v[i]
  const norm = Math.sqrt(sumSq)
  if (!Number.isFinite(norm) || norm === 0) return v
  const out = new Float32Array(v.length)
  for (let i = 0; i < v.length; i++) out[i] = v[i] / norm
  return out
}

/** Dot product. For L2-normalized inputs this equals cosine similarity.
 *  Mismatched lengths score 0 — a vector from another model can't be compared. */
export function dot(a: Float32Array, b: Float32Array): number {
  if (a.length !== b.length) return 0
  let sum = 0
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i]
  return sum
}

/**
 * Content key for embedding dedup: the first 16 bytes of the SHA-256 of the
 * text, hex-encoded (32 chars). Matches macOS. 128 bits is far past the point
 * where a collision is plausible for a per-launch working set, and the short key
 * keeps the recent-hash cache small.
 */
export function contentHash(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 32)
}

/** One candidate in a similarity scan. */
export type ScoredFrame = { frameId: number; similarity: number }

/**
 * The `limit` most similar entries, strongest first.
 *
 * Takes an *iterable* and keeps only the running top-K rather than materializing
 * every candidate: a vector is 12KB, so loading a few thousand frames at once
 * would cost tens of MB on every search. The caller streams rows straight out of
 * SQLite into this.
 */
export function topKBySimilarity(
  entries: Iterable<{ frameId: number; vec: Float32Array }>,
  query: Float32Array,
  limit: number
): ScoredFrame[] {
  if (limit <= 0) return []
  const top: ScoredFrame[] = [] // kept sorted weakest-first, so top[0] is the one to beat
  for (const entry of entries) {
    const similarity = dot(query, entry.vec)
    if (top.length < limit) {
      top.push({ frameId: entry.frameId, similarity })
      top.sort((a, b) => a.similarity - b.similarity)
    } else if (similarity > top[0].similarity) {
      top[0] = { frameId: entry.frameId, similarity }
      top.sort((a, b) => a.similarity - b.similarity)
    }
  }
  return top.reverse()
}
