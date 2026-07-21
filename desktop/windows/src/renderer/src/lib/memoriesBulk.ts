import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Sleep in short slices, returning early once shouldStop() flips — a Stop
// pressed during a long Retry-After pause takes effect within a slice
// (~250ms) instead of after the full wait.
async function waitInterruptible(ms: number, shouldStop?: () => boolean): Promise<void> {
  const SLICE_MS = 250
  for (let waited = 0; waited < ms; waited += SLICE_MS) {
    if (shouldStop?.()) return
    await sleep(Math.min(SLICE_MS, ms - waited))
  }
}

// Page through every memory. The backend expands the FIRST page (offset=0) to
// 5000 rows regardless of the requested limit, then serves later offsets at
// the clamped limit (backend/routers/memories.py _legacy_get_memories) — so
// the offset must advance by the number of rows actually RETURNED, never by
// the requested page size, or accounts past 5000 memories get duplicate pages
// and a premature stop. Dedupes by id and stops when a page adds nothing new
// (guards a server that ignores `offset`) or comes back shorter than asked
// (the end of the list).
export async function fetchAllMemories(): Promise<Memory[]> {
  const PAGE_LIMIT = 200
  const byId = new Map<string, Memory>()
  let offset = 0
  while (offset < 100_000) {
    const r = await omiApi.get('/v3/memories', { params: { limit: PAGE_LIMIT, offset } })
    const page = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
    let added = 0
    for (const m of page) {
      if (m.id && !byId.has(m.id)) {
        byId.set(m.id, m)
        added++
      }
    }
    if (page.length === 0 || added === 0) break
    offset += page.length
    if (page.length < PAGE_LIMIT) break
  }
  return [...byId.values()]
}

export type BulkDeleteTally = { deleted: number; failed: number; firstError?: string }

// Delete memories by id, paced under the server's 60-per-hour delete cap: one at
// a time at ~1.1s, waiting out 429s (honoring Retry-After) and retrying the same
// id rather than failing. 404 = already gone (idempotent). `onResult` fires after
// each id so the UI can drop the row and show progress. `shouldStop` lets the
// caller cancel; it is rechecked after EVERY wait (rate-limit pauses included,
// which also end early), so a Stop pressed mid-pause never lets one more delete
// out. An id cancelled mid-retry counts as neither deleted nor failed. `onWait`
// reports rate-limit pauses (seconds until the next retry; 0 when the pause
// ends) so progress UI can show them honestly.
export async function deleteMemoriesPaced(
  ids: string[],
  onResult: (id: string, ok: boolean, tally: { deleted: number; failed: number }) => void,
  shouldStop?: () => boolean,
  onWait?: (seconds: number) => void
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
          const waitMs =
            Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(3000 * 1.6 ** attempt, 60_000)
          onWait?.(Math.round(waitMs / 1000))
          await waitInterruptible(waitMs, shouldStop)
          onWait?.(0)
          // Recheck after the wait: without this, a Stop pressed during the
          // pause still let the retry delete one more memory.
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
    if (stopped) break // cancelled mid-retry: this id was neither deleted nor failed
    if (ok) deleted++
    else failed++
    onResult(id, ok, { deleted, failed })
    await waitInterruptible(1100, shouldStop) // stay under ~60/hour; Stop skips the tail
  }
  return { deleted, failed, firstError }
}
