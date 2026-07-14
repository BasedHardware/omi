// Rewind embedding indexer — the impure runner around the pure policy in
// `embedQueue.ts` / `embedVector.ts`. Port of the macOS service.
//
// Shape of the thing:
//   * OCR finishes a frame -> `enqueueRewindEmbedding()` (fire-and-forget; this
//     NEVER blocks capture or OCR, exactly as on macOS).
//   * A tick loop flushes when the queue hits 100 items or the oldest has waited
//     60s, whichever comes first.
//   * On launch, a backfill sweeps frames that have OCR text but no vector yet
//     (capped, batched, paced) so an existing library becomes searchable without
//     a burst of API calls.
//   * Everything is best-effort. No embedding path may ever throw into capture,
//     OCR, or search — semantic search is additive recall, and its absence just
//     means keyword-only results.
//
// The service is INERT until the renderer relays a Firebase session (the token
// only exists there on Windows — same constraint as the AI-profile service).
import { EMBED_MODEL, EMBED_DIM } from './embedVector'
import {
  EMBED_BATCH_SIZE,
  EmbedQueue,
  RecentHashCache,
  planEmbedBatch,
  type PendingEmbed
} from './embedQueue'
import { embedBatch, embedOne, type EmbedSession } from './embeddingClient'
import { getRewindEmbedding, rewindFramesNeedingEmbedding, upsertRewindEmbedding } from '../ipc/db'

/** How often the flush timer checks the queue (the 60s deadline lives in the queue). */
const TICK_MS = 5_000

/** Frames the launch backfill will embed before stopping, per macOS. */
const BACKFILL_MAX_PER_LAUNCH = 5000

/** Pause between backfill batches so a large sweep can't monopolize the API or the DB. */
const BACKFILL_BATCH_DELAY_MS = 200

/** Ceiling on the in-memory queue — see `enqueueRewindEmbedding`. */
const MAX_PENDING = 500

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

const queue = new EmbedQueue()
const recentHashes = new RecentHashCache()

// Frames whose embed already failed this launch. Without this, the backfill's
// LEFT JOIN would hand back the same permanently-failing frames on every pass and
// the sweep would never advance. Cleared on restart, so a transient failure does
// get another chance — just not an immediate, spinning one.
const failedThisLaunch = new Set<number>()

let session: EmbedSession | null = null
let timer: NodeJS.Timeout | null = null
let flushing = false
let backfilling = false
let backfilled = 0

/**
 * Set (or clear, on sign-out) the backend session used for embedding calls.
 * Relayed from the renderer on sign-in and on every id-token refresh (~hourly),
 * which keeps main's token fresh so background calls don't start 401ing.
 *
 * A non-null session also kicks the backfill. That closes the startup race —
 * main is ready long before the renderer has a Firebase token, so a backfill
 * kicked at app-ready would find no session and give up for the whole launch.
 * Re-kicks are cheap (a caught-up sweep is one query returning no rows) and are
 * how frames captured while signed out eventually get indexed.
 */
export function configureRewindEmbedSession(next: EmbedSession | null): void {
  session = next && next.token && next.desktopApiBase ? next : null
  if (session) kickBackfill()
}

/** True when semantic search is usable right now (a signed-in session exists). */
export function rewindEmbeddingsAvailable(): boolean {
  return session !== null
}

/**
 * Queue a frame's OCR text for embedding. Non-blocking; safe to call straight
 * from the OCR loop.
 *
 * The queue is bounded because it is fed by an unbounded producer: with no
 * session (signed out) nothing drains, and capture would otherwise grow this
 * list forever. Overflow is not data loss — a dropped frame still has its OCR
 * text on disk with no vector, which is precisely what the backfill sweeps up.
 */
export function enqueueRewindEmbedding(frameId: number, text: string): void {
  if (failedThisLaunch.has(frameId)) return
  if (queue.size >= MAX_PENDING) return
  queue.add(frameId, text, Date.now())
}

/** Persist one vector and remember its content hash, so an identical screen
 *  captured later copies this row instead of paying for another API call. */
function store(frameId: number, hash: string, vec: Float32Array): void {
  upsertRewindEmbedding(frameId, vec, EMBED_MODEL)
  recentHashes.set(hash, frameId)
}

/**
 * Embed + persist one batch. Groups by content hash first (dedup within the
 * batch), copies vectors for content embedded recently (dedup against the cache),
 * and sends only what is genuinely new to the API — the combination is what
 * macOS measures as a ~20x cut in embedding API volume.
 */
