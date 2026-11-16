// --- Track 3 (AI user profile) ---
// IPC bridge for the backend-owned "about the user" profile. Main reads it
// (GET /v1/users/ai-profile, cached for prompt consumers) and proxies the user's
// refresh / edit / delete; the backend does all generation. The renderer holds
// the Firebase token + base URLs, so it pushes a session (setSession). See
// src/main/assistants/aiUserProfile/service.ts.
//
// Results travel as an AiProfileResult envelope instead of a rejected invoke, so
// the renderer can tell a 402 from a 409 from a 422 without parsing an Electron
// error string.
import { ipcMain, type IpcMainInvokeEvent } from 'electron'
import {
  MAX_PROFILE_CHARS,
  configureAiProfileSession,
  deleteProfile,
  editProfile,
  loadProfile,
  refreshProfile,
  type AiProfileSession
} from '../assistants/aiUserProfile/service'
import type { AiProfileResult, AiUserProfile } from '../../shared/types'

// --- Arg validation (m6, defense-in-depth) ----------------------------------
// The renderer is first-party, but validating at the IPC boundary rejects a
// malformed call early instead of letting a bad shape reach the backend fetch.
function isSession(v: unknown): v is AiProfileSession {
  if (typeof v !== 'object' || v === null) return false
  const s = v as Record<string, unknown>
  return (
    typeof s.apiBase === 'string' &&
    typeof s.desktopApiBase === 'string' &&
    typeof s.token === 'string'
  )
}

export function registerAiUserProfileHandlers(): void {
  // Push/refresh (or clear, on null) the backend session. The renderer calls
  // this on auth + every token refresh.
  ipcMain.handle('aiProfile:setSession', (_e: IpcMainInvokeEvent, session: unknown): void => {
    if (session !== null && !isSession(session)) {
      throw new Error('aiProfile: malformed session')
    }
    configureAiProfileSession(session)
  })

  // Current profile from the backend (drives the Settings card).
  ipcMain.handle(
    'aiProfile:get',
    (): Promise<AiProfileResult<AiUserProfile | null>> => loadProfile()
  )

  // "Generate now / Regenerate": the backend synthesizes synchronously.
  ipcMain.handle(
    'aiProfile:refresh',
    (): Promise<AiProfileResult<AiUserProfile>> => refreshProfile()
  )

  // A user edit, saved as source=user_edit.
  ipcMain.handle(
    'aiProfile:edit',
    (_e: IpcMainInvokeEvent, text: unknown): Promise<AiProfileResult<AiUserProfile>> => {
      if (typeof text !== 'string') throw new Error('aiProfile: text must be a string')
      if (!text.trim() || text.length > MAX_PROFILE_CHARS) {
        return Promise.resolve({ ok: false, code: 'invalid_edit' })
      }
      return editProfile(text)
    }
  )

  ipcMain.handle('aiProfile:delete', (): Promise<AiProfileResult<null>> => deleteProfile())
}
