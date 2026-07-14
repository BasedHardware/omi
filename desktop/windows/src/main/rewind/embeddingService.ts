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
  isEmbeddableText,
  planEmbedBatch,
  type PendingEmbed
} from './embedQueue'
import { embedBatch, embedOne, type EmbedSession } from './embeddingClient'
import { linkRewindEmbedding, rewindFramesNeedingEmbedding, upsertRewindEmbedding } from '../ipc/db'

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
let flushInFlight: Promise<void> | null = null
let backfilling = false
let backfilled = 0

// Bumped whenever the service is torn down. A backfill suspended on an await
// (an API call, its 200ms inter-batch pause) would otherwise wake up afterwards
// and keep sweeping against whatever state replaced it. Each sweep captures the
// generation it started in and stops as soon as that is no longer current.
let generation = 0

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
 * Queue a frame's OCR text for embedding, returning whether it was accepted.
 * Non-blocking; safe to call straight from the OCR / capture hot path.
 *
 * The queue is bounded because it is fed by an unbounded producer: with no
 * session (signed out) nothing drains, and capture would otherwise grow this
 * list forever. Overflow is not data loss — a dropped frame still has its OCR
 * text on disk with no vector, which is precisely what the backfill sweeps up.
 */
export function enqueueRewindEmbedding(frameId: number, text: string): boolean {
  if (failedThisLaunch.has(frameId)) return false
  if (queue.size >= MAX_PENDING) return false
  if (!isEmbeddableText(text)) return false
  return queue.add(frameId, text, Date.now())
}

/** Persist a vector for this content (once) and point the frames at it, then
 *  remember the hash so an identical screen later links instead of paying for
 *  another API call. Store BEFORE caching: a cached hash must always have a row. */
function store(frameIds: number[], hash: string, vec: Float32Array): void {
  for (const frameId of frameIds) upsertRewindEmbedding(frameId, hash, vec, EMBED_MODEL)
  recentHashes.add(hash)
}

/**
 * Embed + persist one batch. Groups by content hash first (dedup within the
 * batch), links content embedded recently to its existing vector (dedup against
 * the cache), and sends only what is genuinely new to the API — the combination
 * is what macOS measures as a ~20x cut in embedding API volume.
 */
async function flushBatch(items: PendingEmbed[], current: EmbedSession): Promise<void> {
  const { toEmbed, toCopy } = planEmbedBatch(items, recentHashes)

  for (const group of toCopy) {
    // linkRewindEmbedding is false only if the vector is gone (retention pruned
    // it between the cache write and now) — then it is genuinely new work.
    const linked = group.frameIds.every((frameId) => linkRewindEmbedding(frameId, group.hash))
    if (!linked) {
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
    store(group.frameIds, group.hash, vec)
  }
}

/** Drain the queue. Assumes the caller holds the single-flight slot. */
async function drain(current: EmbedSession, force: boolean): Promise<void> {
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
}

/**
 * Flush every ready batch, one flush at a time.
 *
 * Single-flight, but a forced caller (the backfill) WAITS for the in-flight
 * flush and then runs its own instead of bailing out — bailing would let the
 * backfill count frames it never actually submitted, silently under-delivering
 * against its budget. A timer tick, which has nothing to deliver, still returns
 * immediately rather than queueing up behind a slow API call.
 */
async function flushDue(force = false): Promise<void> {
  if (!session) return
  if (!force && (flushInFlight || !queue.shouldFlush(Date.now()))) return

  // Chain onto whatever is running so two flushes can never overlap (which would
  // double-send the same frames), while a forced caller still gets its turn.
  const run = async (): Promise<void> => {
    await flushInFlight?.catch(() => {})
    const current = session
    if (!current) return
    await drain(current, force)
  }
  const mine = run().finally(() => {
    if (flushInFlight === mine) flushInFlight = null
  })
  flushInFlight = mine
  await mine
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
 *
 * Frames that failed this launch are excluded IN SQL rather than filtered out
 * afterwards. Filtering after the fact was a bug: one transient API failure left
 * the query returning the same (now-skipped) rows forever, the post-filter emptied
 * them, and an empty list read as "caught up" — silently abandoning the rest of
 * the launch's budget. Excluding them in the query lets the sweep advance past
 * them to the work that is still doable.
 */
async function runBackfill(): Promise<void> {
  const mine = generation
  while (backfilled < BACKFILL_MAX_PER_LAUNCH) {
    if (generation !== mine) return // torn down while we were suspended
    if (!session) return // signed out mid-sweep; the next session push resumes it
    const remaining = BACKFILL_MAX_PER_LAUNCH - backfilled
    const frames = rewindFramesNeedingEmbedding(Math.min(EMBED_BATCH_SIZE, remaining), [
      ...failedThisLaunch
    ])
    if (frames.length === 0) return // genuinely caught up: no embeddable rows left

    // Count what the queue ACCEPTED, not what the query returned — `add` drops a
    // frame that is already queued, and the budget must track submitted work.
    let accepted = 0
    for (const f of frames) {
      if (f.id != null && enqueueRewindEmbedding(f.id, f.ocrText)) accepted++
    }
    // A page the queue accepted nothing from cannot make progress, and the same
    // page would come back next iteration — stop rather than spin.
    if (accepted === 0) return
    backfilled += accepted
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
  flushInFlight = null
  backfilling = false
  backfilled = 0
  generation++ // abandon any sweep still suspended on an await
  failedThisLaunch.clear()
  recentHashes.clear() // else a stale hash makes the next run "link" to a vector that isn't there
  queue.take(Number.MAX_SAFE_INTEGER)
}
