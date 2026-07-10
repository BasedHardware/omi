/**
 * Pure reconcile helpers for the Conversations list: once a cloud conversation
 * matching a locally-synced (or sync-in-flight) row appears, the local row is
 * marked done and hidden so the list never shows the same conversation twice.
 */
import { findCloudMatch, type CloudConversationLite } from './outbox'
import type { LocalConversation } from '../../../../shared/types'

const MATCHABLE = new Set(['pending', 'posting', 'unconfirmed', 'failed'])

/**
 * Local rows whose cloud twin is present in the freshly-fetched cloud list.
 * Matching uses the same started_at/finished_at (+ segment count) rule as the
 * outbox dedupe — these round-trip from our own POST, so a match means OUR
 * conversation landed (possibly via an attempt we never got the response for).
 */
export function findSyncedMatches(
  locals: LocalConversation[],
  cloud: CloudConversationLite[]
): { id: string; cloudId: string }[] {
  const out: { id: string; cloudId: string }[] = []
  for (const c of locals) {
    if (!MATCHABLE.has(c.syncState ?? 'local_only')) continue
    if (!c.segments || c.segments.length === 0) continue
    const match = findCloudMatch(
      { startedAt: c.startedAt, endedAt: c.endedAt, segmentCount: c.segments.length },
      cloud
    )
    if (match) out.push({ id: c.id, cloudId: match })
  }
  return out
}

/**
 * Drop local rows whose cloud twin is IN the given cloud id set. A 'done' row
 * whose twin is not fetched (e.g. cloud request failed, or it fell past the page)
 * stays visible — the local copy is the only thing the user would see.
 */
export function hideSyncedLocals(locals: LocalConversation[], cloudIds: Set<string>): LocalConversation[] {
  return locals.filter((c) => !(c.syncState === 'done' && c.cloudId && cloudIds.has(c.cloudId)))
}
