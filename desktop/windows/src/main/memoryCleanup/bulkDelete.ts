// Pure helpers for the bulk memory-delete job. The HTTP loop lives in the IPC
// handler (ipc/memoryCleanup.ts); these decision functions are unit-tested.

export type DeleteOutcome = 'ok' | 'gone' | 'retry' | 'fail'

// Classify a DELETE /v3/memories/:id response.
//  - 2xx        -> ok    (deleted)
//  - 404        -> gone  (already deleted; idempotent success, not a failure)
//  - 429/5xx    -> retry (rate-limited / transient)
//  - everything else (401 expired token, 400, …) -> fail (don't spin on it)
export function classifyStatus(status: number): DeleteOutcome {
  if (status >= 200 && status < 300) return 'ok'
  if (status === 404) return 'gone'
  if (status === 429 || (status >= 500 && status < 600)) return 'retry'
  return 'fail'
}

// Milliseconds to wait before retry `attempt` (1-based). Honors a numeric
// Retry-After (seconds) header when the server sends one; otherwise exponential
// backoff capped at 16s with jitter so a fleet of workers doesn't resynchronize.
export function backoffMs(attempt: number, retryAfter?: string | null): number {
  const ra = Number(retryAfter)
  if (Number.isFinite(ra) && ra > 0) return Math.min(ra * 1000, 60_000)
  const base = Math.min(1000 * 2 ** Math.max(0, attempt - 1), 16_000)
  return base + Math.floor(Math.random() * 400)
}
