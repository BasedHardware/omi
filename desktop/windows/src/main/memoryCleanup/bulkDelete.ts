// Pure helpers for the bulk memory-delete job. The IPC handler
// (ipc/memoryCleanup.ts) supplies Electron's net.fetch; these functions are
// unit-tested without Electron.

export type DeleteOutcome = 'ok' | 'gone' | 'retry' | 'fail'

export const MEMORIES_DELETE_BATCH_SIZE = 100
export const MAX_ATTEMPTS = 6
export const REQUEST_TIMEOUT_MS = 15_000

export type BulkDeleteArgs = { token: string; ids: string[] }
export type BulkDeleteResult = { deleted: number; failed: number; firstError?: string }

export type BulkDeleteResponse = {
  status: number
  headers: { get(name: string): string | null }
  text(): Promise<string>
}

export type BulkDeleteFetch = (
  url: string,
  init: {
    method: string
    headers: Record<string, string>
    body?: string
    signal?: AbortSignal
  }
) => Promise<BulkDeleteResponse>

export type BulkDeleteHooks = {
  sleep?: (ms: number) => Promise<void>
  onProgress?: (state: { deleted: number; failed: number; total: number; done: boolean }) => void
}

// Classify a DELETE /v3/memories response.
//  - 2xx        -> ok    (deleted)
//  - 404        -> gone  (already deleted; idempotent success, not a failure)
//  - 409        -> retry (account destructive-operation gate busy; honor Retry-After)
//  - 429/5xx    -> retry (rate-limited / transient)
//  - everything else (401 expired token, 400, …) -> fail (don't spin on it)
export function classifyStatus(status: number): DeleteOutcome {
  if (status >= 200 && status < 300) return 'ok'
  if (status === 404) return 'gone'
  if (status === 409 || status === 429 || (status >= 500 && status < 600)) return 'retry'
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

const defaultSleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

type AttemptResult = { outcome: DeleteOutcome; reason?: string }

async function requestWithRetry(
  fetchImpl: BulkDeleteFetch,
  url: string,
  init: { method: string; headers: Record<string, string>; body?: string },
  sleep: (ms: number) => Promise<void>
): Promise<AttemptResult> {
  let lastReason = ''
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
    let outcome: DeleteOutcome
    let retryAfter: string | null = null
    try {
      const res = await fetchImpl(url, { ...init, signal: ctrl.signal })
      outcome = classifyStatus(res.status)
      retryAfter = res.headers.get('retry-after')
      if (outcome !== 'ok' && outcome !== 'gone') {
        const body = await res.text().catch(() => '')
        lastReason = `HTTP ${res.status} ${body.slice(0, 160)}`.trim()
      }
    } catch (e) {
      outcome = 'retry'
      lastReason = `network: ${(e as Error).message}`
    } finally {
      clearTimeout(timer)
    }
    if (outcome === 'ok' || outcome === 'gone') return { outcome }
    if (outcome === 'fail') return { outcome, reason: lastReason }
    if (attempt < MAX_ATTEMPTS) await sleep(backoffMs(attempt, retryAfter))
  }
  return { outcome: 'fail', reason: lastReason }
}

function authHeaders(token: string, jsonBody = false): Record<string, string> {
  return jsonBody
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { Authorization: `Bearer ${token}` }
}

// Drain ids through DELETE /v3/memories/batch in chunks of ≤100, sequentially.
// The account destructive-operation gate is exclusive per uid, so a 4-wide
// single-delete fan-out collides with itself. One batch request holds the gate
// once for the whole chunk. 404 on a batch (some id already gone) is bisected
// recursively so only genuinely stale ids reach the single-delete route.
export async function bulkDeleteMemories(
  fetchImpl: BulkDeleteFetch,
  baseURL: string,
  args: BulkDeleteArgs,
  hooks: BulkDeleteHooks = {}
): Promise<BulkDeleteResult> {
  const sleep = hooks.sleep ?? defaultSleep
  const ids = [...new Set(args.ids)]
  let deleted = 0
  let failed = 0
  let firstError = ''

  const emit = (done = false): void => {
    hooks.onProgress?.({ deleted, failed, total: ids.length, done })
  }

  const noteFail = (reason?: string, count = 1): void => {
    failed += count
    if (!firstError && reason) firstError = reason
  }

  const deleteOne = async (id: string): Promise<void> => {
    const result = await requestWithRetry(
      fetchImpl,
      `${baseURL}/v3/memories/${encodeURIComponent(id)}`,
      { method: 'DELETE', headers: authHeaders(args.token) },
      sleep
    )
    if (result.outcome === 'ok' || result.outcome === 'gone') deleted++
    else noteFail(result.reason)
  }

  // The server rejects a whole batch when any id is already gone (all-or-nothing
  // validation -> 404). Bisect instead of falling back to per-id deletes: a
  // chunk that 404s with more than one id is split in half and each half is
  // retried as a batch, so only ids that are individually stale ever reach the
  // single-delete route. This keeps large cleanups off the 60-per-hour
  // per-UID single-delete limiter (#12707 review).
  const deleteChunk = async (chunk: string[]): Promise<void> => {
    if (chunk.length === 0) return
    const result = await requestWithRetry(
      fetchImpl,
      `${baseURL}/v3/memories/batch`,
      {
        method: 'DELETE',
        headers: authHeaders(args.token, true),
        body: JSON.stringify({ memory_ids: chunk })
      },
      sleep
    )
    if (result.outcome === 'ok') {
      deleted += chunk.length
      return
    }
    if (result.outcome === 'gone') {
      if (chunk.length === 1) {
        // The lone id in the chunk is the stale one; a single delete resolves
        // it idempotently (404 gone counts as deleted).
        await deleteOne(chunk[0])
        return
      }
      const mid = Math.floor(chunk.length / 2)
      await deleteChunk(chunk.slice(0, mid))
      await deleteChunk(chunk.slice(mid))
      return
    }
    noteFail(result.reason, chunk.length)
  }

  for (let i = 0; i < ids.length; i += MEMORIES_DELETE_BATCH_SIZE) {
    await deleteChunk(ids.slice(i, i + MEMORIES_DELETE_BATCH_SIZE))
    emit()
  }
  emit(true)
  return { deleted, failed, firstError: firstError || undefined }
}
