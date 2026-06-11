import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Page through every memory (server caps a page at 200). Dedupes by id and stops
// if a page adds nothing new — guards against a server that ignores `offset`.
export async function fetchAllMemories(): Promise<Memory[]> {
  const byId = new Map<string, Memory>()
  for (let offset = 0; offset < 100_000; offset += 200) {
    const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset } })
    const page = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
    let added = 0
    for (const m of page) {
      if (m.id && !byId.has(m.id)) {
        byId.set(m.id, m)
        added++
      }
    }
    if (page.length < 200 || added === 0) break
  }
  return [...byId.values()]
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
        const resp = (e as { response?: { status?: number; headers?: Record<string, string> } }).response
        const status = resp?.status
        if (status === 404) {
          ok = true // already gone
          break
        }
        if (status === 429) {
          const ra = Number(resp?.headers?.['retry-after'])
          await sleep(Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(3000 * 1.6 ** attempt, 60_000))
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
