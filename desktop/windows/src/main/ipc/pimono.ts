// IPC surface for the pi-mono session relay. The renderer holds the only live
// Firebase session on Windows, so it pushes {token, desktopApiBase} here on
// sign-in and on every id-token refresh; main caches it for the pi-mono adapter
// to read at spawn (see codingAgent/piMonoSession.ts).
//
// SECURITY: the payload carries a live Firebase ID token. `configurePiMonoSession`
// validates the shape and never logs the token; this handler must never log the
// payload either.

import { ipcMain } from 'electron'
import { configurePiMonoSession, getPiMonoSession } from '../codingAgent/piMonoSession'
import { ensurePiMonoAdapterRegistered, setControlPlaneOwner } from '../agentKernel/controlPlane'
import { decodeUidFromIdToken } from '../auth/omiAuth'

/** Registers the `pimono:*` IPC handlers backing the session store. */
export function registerPiMonoHandlers(): void {
  ipcMain.handle('pimono:setSession', (_e, session: unknown): void => {
    configurePiMonoSession(session)
    // Wire the control-plane owner to the signed-in user, HOST-DERIVED. The
    // relayed payload carries no uid; we decode it from the Firebase ID token in
    // the now-validated session (getPiMonoSession returns the coerced session, or
    // null when signed out / invalid), so the owner comes from the credential
    // itself — never a renderer-asserted field. This is what scopes every kernel
    // session/surface row (surfaceSession.ts) to the real account instead of the
    // shared DEFAULT_LOCAL_OWNER_ID constant, closing the cross-account read on a
    // shared Windows profile. On sign-out (session === null) it resets to default.
    // An undecodable/forged token decodes to '' → setControlPlaneOwner falls back
    // to the default, which the cold-start gate then refuses (fail closed).
    const current = getPiMonoSession()
    setControlPlaneOwner(current ? decodeUidFromIdToken(current.token) : null)
    // Register the managed-cloud pi-mono adapter into the kernel now that a
    // session may be present. Idempotent, and a no-op when signed out (returns
    // false), so the registry stays empty until a real Firebase session exists.
    // DARK: registration only — nothing routes chat to pi-mono until PR-E.
    ensurePiMonoAdapterRegistered()
  })
}
