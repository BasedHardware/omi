/**
 * Renderer glue between the pure outbox (outbox.ts) and the real world:
 * the Firebase-authed axios client for POST/GET, and the main-process SQLite
 * outbox rows via window.omi.updateLocalConversationSync.
 */
import axios from 'axios'
import { omiApi } from '../apiClient'
import { getPreferences } from '../preferences'
import {
  FROM_SEGMENTS_PATH,
  syncConversation,
  type CloudConversationLite,
  type FromSegmentsRequest,
  type SyncFailure,
  type SyncOutcome
} from './outbox'
import type { ConversationSyncState, LocalConversation } from '../../../../shared/types'

/** Give up on automatic retries after this many attempts; the row stays visible
 * as failed/unconfirmed and backfill's explicit "sync" action can still push it. */
export const MAX_AUTO_SYNC_ATTEMPTS = 10

const RETRYABLE: ConversationSyncState[] = ['pending', 'posting', 'failed', 'unconfirmed']

// POSTs in flight in THIS process — the one case where a 'posting' row is not a
// crash leftover. Everything found 'posting' outside this set is recovered as
// 'unconfirmed' (the app died mid-POST: ambiguous by definition).
const inFlight = new Set<string>()

/** Classify an axios failure for the outbox: an HTTP error RESPONSE proves the
 * server did not create the conversation (→ definite, safe to re-post); no
 * response (timeout / connection drop) is ambiguous. */
function classifyPostError(e: unknown): SyncFailure {
  if (axios.isAxiosError(e)) {
    if (e.response) {
      const detail = typeof e.response.data?.detail === 'string' ? ` ${e.response.data.detail}` : ''
      return { ambiguous: false, message: `HTTP ${e.response.status}${detail}`.slice(0, 300) }
    }
    return { ambiguous: true, message: e.message || 'network error' }
  }
  return { ambiguous: true, message: e instanceof Error ? e.message : String(e) }
}

async function postFromSegments(req: FromSegmentsRequest): Promise<{ id: string }> {
  let id: string | undefined
  try {
    const r = await omiApi.post<{ id?: string }>(FROM_SEGMENTS_PATH, req)
    id = r.data?.id
  } catch (e) {
    throw classifyPostError(e)
  }
  // A 2xx without an id: the server most likely created something → ambiguous.
  if (!id) throw { ambiguous: true, message: 'from-segments returned no conversation id' } satisfies SyncFailure
  return { id }
}

async function listRecentCloud(): Promise<CloudConversationLite[]> {
  const r = await omiApi.get<CloudConversationLite[]>('/v1/conversations', {
    params: { limit: 30, offset: 0 }
  })
  return Array.isArray(r.data) ? r.data : []
}

/** True when this local row belongs to (or could enter) the sync pipeline. */
export function isAwaitingSync(c: LocalConversation): boolean {
  return RETRYABLE.includes(c.syncState ?? 'local_only') && (c.segments?.length ?? 0) > 0
}

/**
 * Drive one local conversation through the outbox against the real backend.
 * Returns null when it's already being synced by this process.
 */
export async function syncLocalConversation(c: LocalConversation): Promise<SyncOutcome | null> {
  if (inFlight.has(c.id)) return null
  let state = c.syncState ?? 'local_only'
  inFlight.add(c.id)
  try {
    if (state === 'posting') {
      // Crash recovery (see inFlight note above).
      await window.omi.updateLocalConversationSync(c.id, {
        syncState: 'unconfirmed',
        syncError: 'recovered: app closed during a previous post'
      })
      state = 'unconfirmed'
    }
    return await syncConversation(
      {
        id: c.id,
        startedAt: c.startedAt,
        endedAt: c.endedAt,
        segments: c.segments ?? [],
        syncState: state,
        cloudId: c.cloudId
      },
      {
        post: postFromSegments,
        listRecent: listRecentCloud,
        persist: (id, patch) => window.omi.updateLocalConversationSync(id, patch)
      },
      getPreferences().language
    )
  } finally {
    inFlight.delete(c.id)
  }
}

// Opportunistic retry throttle: at most one pass per minute (a Conversations
// mount triggers it; without the throttle every navigation would re-poke the API).
const RETRY_PASS_MIN_INTERVAL_MS = 60_000
let lastRetryPassAt = 0

/**
 * Retry every local row still awaiting sync (serially — the unconfirmed dedupe
 * must see the previous row's outcome in the cloud list). Returns true when at
 * least one row reached 'done' so the caller can refresh the cloud list.
 */
export async function retryUnsyncedConversations(locals: LocalConversation[], now = Date.now()): Promise<boolean> {
  if (now - lastRetryPassAt < RETRY_PASS_MIN_INTERVAL_MS) return false
  lastRetryPassAt = now
  let anyDone = false
  for (const c of locals) {
    if (!isAwaitingSync(c)) continue
    if ((c.syncAttempts ?? 0) >= MAX_AUTO_SYNC_ATTEMPTS) continue
    try {
      const out = await syncLocalConversation(c)
      if (out?.status === 'done') anyDone = true
    } catch (e) {
      console.warn('[conv-sync] retry failed for', c.id, e)
    }
  }
  return anyDone
}

/** Test hook: reset the throttle (module state persists across tests). */
export function __resetRetryThrottle(): void {
  lastRetryPassAt = 0
}
