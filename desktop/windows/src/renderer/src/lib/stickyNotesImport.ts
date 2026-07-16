// Shared orchestration for the Windows Sticky Notes → memories import, so the
// Settings → Integrations row and the Hub → Connections panel drive the SAME
// logic (no duplicated read/extract/tag rules). The synthesis prompt lives in
// stickyNotesExtract.ts; this is the read → extract → tagged-write glue that was
// previously inlined in IntegrationsTab.
import { omiApi } from './apiClient'
import { extractNoteMemories } from './stickyNotesExtract'
import type { BatchImportTally } from './memoriesBulk'

export const STICKY_NOTE_TAG = 'sticky_notes/import/note'
export const STICKY_PROFILE_TAG = 'sticky_notes/import/profile'

export type StickyReadOutcome =
  | { status: 'unavailable' }
  | { status: 'error'; error: string }
  // 'no-notes': Sticky Notes present but no note text. 'no-new-memories':
  // extraction ran but produced nothing not already saved. Distinct so callers
  // can message each precisely (Settings has always shown different copy).
  | { status: 'empty'; reason: 'no-notes' | 'no-new-memories' }
  | { status: 'ok'; memories: string[]; profile: string }

/**
 * Read local Sticky Notes and synthesize durable memories from them. Never posts
 * anything — returns the reviewable list so the caller can preview before import.
 * `status` distinguishes the resting states the UI must show distinctly.
 */
export async function readAndExtractStickyNotes(existing: string[]): Promise<StickyReadOutcome> {
  const result = await window.omi.readStickyNotes()
  if (!result.available) return { status: 'unavailable' }
  if (result.error) return { status: 'error', error: result.error }
  if (result.notes.length === 0) return { status: 'empty', reason: 'no-notes' }

  const notesText = result.notes.map((n) => n.text).join('\n\n---\n\n')
  const { memories, profile } = await extractNoteMemories(notesText, existing)
  if (memories.length === 0) return { status: 'empty', reason: 'no-new-memories' }
  return { status: 'ok', memories, profile }
}

/**
 * Write the reviewed sticky-note memories, each tagged with STICKY_NOTE_TAG, plus
 * the profile summary (best-effort, STICKY_PROFILE_TAG). One POST per memory —
 * these lists are short (a handful of notes), unlike the paste importer's batches.
 */
export async function importStickyMemories(
  memories: string[],
  profile: string
): Promise<BatchImportTally> {
  // These lists are short (a handful of notes), so fire the writes concurrently
  // rather than one-at-a-time. firstError keeps array order via the results index.
  const results = await Promise.allSettled(
    memories.map((content) => omiApi.post('/v3/memories', { content, tags: [STICKY_NOTE_TAG] }))
  )
  let ok = 0
  let failed = 0
  let firstError: string | undefined
  for (const r of results) {
    if (r.status === 'fulfilled') {
      ok++
    } else {
      failed++
      if (!firstError) {
        firstError =
          (r.reason as { response?: { data?: { detail?: string } }; message: string }).response
            ?.data?.detail ?? (r.reason as Error).message
      }
    }
  }
  if (profile.trim()) {
    try {
      await omiApi.post('/v3/memories', { content: profile.trim(), tags: [STICKY_PROFILE_TAG] })
    } catch {
      /* profile is best-effort */
    }
  }
  return { ok, failed, firstError }
}
