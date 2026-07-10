/**
 * Client-owned outbox for syncing screen-session conversations to Omi via
 * POST /v1/conversations/from-segments.
 *
 * WHY CLIENT-OWNED IDEMPOTENCY (do not simplify this away): prod does NOT honor
 * `client_session_id` — a blind retry of the same payload DUPLICATES the
 * conversation (verified live 2026-07-10). We still send client_session_id (it
 * is harmless today and becomes real idempotency when upstream deploys), but
 * until then the retry discipline below is the only duplicate protection:
 *
 *   1. An outbox row is persisted BEFORE the first POST (state 'pending').
 *   2. 'posting' marks an in-flight POST; it resolves to exactly one of:
 *        - 'done'        HTTP success → cloud id recorded.
 *        - 'failed'      an HTTP error RESPONSE arrived → the server did not
 *                        create a conversation → safe to re-post later.
 *        - 'unconfirmed' AMBIGUOUS: timeout / connection drop after send — the
 *                        server may or may not have created the conversation.
 *   3. A retry from 'unconfirmed' NEVER re-posts blindly. It first fetches the
 *      recent cloud conversations and looks for one whose started_at/finished_at
 *      match ours (we set both exactly in the request, so they round-trip);
 *      segment count breaks ties. Match → adopt it ('done'). No match → the
 *      earlier POST evidently never landed → re-post.
 *   4. A row found in 'posting' with no in-flight request in this process is a
 *      crash mid-POST — recover it as 'unconfirmed' (ambiguous by definition).
 *
 * Rate limit: from-segments allows 30/hour. One-off retries ride the normal
 * axios 429 backoff; bulk backfill is paced separately (see backfill.ts).
 */
import type { ConversationSyncPatch, ConversationSyncState, SyncSegment } from '../../../../shared/types'

export const FROM_SEGMENTS_PATH = '/v1/conversations/from-segments'

/** Legal outbox transitions (see the state chart on ConversationSyncState). */
const TRANSITIONS: Record<ConversationSyncState, ConversationSyncState[]> = {
  local_only: ['pending'],
  pending: ['posting'],
  posting: ['done', 'failed', 'unconfirmed'],
  failed: ['posting'],
  unconfirmed: ['posting', 'done'],
  done: []
}

export function canTransition(from: ConversationSyncState, to: ConversationSyncState): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false
}

export type SyncableConversation = {
  id: string
  startedAt: number // epoch ms
  endedAt: number // epoch ms
  segments: SyncSegment[]
  syncState: ConversationSyncState
  cloudId?: string | null
}

export type FromSegmentsRequest = {
  transcript_segments: SyncSegment[]
  started_at: string
  finished_at: string
  language: string
  source: 'desktop'
  client_platform: 'windows'
  client_session_id: string
}

/** Build the POST body. `source: 'desktop'` is the only provenance field that
 * round-trips on prod; client_platform is accepted but not returned (rely on
 * source), and client_session_id is future idempotency (ignored today). */
export function buildFromSegmentsRequest(conv: SyncableConversation, language = 'en'): FromSegmentsRequest {
  return {
    transcript_segments: conv.segments,
    started_at: new Date(conv.startedAt).toISOString(),
    finished_at: new Date(conv.endedAt).toISOString(),
    language,
    source: 'desktop',
    client_platform: 'windows',
    client_session_id: conv.id
  }
}

/** The slice of a cloud conversation the dedupe check needs. */
export type CloudConversationLite = {
  id: string
  started_at?: string | null
  finished_at?: string | null
  transcript_segments?: unknown[] | null
}

const MATCH_TOLERANCE_MS = 2_000

/**
 * Find the cloud conversation our earlier (unconfirmed) POST may have created.
 * We can't query by client_session_id, so match on the started_at/finished_at we
 * set explicitly in the request (they round-trip). Tolerance absorbs ISO
 * parsing/precision drift; among several in-window candidates, an exact segment
 * count wins, then the closest started_at.
 */
