// Persisting an extracted memory: one `memories` row locally, PLUS a dual-write
// to the backend `POST /v3/memories` — exactly Mac's two writes
// (`saveMemoryToSQLite` + `syncMemoryToBackend`). The local row is the source of
// truth; a sync failure is fail-open (the row is never lost).
//
// The epoch guard is the load-bearing safety property (borrowed from
// focus/persist.ts): a memory formed under user A must never be written after A
// signs out and B signs in. The caller pins the epoch BEFORE the (long) Gemini
// call; here it is re-read immediately before each write with NO await in
// between, so a session change during extraction cannot slip a departed user's
// memory into the next user's DB or account.
import { net } from 'electron'
import { getAbortSignal, getBackendSession, getSessionEpoch } from '../core/session'
import { insertMemory, markMemorySynced } from '../../ipc/db'
import type { MemoryCategory } from '../../../shared/types'

const REQUEST_TIMEOUT_MS = 15_000

/** What the caller hands us to persist (already confidence-gated + hard-capped). */
export type MemoryToPersist = {
  content: string
  category: MemoryCategory
  sourceApp: string
  contextSummary: string
  /** Stored locally AND sent to the backend — Mac §4 passes windowTitle to
   *  createMemory (unlike Focus, which withholds the title). Faithful to Mac. */
  windowTitle: string | null
  confidence: number
  /** The rewind_frames.id the memory came from (null if unknown). */
  screenshotId: number | null
  createdAt: number
}

/** POST the memory to `/v3/memories`, then stamp the local row synced. A sync
 *  failure keeps the local row (fail-open, degraded) — it is never lost. */
async function syncToBackend(
  rowId: number,
  mem: MemoryToPersist,
  sessionEpoch: number
): Promise<void> {
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
        content: mem.content,
        visibility: 'private',
        category: mem.category,
        confidence: mem.confidence,
        source_app: mem.sourceApp,
        context_summary: mem.contextSummary,
        window_title: mem.windowTitle ?? '',
        // Windows Focus/Insight convention (Mac's MemoryAssistant omits `source`);
        // included so all three desktop assistants tag their memories 'desktop'.
        source: 'desktop'
      }),
      signal: ctrl.signal
    })
    if (!res.ok) {
      console.warn(`[memory] sync HTTP ${res.status}`)
      return
    }
    const created = (await res.json()) as { id?: string }
    // Re-check the epoch before touching the DB: the sync ran across an await, so
    // the session could have changed. Marking a row synced belongs to whoever is
    // signed in NOW. No await between check and write.
    if (getSessionEpoch() !== sessionEpoch) return
    if (created?.id) markMemorySynced(rowId, created.id)
  } catch (e) {
    console.warn('[memory] sync failed:', e instanceof Error ? e.name : 'Error')
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/**
 * Persist one memory: local row + fire-and-forget backend dual-write. Returns the
 * new row id, or null when the session changed between the caller pinning
 * `sessionEpoch` (before the Gemini call) and this write — in which case the
 * memory is dropped rather than written into the wrong user's data.
 */
export function persistMemory(mem: MemoryToPersist, sessionEpoch: number): number | null {
  // The guard: the epoch must still match the one the memory was formed under.
  // Nothing is awaited between this check and insertMemory, so a concurrent
  // sign-out cannot race in between.
  if (getSessionEpoch() !== sessionEpoch) return null

  const rowId = insertMemory({
    content: mem.content,
    category: mem.category,
    sourceApp: mem.sourceApp,
    windowTitle: mem.windowTitle ?? '',
    contextSummary: mem.contextSummary,
    confidence: mem.confidence,
    screenshotId: mem.screenshotId,
    backendSynced: false,
    createdAt: mem.createdAt
  })

  void syncToBackend(rowId, mem, sessionEpoch)
  return rowId
}
