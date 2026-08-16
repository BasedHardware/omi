// Task-title embedding service — an in-memory cosine index over the vectors of
// action items and staged tasks. Port of the macOS `EmbeddingService` (the TASK
// half, not the OCR/Rewind half), adapted to Windows by REUSING the Rewind
// embedding primitives (`embeddingClient` for the proxy call, `embedVector` for
// the vector math) instead of reimplementing either.
//
// Shape of the thing:
//   * On first search/backfill (and again after sign-in) the whole set of stored
//     task vectors is loaded into a `Map` for O(n) brute-force cosine ranking —
//     the working set is small (thousands, not millions), so a flat scan beats
//     the complexity of an ANN index, exactly as on macOS.
//   * New task titles are embedded as RETRIEVAL_DOCUMENT and persisted as a row
//     BLOB on their own table (via the storage wrappers), then added to the index.
//   * A search box embeds its query as RETRIEVAL_QUERY (the asymmetric
//     counterpart) and ranks the index by dot product.
//   * Everything is best-effort: no embedding path throws into its caller. When
//     the backend is unavailable the caller simply gets no semantic results.
//
// The service is INERT until the renderer relays a Firebase session (the token
// only exists in the renderer on Windows — same constraint as the other
// main-process assistants). It reads that session through
// `assistants/core/session.ts` and guards every persist with the session epoch,
// so a job started under user A can never write A's vector after A signs out.
import { EMBED_DIM, dot } from '../rewind/embedVector'
import { embedBatch, embedOne, type EmbedSession } from '../rewind/embeddingClient'
import { getBackendSession, getSessionEpoch } from '../assistants/core/session'
import type { TaskEmbeddingSource } from '../../shared/types'
import {
  getAllActionItemEmbeddings,
  getAllStagedTaskEmbeddings,
  getActionItemsMissingEmbeddings,
  getStagedTasksMissingEmbeddings,
  updateActionItemEmbedding,
  updateStagedTaskEmbedding
} from '../ipc/db'

/** A task's identity in the index. `id` is the local rowid of its source table;
 *  action_items and staged_tasks both start rowids at 1, so `source` is required
 *  to tell `action_item:1` from `staged_task:1` — a bare id would collide. This
 *  is macOS `EmbeddingService`'s exact reasoning. */
export type TaskEmbeddingKey = { source: TaskEmbeddingSource; id: number }

/** One scored candidate returned by `searchSimilar`. */
export type TaskSimilarity = { source: TaskEmbeddingSource; id: number; similarity: number }

/** Cap on the in-memory index. Action items are prioritized on load; once full,
 *  the lowest-id (oldest) entry is evicted to make room. Matches macOS. */
export const MAX_INDEX_SIZE = 5000

/** Task titles the launch backfill will embed before stopping, per macOS. */
const BACKFILL_MAX_PER_LAUNCH = 5000

/** Rows requested per backfill page (also the client's batch ceiling). */
const BACKFILL_PAGE = 100

/** Pause between backfill batches so a large sweep can't monopolize the API/DB. */
const BACKFILL_BATCH_DELAY_MS = 200

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// The index: composite `${source}:${id}` -> L2-normalized vector. Only the
// vectors are held; a search is a dot product over each (they are normalized on
// the way in, so the dot IS the cosine).
const index = new Map<string, Float32Array>()
let loaded = false

/** Composite key for the index. `source` never contains ':' and `id` is numeric,
 *  so `${source}:${id}` round-trips unambiguously (see `parseKey`). */
function keyOf(source: TaskEmbeddingSource, id: number): string {
  return `${source}:${id}`
}

/** Inverse of `keyOf`. Splits on the FIRST ':' — the id is everything after it. */
function parseKey(key: string): TaskEmbeddingKey {
  const at = key.indexOf(':')
  return { source: key.slice(0, at) as TaskEmbeddingSource, id: Number(key.slice(at + 1)) }
}

/** The relayed backend session narrowed to what the embedding proxy needs, or
 *  null when signed out / not yet relayed. */
