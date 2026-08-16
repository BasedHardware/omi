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
 * What actually gets embedded (and hashed) for a frame: the OCR text with its app
 * context prepended. Port of macOS `OCREmbeddingService.formatForEmbedding`
 * (OCREmbeddingService.swift:43-50) — `"[<app>] <windowTitle>\n<ocrText>"`, with
 * the title omitted when empty.
 *
 * The app name and window title are strong retrieval signal, and embedding raw OCR
 * alone throws it away: "that thing I had open in Figma", "the Slack thread about
 * billing" are exactly the queries semantic search exists to serve, and none of
 * that vocabulary is necessarily anywhere in the screen text.
 *
 * Deviation from macOS, deliberately: macOS emits a bare `"[]"` when the app name
 * is missing (it always has one; on Windows the foreground reader can come up
 * empty). An empty bracket is noise in the embedded text, so the context prefix is
 * dropped instead.
 *
 * NOTE this is what the content hash is taken over (macOS hashes the formatted
 * string too — OCREmbeddingService.swift:68). Two frames with identical OCR in
 * DIFFERENT apps are therefore distinct content and get their own vector, which is
 * the point. The ~20x dedup saving comes from consecutive screenshots of the SAME
 * window, which still compose byte-identically.
 */
export function formatForEmbedding(ocrText: string, app: string, windowTitle: string): string {
  const context = [app.trim() ? `[${app.trim()}]` : '', windowTitle.trim()]
    .filter(Boolean)
    .join(' ')
  return context ? `${context}\n${ocrText}` : ocrText
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

/** One scored candidate: a content hash and its similarity to the query. */
export type ScoredHash = { hash: string; similarity: number }

/** One row of the vector store: a unique content hash and its vector. */
export type VectorRow = { hash: string; vec: Float32Array }

/** How many vector rows to read per chunk before yielding the event loop. */
export const VECTOR_SCAN_CHUNK = 200

/**
 * Running top-K accumulator, kept sorted weakest-first so `entries[0]` is always
 * the one a new candidate must beat.
 *
 * It is an incremental object rather than a fold over an iterable because the
 * scan that feeds it is chunked and *awaits* between chunks (see
 * `scanTopKBySimilarity`) — the state has to survive those suspension points.
 * Only K entries are ever retained: a vector is 12KB, so materializing the whole
 * store to rank it would cost tens of MB per search.
 */
export class TopKSimilar {
  private readonly entries: ScoredHash[] = []

  constructor(
    private readonly query: Float32Array,
    private readonly limit: number
  ) {}

  push(row: VectorRow): void {
    if (this.limit <= 0) return
    const similarity = dot(this.query, row.vec)
    if (this.entries.length < this.limit) {
      this.entries.push({ hash: row.hash, similarity })
      this.entries.sort((a, b) => a.similarity - b.similarity)
    } else if (similarity > this.entries[0].similarity) {
      this.entries[0] = { hash: row.hash, similarity }
      this.entries.sort((a, b) => a.similarity - b.similarity)
    }
  }

  /** The retained candidates, strongest first. */
  results(): ScoredHash[] {
    return [...this.entries].reverse()
  }
}

/**
 * Rank the whole vector store against `query` WITHOUT blocking the main process.
 *
 * better-sqlite3 is synchronous, so a single `SELECT` over every vector would
 * hold the main thread for the entire scan — freezing IPC, capture ingestion and
 * the UI for as long as it takes. Instead the caller hands us a `fetchChunk` that
 * reads a bounded page of rows, and we `await yieldToEventLoop()` between pages.
 * Each individual page is short; the app stays responsive no matter how large the
 * store grows, which makes the freeze structurally impossible rather than merely
 * unlikely.
 */
export async function scanTopKBySimilarity(
  fetchChunk: (offset: number, limit: number) => VectorRow[],
  query: Float32Array,
  limit: number,
  yieldToEventLoop: () => Promise<void>,
  chunkSize: number = VECTOR_SCAN_CHUNK
): Promise<ScoredHash[]> {
  const top = new TopKSimilar(query, limit)
  if (limit <= 0) return []
  for (let offset = 0; ; offset += chunkSize) {
    const rows = fetchChunk(offset, chunkSize)
    for (const row of rows) top.push(row)
    if (rows.length < chunkSize) break // short page == end of the store
    await yieldToEventLoop()
  }
  return top.results()
}
