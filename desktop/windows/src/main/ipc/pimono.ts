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
import {
  ensurePiMonoAdapterRegistered,
  setControlPlaneOwner,
  controlPlaneOwnerId,
  hasKnownControlPlaneOwner
} from '../agentKernel/controlPlane'
import { verifyFirebaseIdToken } from '../auth/firebaseIdToken'
import {
  clearRendererConversationBinding,
  fenceRendererConversationOwner,
  setRendererConversationSelection
} from '../jit/rendererConversationBinding'

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
    // Keep the renderer-selection projection fenced to the same verified host
    // owner. A token refresh for the same account preserves the selected chat;
    // sign-out or an account switch drops it before any JIT analysis can capture
    // the prior account's deletion key.
    if (uid) fenceRendererConversationOwner(controlPlaneOwnerId())
    else clearRendererConversationBinding()
    // Register the managed-cloud pi-mono adapter into the kernel now that a
    // session may be present. Idempotent, and a no-op when signed out (returns
    // false), so the registry stays empty until a real Firebase session exists.
    // DARK: registration only — nothing routes chat to pi-mono until PR-E.
    ensurePiMonoAdapterRegistered()
  })

  // The renderer reports selection independently of sending. This is the only
  // writer for the JIT -> renderer deletion association; main-chat turns must
  // never update a process-global "last chat" value.
  ipcMain.handle('jit:rendererSelectionChanged', (_e, key: unknown): boolean => {
    if (!hasKnownControlPlaneOwner()) {
      // Keep a cold-start selection pending until the verified auth relay wires
      // the owner. It is only a renderer deletion key (not an authority claim),
      // and sign-out clears it before another account can adopt it.
      setRendererConversationSelection(null, typeof key === 'string' ? key : null)
      return false
    }
    setRendererConversationSelection(
      controlPlaneOwnerId(),
      typeof key === 'string' || key === null ? key : null
    )
    return true
  })
}