function readSession(): EmbedSession | null {
  const s = getBackendSession()
  return s ? { desktopApiBase: s.desktopApiBase, token: s.token } : null
}

/**
 * A 402 (payment required / quota) or 429 (rate limited, after the client's own
 * retries) is an EXPECTED backend condition, not a bug: the backfill should stop
 * quietly and try again next launch rather than log an error for each one. The
 * client sanitizes proxy errors down to a status code in the message, so match on
 * that.
 */
function isExpectedBackendStop(e: unknown): boolean {
  const msg = e instanceof Error ? e.message : ''
  return /\b(402|429)\b/.test(msg)
}

/** Persist one vector as a row BLOB on its source table. */
function persistEmbedding(source: TaskEmbeddingSource, id: number, vec: Float32Array): void {
  if (source === 'action_item') updateActionItemEmbedding(id, vec)
  else updateStagedTaskEmbedding(id, vec)
}

/**
 * (Re)build the in-memory index from stored vectors. Idempotent: clears first, so
 * calling it again after sign-in refreshes the index for the new account. Fills
 * from action_items FIRST (highest ids = newest, up to the cap), then staged
 * tasks fill any remaining capacity — action items are prioritized, per macOS.
 */
export function loadIndex(): void {
  index.clear()
  const actions = getAllActionItemEmbeddings().sort((a, b) => b.id - a.id)
  for (const row of actions) {
    if (index.size >= MAX_INDEX_SIZE) break
    index.set(keyOf('action_item', row.id), row.embedding)
  }
  const staged = getAllStagedTaskEmbeddings().sort((a, b) => b.id - a.id)
  for (const row of staged) {
    if (index.size >= MAX_INDEX_SIZE) break
    index.set(keyOf('staged_task', row.id), row.embedding)
  }
  loaded = true
}

/** Load the index once, lazily, before the first search or backfill. */
function ensureLoaded(): void {
  if (!loaded) loadIndex()
}

/** Evict the entry with the lowest numeric id (oldest ≈ least useful). */
function evictLowest(): void {
  let lowestKey: string | null = null
  let lowestId = Infinity
  for (const key of index.keys()) {
    const id = parseKey(key).id
    if (id < lowestId) {
      lowestId = id
      lowestKey = key
    }
  }
  if (lowestKey !== null) index.delete(lowestKey)
}

/**
 * Add (or replace) a task's vector in the index. When the index is full and this
 * is a NEW key, the lowest-id entry is evicted first to stay at the cap — macOS's
 * LRU-ish bound.
 */
export function addToIndex(source: TaskEmbeddingSource, id: number, vec: Float32Array): void {
  const key = keyOf(source, id)
  if (!index.has(key) && index.size >= MAX_INDEX_SIZE) evictLowest()
  index.set(key, vec)
}

/**
 * Drop a task's vector from the index. FIX (ii): call this whenever a task row is
 * HARD-DELETED so the index can't keep serving a stale vector for a task that no
 * longer exists. Exposed for the sync engine's delete path; this module does not
 * depend on the sync engine.
 */
export function removeFromIndex(source: TaskEmbeddingSource, id: number): void {
  index.delete(keyOf(source, id))
}

/**
 * Embed a search query (`RETRIEVAL_QUERY`). Returns null — never throws — when
 * semantic search is unavailable (no session, empty text, backend error) so the
 * caller can fall back. The client L2-normalizes the vector already.
 */
export async function embedQuery(text: string): Promise<Float32Array | null> {
  const session = readSession()
  if (!session || !text.trim()) return null
  try {
    const vec = await embedOne(session, text, 'RETRIEVAL_QUERY')
    return vec.length === EMBED_DIM ? vec : null
  } catch (e) {
    console.warn(`[task-embed] query embed failed: ${(e as Error).message}`)
    return null
  }
}

/**
 * Rank the whole in-memory index against `queryVec` by cosine similarity
 * (a plain dot product — everything is normalized), returning the top `topK`
 * strongest first. Callers apply their own similarity threshold; this only sorts.
 */
