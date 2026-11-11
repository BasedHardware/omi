// Polling rules for a conversation that is still being enriched, ported from the
// macOS detail view: re-GET the conversation up to 15 times, 2s apart (30s max),
// stopping early the moment it leaves `processing`.
//
// Backend behavior this is built around (verified): GET /v1/conversations/{id}
// clears the `deferred` flag and kicks off enrichment in the BACKGROUND, then
// returns immediately — so the first response has the transcript but no summary
// or action items yet. Statuses: in_progress | processing | merging | completed |
// failed.
//
// Known backend quirk we must degrade around (server-side fix is out of scope):
// if enrichment FAILS, the backend re-arms `deferred` and force-sets the status
// to `completed`. A failed enrichment therefore looks exactly like a finished one
// with an empty summary. So "stop when status != processing" is the only sound
// stop condition — never "stop when a summary exists", which would spin forever.

export const POLL_INTERVAL_MS = 2000
export const POLL_MAX_ATTEMPTS = 15

/** True while Omi is still generating the summary / action items. */
export function isProcessing(status?: string | null): boolean {
  return status === 'processing'
}

/** Should the detail view show the "Processing conversation…" section? */
export function isEnriching(conv: { status?: string | null; deferred?: boolean }): boolean {
  return isProcessing(conv.status) || conv.deferred === true
}

/**
 * Stop condition for the poll loop. `attempt` is 1-based (the number of polls
 * already issued).
 *
 * Stops when the conversation is no longer processing, or when we have burned
 * all 15 attempts — so the spinner always terminates, even if the backend leaves
 * the conversation wedged in `processing`.
 */
export function shouldStopPolling(status: string | null | undefined, attempt: number): boolean {
  if (!isProcessing(status)) return true
  return attempt >= POLL_MAX_ATTEMPTS
}
