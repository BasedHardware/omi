/**
 * Pure reconcile helpers for the Conversations list: once a cloud conversation
 * matching a locally-synced (or sync-in-flight) row appears, the local row is
 * marked done and hidden so the list never shows the same conversation twice.
 */
import { findCloudMatch, type CloudConversationLite } from './outbox'
import type { ConversationSyncPatch, LocalConversation } from '../../../../shared/types'

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
 * Adopt cloud twins: compute the matches AND persist each 'done' transition
 * (fire-and-forget through the injected persist — IPC → SQLite in the app),
 * returning the locals with the adoption reflected. This is the only adoption
 * write path besides syncConversation's own POST success, kept here so UI
 * components never encode an outbox transition themselves.
 */
export function reconcileSyncedLocals(
  locals: LocalConversation[],
  cloud: CloudConversationLite[],
  persist: (id: string, patch: ConversationSyncPatch) => Promise<void>
): LocalConversation[] {
  const matches = findSyncedMatches(locals, cloud)
  if (matches.length === 0) return locals
  const byId = new Map<string, string>()
  for (const m of matches) {
    byId.set(m.id, m.cloudId)
    void persist(m.id, { syncState: 'done', cloudId: m.cloudId, syncError: null }).catch((e) =>
      console.warn('sync reconcile persist failed:', e)
    )
  }
  return locals.map((c) => (byId.has(c.id) ? { ...c, syncState: 'done', cloudId: byId.get(c.id)! } : c))
}

/**
 * Drop local rows whose cloud twin is IN the given cloud id set. A 'done' row
 * whose twin is not fetched (e.g. cloud request failed, or it fell past the page)
 * stays visible — the local copy is the only thing the user would see.
 */
export function hideSyncedLocals(locals: LocalConversation[], cloudIds: Set<string>): LocalConversation[] {
  return locals.filter((c) => !(c.syncState === 'done' && c.cloudId && cloudIds.has(c.cloudId)))
}
