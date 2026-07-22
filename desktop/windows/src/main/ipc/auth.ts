// Electron wiring for the backend-mediated Google sign-in flow. The actual
// flow (loopback listener, authorize URL, token exchange) lives in
// src/main/auth/googleSignInFlow.ts and is Electron-free; this file supplies
// the browser opener, file logging, and window surfacing.
import { app, ipcMain, shell } from 'electron'
import { appendFileSync } from 'fs'
import { join } from 'path'
import { startGoogleSignIn } from '../auth/googleSignInFlow'
import type { GoogleSignInResult } from '../../shared/types'

// Main-process console.log only reaches the dev-server terminal, which is easy
// to miss. Also append to userData/google-signin.log so a failed field sign-in
// can be traced after the fact (same pattern as integrations/oauth.ts).
function authLog(msg: string, extra?: unknown): void {
  const line = `[${new Date().toISOString()}] ${msg}${extra !== undefined ? ' ' + JSON.stringify(extra) : ''}`
  console.log('[google-signin]', line)
  try {
    appendFileSync(join(app.getPath('userData'), 'google-signin.log'), line + '\n')
  } catch {
    /* best-effort logging only */
  }
}

function apiBase(): string {
  return import.meta.env.VITE_OMI_API_BASE || 'https://api.omi.me'
}

/**
 * Register the auth IPC. `onSignedIn` surfaces the main window after the
 * loopback callback lands (the browser holds foreground focus at that point —
 * see index.ts for the focus-steal implementation).
 */
export function registerAuthHandlers(onSignedIn: () => void): void {
  ipcMain.handle('auth:google:signIn', async (): Promise<GoogleSignInResult> => {
    authLog('sign-in requested')
    const result = await startGoogleSignIn({
      apiBase: apiBase(),
      openExternal: (url) => shell.openExternal(url),
      log: authLog
    })
    if (result.ok) {
      authLog('sign-in complete — surfacing window')
      onSignedIn()
    }
    return result
  })
}
