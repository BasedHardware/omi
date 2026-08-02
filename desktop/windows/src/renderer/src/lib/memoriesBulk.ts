import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Sleep in short slices, returning as soon as shouldStop() flips. A single
// `await sleep(retryAfterMs)` is unobservable, so a Stop pressed during a pause
// cannot take effect until the whole wait has elapsed. Callers with no
// cancellation get the original single timer, unsliced.
const STOP_POLL_MS = 250
async function waitInterruptible(ms: number, shouldStop?: () => boolean): Promise<void> {
  if (!shouldStop) return sleep(ms)
  for (let waited = 0; waited < ms; waited += STOP_POLL_MS) {
    if (shouldStop()) return
    await sleep(Math.min(STOP_POLL_MS, ms - waited))
  }
}

// A raw axios response, narrowed to just what the pager's onResponse hook reads
// (headers) — avoids coupling this module to the full axios type surface.
type MemoriesResponse = { data: unknown; headers?: Record<string, unknown> }

// Page through every memory. GET /v3/memories clamps `limit` to at most 500
// (no first-page 5000 expansion — that caused prod GET 504s). Request the
// server max page on every call and advance `offset` by items actually received.
// Dedupes by id; stops on empty page or zero new ids.
const MEMORIES_PAGE_LIMIT = 500
//
// `onResponse` fires for every raw page response so a caller (the Memories page)
// can read capability headers off the first page — e.g.
// X-Omi-Memory-Canonical-Lifecycle-Exposed, which gates the tier/device filters
// — without a second request. It is the single source of truth for "fetch every
// memory": the display hook (useMemories) and the bulk export/purge paths all go
// through it, so the pagination contract can never drift between them again.
export async function fetchAllMemoriesPaged(
  onResponse?: (res: MemoriesResponse) => void
): Promise<Memory[]> {
  const byId = new Map<string, Memory>()
  let offset = 0
  while (offset < 100_000) {
    const r = await omiApi.get('/v3/memories', { params: { limit: MEMORIES_PAGE_LIMIT, offset } })
    onResponse?.(r)
    const page = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
    if (page.length === 0) break
    let added = 0
    for (const m of page) {
      if (m.id && !byId.has(m.id)) {
        byId.set(m.id, m)
        added++
      }
    }
    if (added === 0) break
    offset += page.length
  }
  return [...byId.values()]
}

// Convenience wrapper for callers that only need the full list (export/purge).
export function fetchAllMemories(): Promise<Memory[]> {
  return fetchAllMemoriesPaged()
}

// Cap aligned with the backend's MEMORIES_BATCH_MAX (backend/routers/memories.py)
// so a chunk can never be rejected for exceeding the server's per-request limit.
export const MEMORIES_IMPORT_BATCH_SIZE = 100

export type BatchImportTally = { ok: number; failed: number; firstError?: string }

// Send memory contents through POST /v3/memories/batch in chunks of at most
// MEMORIES_IMPORT_BATCH_SIZE, one request per chunk, sequentially. Replaces the
// old one-POST-per-memory fan-out (up to hundreds of requests for a large
// import), which could blow through the per-Authorization rate limit and
// collaterally 429 unrelated chat/sync/goals calls for the same user.
export async function postMemoriesBatched(contents: string[]): Promise<BatchImportTally> {
  let ok = 0
  let failed = 0
  let firstError: string | undefined
  for (let i = 0; i < contents.length; i += MEMORIES_IMPORT_BATCH_SIZE) {
    const chunk = contents.slice(i, i + MEMORIES_IMPORT_BATCH_SIZE)
    try {
      const r = await omiApi.post('/v3/memories/batch', {
        memories: chunk.map((content) => ({ content }))
      })
      ok += r.data?.created_count ?? chunk.length
    } catch (e) {
      const msg =
        (e as { response?: { status?: number; data?: { detail?: string } }; message: string })
          .response?.data?.detail ??
        (e as { response?: { status?: number } }).response?.status?.toString() ??
        (e as Error).message
      if (!firstError) firstError = msg
      failed += chunk.length
    }
  }
  return { ok, failed, firstError }
}

export type BulkDeleteTally = { deleted: number; failed: number; firstError?: string }

// Delete memories by id, paced under the server's 60-per-hour delete cap: one at
// a time at ~1.1s, waiting out 429s (honoring Retry-After) and retrying the same
// id rather than failing. 404 = already gone (idempotent). `onResult` fires after
// each id so the UI can drop the row and show progress. `shouldStop` is
// rechecked after every wait, rate-limit pauses included. An id cancelled
// mid-retry counts as neither deleted nor failed and fires no `onResult`,
// because it still exists.
export async function deleteMemoriesPaced(
  ids: string[],
  onResult: (id: string, ok: boolean, tally: { deleted: number; failed: number }) => void,
  shouldStop?: () => boolean
): Promise<BulkDeleteTally> {
  let deleted = 0
  let failed = 0
  let firstError: string | undefined
  for (const id of ids) {
    if (shouldStop?.()) break
    let ok = false
    let stopped = false
    for (let attempt = 0; attempt < 30; attempt++) {
      try {
        // __noRetry: this loop owns 429 handling, so the axios interceptor's
        // short backoff doesn't fight the hourly rate window.
        await omiApi.delete(`/v3/memories/${id}`, { ...({ __noRetry: true } as object) })
        ok = true
        break
      } catch (e) {
        const resp = (e as { response?: { status?: number; headers?: Record<string, string> } })
          .response
        const status = resp?.status
        if (status === 404) {
          ok = true // already gone
          break
        }
        if (status === 429) {
          const ra = Number(resp?.headers?.['retry-after'])
          await waitInterruptible(
            Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(3000 * 1.6 ** attempt, 60_000),
            shouldStop
          )
          // Without this recheck the pause ends and the retry deletes one more
          // memory after the user already asked to stop.
          if (shouldStop?.()) {
            stopped = true
            break
          }
          continue
        }
        if (!firstError) firstError = status ? `HTTP ${status}` : (e as Error).message
        break
      }
    }
    if (stopped) break // cancelled mid-retry: neither deleted nor failed
    if (ok) deleted++
    else failed++
    onResult(id, ok, { deleted, failed })
    await waitInterruptible(1100, shouldStop) // stay under ~60/hour; Stop skips the tail
  }
  return { deleted, failed, firstError }
}
