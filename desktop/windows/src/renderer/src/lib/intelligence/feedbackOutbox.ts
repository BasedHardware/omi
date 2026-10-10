// Durable feedback outbox for the What Matters Now loop (mac parity:
// DashboardIntelligenceStore's PendingDashboardFeedback queue). Feedback is
// written ahead of the POST, keyed by its idempotency key, so a failed or
// interrupted send survives restarts and replays on the next load. The same
// key overwrites its entry rather than duplicating it, which is also the
// in-flight dedup: a retried action reuses its deterministic key.
//
// Semantics ported verbatim from mac:
// - storage key `whatMattersNowFeedbackOutbox.v1.<ownerId>`, per-owner scoped;
// - entries carry the account generation they were minted under, and entries
//   whose generation no longer matches the live control are DISCARDED, never
//   sent (a superseded generation's feedback is meaningless to the server);
// - replay is one sequential pass with no backoff or attempt counter; failures
//   leave the entry for the next load;
// - pending later/dismiss entries suppress matching projection rows until the
//   server has acknowledged them (see matchesPendingSuppression).
import { getCacheUid } from '../persistentCache'
import type { FeedbackCreateBody } from './wireTypes'

export type PendingFeedback = {
  request: FeedbackCreateBody
  idempotencyKey: string
  accountGeneration: number
}

const OUTBOX_KEY_PREFIX = 'whatMattersNowFeedbackOutbox.v1.'

export function outboxOwnerId(): string {
  return getCacheUid() ?? 'signed-out'
}

function storageKey(ownerId: string): string {
  return `${OUTBOX_KEY_PREFIX}${ownerId}`
}

export function loadOutbox(ownerId: string = outboxOwnerId()): PendingFeedback[] {
  try {
    const raw = window.localStorage.getItem(storageKey(ownerId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const entries: PendingFeedback[] = []
    for (const item of parsed) {
      const e = item as Partial<PendingFeedback> | null
      const r = e?.request as Partial<FeedbackCreateBody> | null | undefined
      if (
        e &&
        typeof e.idempotencyKey === 'string' &&
        typeof e.accountGeneration === 'number' &&
        r &&
        typeof r === 'object' &&
        typeof r.action === 'string' &&
        typeof r.subject_kind === 'string' &&
        typeof r.subject_id === 'string' &&
        typeof r.intervention_id === 'string'
      ) {
        entries.push(e as PendingFeedback)
      }
      // Malformed persisted entries are dropped here rather than replayed
      // forever; the save below rewrites the pruned list.
    }
    return entries
  } catch {
    return []
  }
}

function saveOutbox(entries: PendingFeedback[], ownerId: string): void {
  try {
    window.localStorage.setItem(storageKey(ownerId), JSON.stringify(entries))
  } catch {
    // Quota failure degrades to at-most-once delivery for this entry.
  }
}

/** Write-ahead enqueue: same idempotency key overwrites its previous entry. */
export function enqueueFeedback(entry: PendingFeedback, ownerId: string = outboxOwnerId()): void {
  const entries = loadOutbox(ownerId).filter((e) => e.idempotencyKey !== entry.idempotencyKey)
  entries.push(entry)
  saveOutbox(entries, ownerId)
}

export function removeFeedback(idempotencyKey: string, ownerId: string = outboxOwnerId()): void {
  saveOutbox(
    loadOutbox(ownerId).filter((e) => e.idempotencyKey !== idempotencyKey),
    ownerId
  )
}

/** Drop entries minted under a superseded account generation. They are never
 *  sent: the server's generation fence would 409 them and the feedback no
 *  longer describes live state. Returns the surviving entries. */
export function purgeMismatchedGeneration(
  liveGeneration: number,
  ownerId: string = outboxOwnerId()
): PendingFeedback[] {
  const survivors = loadOutbox(ownerId).filter((e) => e.accountGeneration === liveGeneration)
  saveOutbox(survivors, ownerId)
  return survivors
}

/** A projection row is suppressed while a pending later/dismiss entry matches it
 *  by intervention id OR by (feedback subject kind + id) — the row was acted on
 *  and the server just does not know yet. Once the POST succeeds the entry is
 *  removed and server authority resumes. */
export function matchesPendingSuppression(
  pending: PendingFeedback[],
  row: { interventionId: string; feedbackSubjectKind: string; feedbackSubjectId: string }
): boolean {
  return pending.some(
    (e) =>
      (e.request.action === 'later' || e.request.action === 'dismiss') &&
      (e.request.intervention_id === row.interventionId ||
        (e.request.subject_kind === row.feedbackSubjectKind &&
          e.request.subject_id === row.feedbackSubjectId))
  )
}

export type FeedbackSender = (entry: PendingFeedback) => Promise<void>

/** One sequential replay pass over the CURRENT outbox. Failures leave their
 *  entry in place; entries enqueued while the pass runs survive it (the final
 *  list is re-read and filtered by succeeded keys, mirroring mac). Returns the
 *  number of entries delivered. */
export async function replayOutbox(
  send: FeedbackSender,
  ownerId: string = outboxOwnerId(),
  scopeCurrent: () => boolean = () => true
): Promise<number> {
  const entries = loadOutbox(ownerId)
  const succeeded = new Set<string>()
  for (const entry of entries) {
    // An account switch mid-pass must not submit the previous owner's
    // feedback under the new session's credentials.
    if (!scopeCurrent()) break
    try {
      await send(entry)
      succeeded.add(entry.idempotencyKey)
    } catch {
      // Sequential, no backoff: the entry stays for the next load.
    }
  }
  if (succeeded.size > 0 && scopeCurrent()) {
    saveOutbox(
      loadOutbox(ownerId).filter((e) => !succeeded.has(e.idempotencyKey)),
      ownerId
    )
  }
  return succeeded.size
}