export function findCloudMatch(
  conv: { startedAt: number; endedAt: number; segmentCount?: number },
  cloud: CloudConversationLite[],
  toleranceMs = MATCH_TOLERANCE_MS
): string | null {
  type Candidate = { id: string; startDiff: number; countMatch: boolean }
  const candidates: Candidate[] = []
  for (const c of cloud) {
    if (!c.started_at) continue
    const started = Date.parse(c.started_at)
    if (!Number.isFinite(started) || Math.abs(started - conv.startedAt) > toleranceMs) continue
    if (c.finished_at) {
      const finished = Date.parse(c.finished_at)
      if (Number.isFinite(finished) && Math.abs(finished - conv.endedAt) > toleranceMs) continue
    }
    candidates.push({
      id: c.id,
      startDiff: Math.abs(started - conv.startedAt),
      countMatch:
        conv.segmentCount !== undefined &&
        Array.isArray(c.transcript_segments) &&
        c.transcript_segments.length === conv.segmentCount
    })
  }
  candidates.sort((a, b) => Number(b.countMatch) - Number(a.countMatch) || a.startDiff - b.startDiff)
  return candidates[0]?.id ?? null
}

/** A classified POST failure. `ambiguous: false` requires positive evidence that
 * the server did NOT create the conversation (an HTTP error response). */
export type SyncFailure = { ambiguous: boolean; message: string }

function normalizeFailure(e: unknown): SyncFailure {
  const anyE = e as { ambiguous?: unknown; message?: unknown }
  return {
    // Unclassified throws default to AMBIGUOUS: never blind-repost on a maybe.
    ambiguous: typeof anyE?.ambiguous === 'boolean' ? anyE.ambiguous : true,
    message: typeof anyE?.message === 'string' && anyE.message ? anyE.message : String(e)
  }
}

export type SyncDeps = {
  /** POST from-segments; resolve with the created conversation id. Rejections
   * should carry `{ ambiguous, message }` (see classify helpers in
   * conversationSync.ts); unclassified rejections are treated as ambiguous. */
  post: (req: FromSegmentsRequest) => Promise<{ id: string }>
  /** Recent cloud conversations, newest first (for the unconfirmed dedupe). */
  listRecent: () => Promise<CloudConversationLite[]>
  /** Persist an outbox transition (IPC → SQLite in production). */
  persist: (id: string, patch: ConversationSyncPatch) => Promise<void>
}

export type SyncOutcome =
  | { status: 'done'; cloudId: string; deduped: boolean }
  | { status: 'failed'; error: string }
  | { status: 'unconfirmed'; error: string }

/**
 * Drive one conversation through the outbox to a terminal-ish state. Accepts
 * rows in any non-'posting' state ('local_only' rows — backfill — pass through
 * 'pending' first; recover crashed 'posting' rows to 'unconfirmed' before
 * calling, see recoverOrphanedPosting in conversationSync.ts).
 */
export async function syncConversation(
  conv: SyncableConversation,
  deps: SyncDeps,
  language = 'en'
): Promise<SyncOutcome> {
  let state = conv.syncState

  if (state === 'done') return { status: 'done', cloudId: conv.cloudId ?? '', deduped: false }
  if (state === 'posting') throw new Error(`syncConversation(${conv.id}): already posting`)

  if (state === 'local_only') {
    await deps.persist(conv.id, { syncState: 'pending' })
    state = 'pending'
  }

  if (conv.segments.length === 0) {
    await deps.persist(conv.id, { syncState: 'failed', syncError: 'no segments to sync' })
    return { status: 'failed', error: 'no segments to sync' }
  }

  // Unconfirmed → the mandatory dedupe check BEFORE any re-post.
  if (state === 'unconfirmed') {
    let cloud: CloudConversationLite[]
    try {
      cloud = await deps.listRecent()
    } catch (e) {
      // Can't verify → stay unconfirmed; a later retry re-runs the check.
      return { status: 'unconfirmed', error: `dedupe check failed: ${(e as Error).message}` }
    }
    const match = findCloudMatch(
      { startedAt: conv.startedAt, endedAt: conv.endedAt, segmentCount: conv.segments.length },
      cloud
    )
    if (match) {
      await deps.persist(conv.id, { syncState: 'done', cloudId: match, syncError: null })
      return { status: 'done', cloudId: match, deduped: true }
    }
    // No cloud twin — the earlier POST never landed; safe to re-post.
  }

  await deps.persist(conv.id, { syncState: 'posting', incrementAttempts: true })
  try {
    const { id: cloudId } = await deps.post(buildFromSegmentsRequest(conv, language))
    await deps.persist(conv.id, { syncState: 'done', cloudId, syncError: null })
    return { status: 'done', cloudId, deduped: false }
  } catch (e) {
    const failure = normalizeFailure(e)
    const to: ConversationSyncState = failure.ambiguous ? 'unconfirmed' : 'failed'
    await deps.persist(conv.id, { syncState: to, syncError: failure.message })
    return failure.ambiguous
      ? { status: 'unconfirmed', error: failure.message }
      : { status: 'failed', error: failure.message }
  }
}
