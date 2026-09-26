import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'
import type { MemoryReadView } from './memoriesCache'

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
export type MemoriesResponse = { data: unknown; headers?: Record<string, unknown> }

export type FetchMemoriesOptions = {
  /** Optional server-side temporal view. Omit for legacy/stable semantics. */
  view?: MemoryReadView
  /** Route used by the explicit history reader when the caller needs ledger rows. */
  path?: '/v3/memories' | '/v3/memories/ledger-history'
}

export const MEMORY_BELIEF_ENABLED_HEADER = 'x-omi-memory-belief-enabled'
export const MEMORY_NEXT_CURSOR_HEADER = 'x-omi-memory-next-cursor'
export const MEMORY_LIST_TRUNCATED_HEADER = 'x-omi-list-truncated'
export const MEMORY_TRUNCATED_MESSAGE =
  'Memory list was truncated by the server read budget; result may be incomplete'

function headerValue(
  headers: Record<string, unknown> | undefined,
  name: string
): string | undefined {
  if (!headers) return undefined
  const wanted = name.toLowerCase()
  const entry = Object.entries(headers).find(([key]) => key.toLowerCase() === wanted)?.[1]
  return typeof entry === 'string' && entry.trim() ? entry.trim() : undefined
}

export function beliefCapabilityFromResponse(response: MemoriesResponse): boolean | null {
  const value = headerValue(response.headers, MEMORY_BELIEF_ENABLED_HEADER)?.toLowerCase()
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

export function nextMemoryCursor(response: MemoriesResponse): string | undefined {
  return headerValue(response.headers, MEMORY_NEXT_CURSOR_HEADER)
}

export function listTruncatedFromResponse(response: MemoriesResponse): boolean {
  return headerValue(response.headers, MEMORY_LIST_TRUNCATED_HEADER)?.toLowerCase() === 'true'
}

// Page through every memory. GET /v3/memories clamps `limit` to at most 500
// (no first-page 5000 expansion — that caused prod GET 504s). Request the
// server max page on every call and advance `offset` by items actually received.
// Dedupes by id; stops on empty page or zero new ids; throws when the final
// response was cut short by the server's read budget (X-Omi-List-Truncated).
const MEMORIES_PAGE_LIMIT = 500
const MAX_MEMORY_PAGES = 10_000
//
// `onResponse` fires for every raw page response so a caller (the Memories page)
// can read capability headers off the first page — e.g.
// X-Omi-Memory-Canonical-Lifecycle-Exposed, which gates the tier/device filters
// — without a second request. It is the single source of truth for "fetch every
// memory": the display hook (useMemories) and the bulk export/purge paths all go
// through it, so the pagination contract can never drift between them again.
export async function fetchAllMemoriesPaged(
  onResponse?: (res: MemoriesResponse) => void,
  options: FetchMemoriesOptions = {}
): Promise<Memory[]> {
  const byId = new Map<string, Memory>()
  const path = options.path ?? '/v3/memories'
  let offset = 0
  let cursor: string | undefined
  let pageCount = 0
  while (pageCount < MAX_MEMORY_PAGES) {
    const params: Record<string, string | number> = { limit: MEMORIES_PAGE_LIMIT }
    if (options.view && path === '/v3/memories') params.view = options.view
    if (cursor) params.cursor = cursor
    else params.offset = offset
    const r = await omiApi.get(path, { params })
    onResponse?.(r)
    const nextCursor = nextMemoryCursor(r)
    const lastTruncated = listTruncatedFromResponse(r)
    const page = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
    pageCount++
    let added = 0
    for (const m of page) {
      if (m.id && !byId.has(m.id)) {
        byId.set(m.id, m)
        added++
      }
    }
    // A temporal view may filter an entire physical page. The server's cursor
    // still advances in that case, so do not stop on an empty page while a
    // continuation cursor is present.
    if (nextCursor) {
      if (nextCursor === cursor) {
        // An unchanged cursor means the server cannot continue (budget spent);
        // with the truncated flag set that must not masquerade as a complete list.
        if (lastTruncated) throw new Error(MEMORY_TRUNCATED_MESSAGE)
        break
      }
      cursor = nextCursor
      continue
    }
    if (page.length === 0 || added === 0) {
      // Only the LAST response's flag matters: in offset mode a truncated page
      // still advances by rows received, so a later complete page recovers and
      // the final empty page ends the walk cleanly.
      if (lastTruncated) throw new Error(MEMORY_TRUNCATED_MESSAGE)
      break
    }
    offset += page.length
  }
  if (pageCount >= MAX_MEMORY_PAGES) {
    throw new Error(
      'Memory pagination exceeded the client safety bound; resume with a server cursor'
    )
  }
  return [...byId.values()]
}

// Convenience wrapper for callers that only need the full list (export/purge).
export function fetchAllMemories(options?: FetchMemoriesOptions): Promise<Memory[]> {
  return fetchAllMemoriesPaged(undefined, options)
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
  for (let i = 0; i < ids.length; i++) {
    const id = ids[i]
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
    // Only pace before the *next* request. After the last id there is nothing
    // left to space out, so serving this wait would just delay the caller
    // (e.g. Memories.tsx's setDeleting(false) / completion toast) by ~1.1s.
    if (i < ids.length - 1) {
      await waitInterruptible(1100, shouldStop) // space out consecutive deletes; Stop skips the wait
    }
  }
  return { deleted, failed, firstError }
}