async function flushBatch(items: PendingEmbed[], current: EmbedSession): Promise<void> {
  const { toEmbed, toCopy } = planEmbedBatch(items, recentHashes)

  for (const group of toCopy) {
    const vec = getRewindEmbedding(group.sourceFrameId)
    if (vec) {
      for (const frameId of group.frameIds) store(frameId, group.hash, vec)
    } else {
      // The cached twin's row is gone (retention pruned it) — re-embed instead.
      recentHashes.delete(group.hash)
      toEmbed.push(group)
    }
  }

  if (toEmbed.length === 0) return

  const vectors = await embedBatch(
    current,
    toEmbed.map((g) => g.text),
    'RETRIEVAL_DOCUMENT'
  )
  for (let i = 0; i < toEmbed.length; i++) {
    const group = toEmbed[i]
    const vec = vectors[i]
    if (!vec) {
      for (const frameId of group.frameIds) failedThisLaunch.add(frameId)
      continue
    }
    for (const frameId of group.frameIds) store(frameId, group.hash, vec)
  }
}

/** Flush every ready batch. Single-flight: a slow API call must not overlap with
 *  the next tick (which would double-send the same frames). */
async function flushDue(force = false): Promise<void> {
  if (flushing) return
  const current = session
  if (!current) return
  if (!force && !queue.shouldFlush(Date.now())) return

  flushing = true
  try {
    while (queue.size > 0) {
      const batch = queue.take(EMBED_BATCH_SIZE)
      try {
        await flushBatch(batch, current)
      } catch (e) {
        // Degrade quietly: these frames stay unembedded (keyword search still
        // finds them) and the sweep moves on. There is no Windows recordFallback
        // emitter to route this through yet (see the Track 3 TODO in
        // assistants/aiUserProfile/orchestrate.ts), so a log is the honest option.
        for (const item of batch) failedThisLaunch.add(item.frameId)
        console.warn(`[rewind-embed] batch of ${batch.length} failed: ${(e as Error).message}`)
        return
      }
      if (!force && !queue.shouldFlush(Date.now())) return
    }
  } finally {
    flushing = false
  }
}

/**
 * Embed a search query (`RETRIEVAL_QUERY` — the asymmetric counterpart to the
 * stored passages' `RETRIEVAL_DOCUMENT`). Returns null, never throws, when
 * semantic search is unavailable: the caller falls back to keyword-only.
 */
export async function embedRewindQuery(text: string): Promise<Float32Array | null> {
  const current = session
  if (!current || !text.trim()) return null
  try {
    const vec = await embedOne(current, text, 'RETRIEVAL_QUERY')
    return vec.length === EMBED_DIM ? vec : null
  } catch (e) {
    console.warn(`[rewind-embed] query embed failed, keyword-only: ${(e as Error).message}`)
    return null
  }
}

/**
 * Sweep frames that have OCR text but no vector. Resumable across launches by
 * construction: a persisted vector is never recomputed, so the LEFT JOIN behind
 * `rewindFramesNeedingEmbedding` returns exactly the work that remains — there is
 * no cursor to persist, and none to corrupt.
 */
async function runBackfill(): Promise<void> {
  while (backfilled < BACKFILL_MAX_PER_LAUNCH) {
    if (!session) return // signed out mid-sweep; the next session push resumes it
    const remaining = BACKFILL_MAX_PER_LAUNCH - backfilled
    const frames = rewindFramesNeedingEmbedding(Math.min(EMBED_BATCH_SIZE, remaining))
    const fresh = frames.filter((f) => f.id != null && !failedThisLaunch.has(f.id))
    if (fresh.length === 0) return // caught up

    for (const f of fresh) enqueueRewindEmbedding(f.id as number, f.ocrText)
    backfilled += fresh.length
    await flushDue(true)
    await sleep(BACKFILL_BATCH_DELAY_MS)
  }
  console.log(`[rewind-embed] backfill hit the ${BACKFILL_MAX_PER_LAUNCH}/launch cap`)
}

/** Run the sweep unless one is already in flight. Single-flight matters because
 *  every hourly token refresh calls in here. */
function kickBackfill(): void {
  if (backfilling) return
  backfilling = true
  void runBackfill()
    .catch((e) => console.warn(`[rewind-embed] backfill stopped: ${(e as Error).message}`))
    .finally(() => {
      backfilling = false
    })
}

/** Start the flush timer. The backfill starts on its own once a session arrives
 *  (see `configureRewindEmbedSession`). Idempotent. */
export function startRewindEmbedding(): void {
  if (timer) clearInterval(timer)
  timer = setInterval(() => void flushDue(), TICK_MS)
}

/** Test seam: reset all module state. */
export function __resetRewindEmbeddingForTests(): void {
  if (timer) clearInterval(timer)
  timer = null
  session = null
  flushing = false
  backfilling = false
  backfilled = 0
  failedThisLaunch.clear()
  queue.take(Number.MAX_SAFE_INTEGER)
}
