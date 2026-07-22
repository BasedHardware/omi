// --- Track 3 (AI user profile) ---
// IPC bridge for the once-daily synthesized "about the user" profile. The
// service runs in the main process (better-sqlite3 + backend sync survive
// renderer reloads); the renderer holds the Firebase token + base URLs, so it
// pushes a session (setSession) and drives generation. See
// src/main/assistants/aiUserProfile/service.ts for the token-model rationale.
import { ipcMain, type IpcMainInvokeEvent } from 'electron'
import {
  configureAiProfileSession,
  deleteAll,
  deleteProfile,
  editProfileText,
  generateNow,
  getLatestProfileRecord,
  type AiProfileSession
} from '../assistants/aiUserProfile/service'
import type { AiUserProfileRecord } from '../../shared/types'

// --- Arg validation (m6, defense-in-depth) ----------------------------------
// The renderer is first-party, but validating at the IPC boundary rejects a
// malformed call early (a clear Error over the invoke) instead of letting a bad
// shape reach the backend fetch or the DB writer.
function isSession(v: unknown): v is AiProfileSession {
  if (typeof v !== 'object' || v === null) return false
  const s = v as Record<string, unknown>
  return (
    typeof s.apiBase === 'string' &&
    typeof s.desktopApiBase === 'string' &&
    typeof s.token === 'string'
  )
}

function assertId(id: unknown): asserts id is number {
  if (typeof id !== 'number' || !Number.isInteger(id)) {
    throw new Error('aiProfile: id must be an integer')
  }
}

export function registerAiUserProfileHandlers(): void {
  // Push/refresh (or clear, on null) the backend session so background
  // generation has credentials. The renderer calls this on auth + token refresh.
  ipcMain.handle('aiProfile:setSession', (_e: IpcMainInvokeEvent, session: unknown): void => {
    // null clears the cached session; anything else must be a well-formed one.
    if (session !== null && !isSession(session)) {
      throw new Error('aiProfile: malformed session')
    }
    configureAiProfileSession(session)
  })

  // Generate a profile now (fresh session supplied by the renderer).
  ipcMain.handle(
    'aiProfile:generateNow',
    (_e: IpcMainInvokeEvent, session?: unknown): Promise<AiUserProfileRecord> => {
      // Optional: undefined falls back to the cached session; a provided value
      // must be well-formed.
      if (session !== undefined && !isSession(session)) {
        throw new Error('aiProfile: malformed session')
      }
      return generateNow(session)
    }
  )

  // Latest stored profile RECORD (drives the Settings preview/edit UI, which
  // needs id/date/sources). Downstream grounding uses getLatestProfileText()
  // directly in-process, not this IPC.
  ipcMain.handle('aiProfile:getLatest', (): AiUserProfileRecord | null => getLatestProfileRecord())

  // Manual edit of a stored profile.
  ipcMain.handle(
    'aiProfile:edit',
    (_e: IpcMainInvokeEvent, id: unknown, text: unknown): Promise<void> => {
      assertId(id)
      if (typeof text !== 'string') throw new Error('aiProfile: text must be a string')
      return editProfileText(id, text)
    }
  )

  ipcMain.handle('aiProfile:delete', (_e: IpcMainInvokeEvent, id: unknown): void => {
    assertId(id)
    deleteProfile(id)
  })

  ipcMain.handle('aiProfile:deleteAll', (): void => deleteAll())
}
