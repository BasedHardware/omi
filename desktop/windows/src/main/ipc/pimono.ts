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
import { verifyFirebaseIdToken } from '../auth/firebaseIdToken'

/** Registers the `pimono:*` IPC handlers backing the session store. */
export function registerPiMonoHandlers(): void {
  ipcMain.handle('pimono:setSession', async (_e, session: unknown): Promise<void> => {
    configurePiMonoSession(session)
    // Wire the control-plane owner to the signed-in user, HOST-DERIVED and
    // SIGNATURE-VERIFIED. The relayed payload carries no uid; we take it from the
    // `sub` of the Firebase ID token in the now-validated session — but ONLY after
    // verifying that token is a genuine, unexpired, Google-signed token for this
    // project (verifyFirebaseIdToken). A mere decode would trust an unsigned
    // `{user_id: <victim>}` a compromised renderer could forge, letting it read
    // another local account's kernel chat. The owner is what scopes every kernel
    // session/surface row (surfaceSession.ts) to the real account instead of the
    // shared DEFAULT_LOCAL_OWNER_ID constant.
    //
    // On ANY verification failure (bad sig, wrong alg, expired, wrong aud/iss,
    // cert-fetch failure) uid is null → setControlPlaneOwner falls back to the
    // default constant → the cold-start gate (hasKnownControlPlaneOwner) refuses
    // kernel chat + control tools. Fail closed, never fall back to the decode path.
    // On sign-out (session === null) it resets to default.
    const current = getPiMonoSession()
    const uid = current ? await verifyFirebaseIdToken(current.token) : null
    setControlPlaneOwner(uid)
    // Register the managed-cloud pi-mono adapter into the kernel now that a
    // session may be present. Idempotent, and a no-op when signed out (returns
    // false), so the registry stays empty until a real Firebase session exists.
    // DARK: registration only — nothing routes chat to pi-mono until PR-E.
    ensurePiMonoAdapterRegistered()
  })
}
