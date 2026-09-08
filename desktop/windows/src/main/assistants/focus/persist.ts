// Persisting a Focus verdict: one focus_sessions row locally, PLUS a dual-write
// to the backend memories store — exactly Mac's two writes
// (`saveFocusSessionToSQLite` + `syncFocusSessionToBackend`).
//
// There is NO `/v1/focus/*` backend endpoint — Mac's `FocusStatsResponse` /
// `CreateFocusSessionRequest` structs are dead code. A focus event reaches the
// backend as an ordinary memory (category `system`), which is what makes focus
// history searchable alongside everything else.
//
// The epoch guard is the load-bearing safety property, borrowed from
// aiUserProfile/orchestrate.ts: a verdict formed under user A must never be
// written after A signs out and B signs in. The caller pins the epoch BEFORE the
// (long) Gemini call; here it is re-read immediately before each write with NO
// await in between, so a session change during the analysis cannot slip a
// departed user's data into the next user's DB or account.
import { net } from 'electron'
import { getAbortSignal, getBackendSession, getSessionEpoch } from '../core/session'
import { insertFocusSession, markFocusSessionSynced } from '../../ipc/db'
import type { ScreenAnalysis } from './models'

const REQUEST_TIMEOUT_MS = 15_000

/** Mac's memory content + tags for a focus event (`saveFocusToMemoriesTable`). */
function memoryContent(a: ScreenAnalysis): string {
  const verb = a.status === 'focused' ? 'Focused' : 'Distracted'
  return `${verb} on ${a.appOrSite}: ${a.description}`
}

function memoryTags(a: ScreenAnalysis): string[] {
  const tags = ['focus', a.status, `app:${a.appOrSite}`]
  if (a.message) tags.push('has-message')
  return tags
}

/** POST the focus event as a generic memory, then stamp the local row synced.
 *  `sessionEpoch` is the epoch the verdict was formed under. A sync failure keeps
 *  the local row (fail-open, degraded) — it is never lost. */
async function syncToBackend(
  rowId: number,
  analysis: ScreenAnalysis,
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
        content: memoryContent(analysis),
        category: 'system',
        source: 'desktop',
        tags: memoryTags(analysis)
      }),
      signal: ctrl.signal
    })
    if (!res.ok) {
      console.warn(`[focus] memory sync HTTP ${res.status}`)
      return
    }
    const created = (await res.json()) as { id?: string }
    // Re-check the epoch before touching the DB: the sync ran across an await, so
    // the session could have changed. Marking a row synced belongs to whoever is
    // signed in NOW, not to a departed session. No await between check and write.
    if (getSessionEpoch() !== sessionEpoch) return
    if (created?.id) markFocusSessionSynced(rowId, created.id)
  } catch (e) {
    console.warn('[focus] memory sync failed:', e instanceof Error ? e.name : 'Error')
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/**
 * Persist one verdict: local row + fire-and-forget backend memory. Returns the
 * new row id, or null when the session changed between the caller pinning
 * `sessionEpoch` (before the Gemini call) and this write — in which case the
 * verdict is dropped rather than written into the wrong user's data.
 *
 * `screenshotId` is the frame's row id as a string (or null); `windowTitle` is
 * stored locally ONLY (it never leaves the device — the synced memory carries
 * `appOrSite`, not the raw title, which could be "Chase — Log in").
 */
export function persistFocusSession(
  analysis: ScreenAnalysis,
  frame: { screenshotId: string | null; windowTitle: string | null; createdAt: number },
  sessionEpoch: number
): number | null {
  // The guard: the epoch must still match the one the verdict was formed under.
  // Nothing is awaited between this check and insertFocusSession, so a concurrent
  // sign-out cannot race in between.
  if (getSessionEpoch() !== sessionEpoch) return null

  const rowId = insertFocusSession({
    screenshotId: frame.screenshotId,
    status: analysis.status,
    appOrSite: analysis.appOrSite,
    description: analysis.description,
    message: analysis.message,
    createdAt: frame.createdAt,
    windowTitle: frame.windowTitle,
    backendSynced: false
  })

  void syncToBackend(rowId, analysis, sessionEpoch)
  return rowId
}
