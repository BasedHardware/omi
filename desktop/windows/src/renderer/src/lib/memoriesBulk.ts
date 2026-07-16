import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// A raw axios response, narrowed to just what the pager's onResponse hook reads
// (headers) — avoids coupling this module to the full axios type surface.
type MemoriesResponse = { data: unknown; headers?: Record<string, unknown> }

// Page through every memory. GET /v3/memories clamps `limit` to at most 5000
// and — on BOTH the legacy and canonical read paths — FORCES limit to 5000
// whenever offset is 0, regardless of the requested limit (see
// _legacy_get_memories and the canonical branch of get_memories in
// backend/routers/memories.py). So the first call here can return up to 5000
// memories even though it asks for 200. Advance `offset` by the number of
// items actually received (not a fixed step) so the next request picks up
// where the server really left off — a fixed +200 step would re-request
// already-seen ids from inside that forced first page and hit the dedup guard
// early, silently truncating anything past the account's first 5000 memories.
// Dedupes by id and stops when a page is empty or adds nothing new — guards
// against a server that ignores `offset` entirely.
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
    const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset } })
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
// each id so the UI can drop the row and show progress. `shouldStop` lets the
// caller cancel between ids.
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
          await sleep(
            Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(3000 * 1.6 ** attempt, 60_000)
          )
          continue
        }
        if (!firstError) firstError = status ? `HTTP ${status}` : (e as Error).message
        break
      }
    }
    if (ok) deleted++
    else failed++
    onResult(id, ok, { deleted, failed })
    await sleep(1100) // stay under ~60/hour
  }
  return { deleted, failed, firstError }
}