export function searchSimilar(queryVec: Float32Array, topK = 10): TaskSimilarity[] {
  ensureLoaded()
  const scored: TaskSimilarity[] = []
  for (const [key, vec] of index) {
    const { source, id } = parseKey(key)
    scored.push({ source, id, similarity: dot(queryVec, vec) })
  }
  scored.sort((a, b) => b.similarity - a.similarity)
  return scored.slice(0, Math.max(0, topK))
}

/**
 * Embed one task title as a stored passage (`RETRIEVAL_DOCUMENT`), persist it, and
 * add it to the index. Best-effort: never throws. The write is epoch-guarded —
 * the session is re-checked AFTER the (awaited) embed and BEFORE the DB write with
 * no await in between, so a sign-out/switch that landed during the request drops
 * the vector instead of writing the previous user's data.
 */
export async function generateEmbeddingForTask(
  source: TaskEmbeddingSource,
  id: number,
  text: string
): Promise<void> {
  const session = readSession()
  if (!session || !text.trim()) return
  const epoch = getSessionEpoch()
  try {
    const vec = await embedOne(session, text, 'RETRIEVAL_DOCUMENT')
    if (getSessionEpoch() !== epoch) return // session changed mid-request; drop
    if (vec.length !== EMBED_DIM) return
    persistEmbedding(source, id, vec)
    addToIndex(source, id, vec)
  } catch (e) {
    console.warn(`[task-embed] embed for ${source}:${id} failed: ${(e as Error).message}`)
  }
}

/** One page of missing-embedding rows for a source. */
function missingPage(
  source: TaskEmbeddingSource,
  limit: number
): { id: number; description: string }[] {
  return source === 'action_item'
    ? getActionItemsMissingEmbeddings(limit)
    : getStagedTasksMissingEmbeddings(limit)
}

/**
 * Sweep tasks that have a title but no vector yet, embedding them in batches so an
 * existing task list becomes searchable without a burst of API calls. Resumable
 * across launches by construction: a persisted vector drops that row out of the
 * "missing" query, so there is no cursor to keep.
 *
 * Stops on session loss or an expected backend condition (402/429 — quota/rate),
 * neither of which is error-reported. Capped per launch, like macOS.
 */
export async function backfillMissing(): Promise<void> {
  ensureLoaded()
  let embedded = 0
  for (const source of ['action_item', 'staged_task'] as const) {
    while (embedded < BACKFILL_MAX_PER_LAUNCH) {
      const session = readSession()
      if (!session) return // signed out mid-sweep; the next launch resumes it
      const limit = Math.min(BACKFILL_PAGE, BACKFILL_MAX_PER_LAUNCH - embedded)
      const rows = missingPage(source, limit)
      if (rows.length === 0) break // this source is fully embedded

      const epoch = getSessionEpoch()
      let vectors: (Float32Array | null)[]
      try {
        vectors = await embedBatch(
          session,
          rows.map((r) => r.description),
          'RETRIEVAL_DOCUMENT'
        )
      } catch (e) {
        if (isExpectedBackendStop(e)) return // quota/rate limited — stop quietly
        console.warn(`[task-embed] backfill batch failed: ${(e as Error).message}`)
        return
      }
      if (getSessionEpoch() !== epoch) return // session changed mid-request
      // Strict 1:1: the client returns one entry per input, so a length mismatch
      // means the mapping is untrustworthy — fail the batch rather than misassign
      // a vector to the wrong task (macOS's rule).
      if (vectors.length !== rows.length) return

      let persistedThisPage = 0
      for (let i = 0; i < rows.length; i++) {
        const vec = vectors[i]
        if (!vec || vec.length !== EMBED_DIM) continue // API dropped/malformed this item
        persistEmbedding(source, rows[i].id, vec)
        addToIndex(source, rows[i].id, vec)
        embedded++
        persistedThisPage++
      }
      // A page where nothing persisted can only be rows the API keeps rejecting;
      // they stay NULL and would re-appear at the head forever. Stop this source
      // rather than spin.
      if (persistedThisPage === 0) break
      await sleep(BACKFILL_BATCH_DELAY_MS)
    }
  }
}
