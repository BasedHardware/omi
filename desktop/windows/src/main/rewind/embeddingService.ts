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
import { EMBED_MODEL, EMBED_DIM, formatForEmbedding } from './embedVector'
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

// Frames the queue refused as unembeddable (OCR text under MIN_EMBED_TEXT_LEN
// once trimmed). They can never produce a vector, so — exactly like the failed
// set — they must be excluded from the work query, or they sit at the head of
// every page forever and the sweep stalls behind them. See runBackfill.
const unembeddableThisLaunch = new Set<number>()

let session: EmbedSession | null = null
// Firebase uid behind `session.token`, so a user SWITCH is detectable and not
// just a sign-out. See configureRewindEmbedSession.
let sessionUid: string | null = null
let timer: NodeJS.Timeout | null = null
let flushInFlight: Promise<void> | null = null
let backfilling = false
let backfilled = 0

// Bumped whenever the service is torn down or the user changes. Anything
// suspended on an await (an API call, the backfill's 200ms inter-batch pause)
// would otherwise wake up afterwards and keep working against whatever state
// replaced it — writing the PREVIOUS user's vectors into the freshly-wiped
// database. Every async path captures the generation it started in and stops as
// soon as that is no longer current.
let generation = 0

/** Firebase uid (`sub`) inside an id token, or null if it isn't a readable JWT
 *  (E2E stubs, malformed tokens). Never throws — a failure to read the uid must
 *  not disarm indexing, it just means we can only detect sign-OUT, not a switch. */
function tokenUid(token: string): string | null {
  const payload = token.split('.')[1]
  if (!payload) return null
  try {
    const json = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as {
      sub?: string
      user_id?: string
    }
    return json.sub ?? json.user_id ?? null
  } catch {
    return null
  }
}

/**
 * Forget everything the previous user left behind.
 *
 * Clearing `session` alone is NOT enough, and that was a real leak: the queue can
 * hold ~40 frames of user A's OCR text at sign-out, main-process module state
 * survives the renderer reload, and nothing restarts Electron's main process on
 * sign-out. So when user B signed in, the next 5s tick drained A's screen text to
 * the embedding proxy UNDER B'S BEARER TOKEN and wrote the resulting vectors into
 * the just-wiped database. Same-account is no better: sign out, sign back in, and
 * vectors derived from pre-wipe screen content are resurrected — which is exactly
 * the promise ("delete my history leaves no vector of screen content behind")
 * that the wipe exists to keep.
 *
 * Bumping `generation` is what stops the work already in flight; clearing the
 * four containers is what stops the work merely queued.
 */
function forgetSession(): void {
  generation++ // abandon anything suspended on an await, mid-flight or mid-sweep
  queue.take(Number.MAX_SAFE_INTEGER) // A's OCR text must not outlive A's session
  recentHashes.clear() // else a stale hash "links" to a vector the wipe deleted
  failedThisLaunch.clear()
  unembeddableThisLaunch.clear()
  flushInFlight = null // the old drain is now a no-op; don't chain behind it
  backfilling = false
  backfilled = 0
}

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
 *
 * A routine token refresh (same uid) must NOT reset anything — it arrives every
 * hour and would otherwise throw away a queue and a half-finished sweep.
 */
