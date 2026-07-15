// IPC surface for the pi-mono session relay. The renderer holds the only live
// Firebase session on Windows, so it pushes {token, desktopApiBase} here on
// sign-in and on every id-token refresh; main caches it for the pi-mono adapter
// to read at spawn (see codingAgent/piMonoSession.ts).
//
// SECURITY: the payload carries a live Firebase ID token. `configurePiMonoSession`
// validates the shape and never logs the token; this handler must never log the
// payload either.

import { ipcMain } from 'electron'
import { configurePiMonoSession } from '../codingAgent/piMonoSession'
import { ensurePiMonoAdapterRegistered } from '../agentKernel/controlPlane'

/** Registers the `pimono:*` IPC handlers backing the session store. */
export function registerPiMonoHandlers(): void {
  ipcMain.handle('pimono:setSession', (_e, session: unknown): void => {
    configurePiMonoSession(session)
    // Register the managed-cloud pi-mono adapter into the kernel now that a
    // session may be present. Idempotent, and a no-op when signed out (returns
    // false), so the registry stays empty until a real Firebase session exists.
    // DARK: registration only — nothing routes chat to pi-mono until PR-E.
    ensurePiMonoAdapterRegistered()
  })
}
