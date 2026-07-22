// Persisting an insight: one local `insights` row (the UI cache + the dedupe
// source the next prompt reads back) PLUS a fire-and-forget dual-write to the
// backend memories store — Mac's `saveInsightToSQLite` + `syncInsightToBackend`.
//
// Mac's memory shape: content = the advice text, backend category `.interesting`
// (differs from the local table), tags ["tips", <category>]. The local `insights`
// table has no synced/backend-id column, so there is nothing to stamp on success
// — a failed sync just leaves the local row (fail-open, degraded), never lost.
//
// The EPOCH GUARD is the load-bearing safety property (borrowed from
// focus/persist.ts): the caller pins the epoch BEFORE the long Gemini pipeline;
// here it is re-read immediately before the local write AND again before the
// network sync, with NO await in between, so an insight formed under user A is
// never written into user B's DB or account after a sign-out/refresh.
import { net } from 'electron'
import { getAbortSignal, getBackendSession, getSessionEpoch } from '../core/session'
import { insertInsight } from '../../ipc/db'
import type { InsightPayload } from '../../../shared/types'
import type { ExtractedInsight } from './models'

const REQUEST_TIMEOUT_MS = 15_000

/** ExtractedInsight → the InsightPayload shape the toast + local table use. The
 *  notification body prefers the short headline, falling back to the advice. */
export function toPayload(insight: ExtractedInsight): InsightPayload {
  return {
    headline: insight.headline?.trim() || insight.advice,
    advice: insight.advice,
    reasoning: insight.reasoning ?? '',
    category: insight.category,
    sourceApp: insight.sourceApp,
    confidence: insight.confidence
  }
}

/** POST the insight as a backend memory (Mac's syncInsightToBackend). Best-effort:
 *  a failure keeps the local row. `sessionEpoch` is re-checked right before the
 *  request so a sign-out mid-pipeline drops the outbound write. */
async function syncToBackend(payload: InsightPayload, sessionEpoch: number): Promise<void> {
  if (getSessionEpoch() !== sessionEpoch) return
  const session = getBackendSession()
  if (!session) return
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await net.fetch(`${session.apiBase}/v3/memories`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        content: payload.advice,
        // Mac's backend category for an insight is `.interesting` (distinct from
        // the local table's own categorization).
        category: 'interesting',
        source: 'desktop',
        tags: ['tips', payload.category]
      }),
      signal: ctrl.signal
    })
    if (!res.ok) console.warn(`[insight] memory sync HTTP ${res.status}`)
  } catch (e) {
    console.warn('[insight] memory sync failed:', e instanceof Error ? e.name : 'Error')
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/**
 * Persist one insight: local row + fire-and-forget backend memory. Returns the
 * new row id, or null when the session changed between the caller pinning
 * `sessionEpoch` (before the Gemini pipeline) and this write — in which case the
 * insight is dropped rather than written into the wrong user's data.
 */
export function persistInsight(insight: ExtractedInsight, sessionEpoch: number): number | null {
  // The guard: the epoch must still match. Nothing is awaited between here and the
  // insert, so a concurrent sign-out cannot race in between.
  if (getSessionEpoch() !== sessionEpoch) return null

  const payload = toPayload(insight)
  const rowId = insertInsight(payload)
  void syncToBackend(payload, sessionEpoch)
  return rowId
}