export function configureRewindEmbedSession(next: EmbedSession | null): void {
  const valid = next && next.token && next.desktopApiBase ? next : null
  const nextUid = valid ? tokenUid(valid.token) : null

  // Sign-out, or a different user: nothing of the old session may survive.
  if (!valid || (sessionUid !== null && nextUid !== sessionUid)) forgetSession()

  session = valid
  sessionUid = nextUid
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
export function enqueueRewindEmbedding(
  frameId: number,
  ocrText: string,
  app: string,
  windowTitle: string
): boolean {
  if (failedThisLaunch.has(frameId)) return false
  if (queue.size >= MAX_PENDING) return false
  // The length floor is checked against the RAW OCR text, before the app context is
  // prepended (macOS does the same — OCREmbeddingService.swift:65). Checking the
  // formatted string instead would let a frame with NO screen text clear the floor
  // on its "[Google Chrome] New Tab" prefix alone, and we would pay for a vector of
  // pure window chrome.
  if (!isEmbeddableText(ocrText)) return false
  return queue.add(frameId, formatForEmbedding(ocrText, app, windowTitle), Date.now())
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
async function flushBatch(
  items: PendingEmbed[],
  current: EmbedSession,
  mine: number
): Promise<void> {
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
  // The sign-out/wipe can land while that request is in flight. Persisting now
  // would write the previous user's vectors into the wiped database as orphans
  // (their frames are gone), so drop them on the floor instead.
  if (generation !== mine) return
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

/**
 * Drain the queue. Assumes the caller holds the single-flight slot.
 *
 * The session is re-checked on EVERY iteration, not captured once: a sign-out
 * landing mid-drain used to leave this loop happily sending the signed-out user's
 * frames with each `await`, because `current` was a stale local.
 */
async function drain(current: EmbedSession, force: boolean): Promise<void> {
  const mine = generation
  while (queue.size > 0) {
    if (generation !== mine || session !== current) return // signed out / user changed
    const batch = queue.take(EMBED_BATCH_SIZE)
    try {
      await flushBatch(batch, current, mine)
    } catch (e) {
      // Degrade quietly: these frames stay unembedded (keyword search still
      // finds them) and the sweep moves on. There is no Windows recordFallback
      // emitter to route this through yet (see the Track 3 TODO in
      // assistants/aiUserProfile/orchestrate.ts), so a log is the honest option.
      if (generation !== mine) return // torn down mid-request; not the new session's failure
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
 * Frames that cannot be embedded are excluded IN SQL rather than filtered out
 * afterwards. Filtering after the fact was a bug, twice over — the query kept
 * handing back rows the queue would refuse, and an all-refused page read as
 * "caught up", silently abandoning the rest of the launch's budget:
 *
 *  - frames whose batch FAILED this launch (transient API error), and
 *  - frames whose OCR text is too short to embed (`MIN_EMBED_TEXT_LEN`): a lock
 *    screen, a full-screen video, a blank desktop, a clock. These are the newest
 *    rows, so they pile up at the head of `ORDER BY ts DESC` and never leave —
 *    they can never earn an embedding row, which is the only thing that drops a
 *    frame out of the work query. Past ~100 of them, page 1 is 100% dead weight
 *    on this and EVERY FUTURE launch, and the whole pre-existing library is
 *    silently never indexed.
 *
 * Both are excluded in the query, so the sweep advances past them to the work
 * that is still doable.
 */
async function runBackfill(): Promise<void> {
  const mine = generation
  while (backfilled < BACKFILL_MAX_PER_LAUNCH) {
    if (generation !== mine) return // torn down while we were suspended
    if (!session) return // signed out mid-sweep; the next session push resumes it
    const remaining = BACKFILL_MAX_PER_LAUNCH - backfilled
    const frames = rewindFramesNeedingEmbedding(Math.min(EMBED_BATCH_SIZE, remaining), [
      ...failedThisLaunch,
      ...unembeddableThisLaunch
    ])
    if (frames.length === 0) return // genuinely caught up: no embeddable rows left

    // Count what the queue ACCEPTED, not what the query returned — `add` drops a
    // frame that is already queued, and the budget must track submitted work.
    let accepted = 0
    let skipped = 0
    for (const f of frames) {
      if (f.id == null) continue
      // Belt to the SQL filter's braces: SQLite's TRIM only strips spaces, while
      // the queue's guard is JS `.trim()` (tabs, newlines, NBSP…). A row the query
      // thinks is long enough but the queue refuses would otherwise be exactly the
      // dead weight described above.
      if (!isEmbeddableText(f.ocrText)) {
        unembeddableThisLaunch.add(f.id)
        skipped++
        continue
      }
      if (enqueueRewindEmbedding(f.id, f.ocrText, f.app, f.windowTitle)) accepted++
    }
    // Nothing submitted AND nothing newly excluded means this page cannot change
    // — the next query would return it verbatim. Stop rather than spin. (If we
    // skipped some, the next page IS different: those ids are now excluded.)
    if (accepted === 0 && skipped === 0) return
    if (accepted === 0) continue // a page of pure dead weight; move past it
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

/** Test seam: reset all module state. Deliberately built ON `forgetSession()`
 *  rather than beside it — the two drifting apart is what C2 was: the reset knew
 *  every field sign-out had to clear, and production cleared exactly one of them. */
export function __resetRewindEmbeddingForTests(): void {
  if (timer) clearInterval(timer)
  timer = null
  session = null
  sessionUid = null
  forgetSession()
}
