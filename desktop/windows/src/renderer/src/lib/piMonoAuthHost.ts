// Renderer host for the pi-mono managed-cloud chat session (Track 1).
//
// Same shape, and the same reason for existing, as `rewindEmbedHost.ts` and
// `aiProfileHost.ts`: the main-process consumer (the pi-mono session store /
// adapter, src/main/codingAgent/piMonoSession.ts) needs a Firebase ID token,
// but on Windows (unlike macOS) that token lives ONLY in the renderer. So the
// store is inert until a session is relayed in.
//
// This is a PURE SESSION RELAY and nothing more. It pushes {token,
// desktopApiBase} to main on sign-in and on every id-token refresh (~hourly,
// which keeps main's token from expiring while a pi subprocess is live — a
// refresh restarts the subprocess with the fresh token), and clears it on
// sign-out so a background pi run can't keep spending the previous user's
// credentials. It never spawns or drives pi — that lifecycle lives in main.
//
// Kept separate from rewindEmbedHost / aiProfileHost rather than folded in: the
// three consumers are owned by different tracks and neither should be able to
// break another's session by changing its own relay.
import { onIdTokenChanged, type User } from 'firebase/auth'
import { auth } from './firebase'

let started = false

// Monotonic id for the latest auth event. `getIdToken()` can be a real network
// refresh, so a sign-out landing during that await would otherwise let the
// resolved token overtake the clear and re-arm main with the signed-out user's
// credentials. Every auth event bumps this; a push whose seq went stale is dropped.
let authSeq = 0

/** Relay a fresh session to main. Never throws (the caller is an auth listener)
 *  and never logs the token. */
async function pushSession(user: User, seq: number): Promise<void> {
  try {
    const token = await user.getIdToken()
    if (seq !== authSeq || auth.currentUser !== user) {
      console.log('[pi-mono-auth-host] dropping stale session push')
      return
    }
    await window.omi.pimonoSetSession({
      desktopApiBase: import.meta.env.VITE_OMI_DESKTOP_API_BASE as string,
      token
    })
  } catch (e) {
    console.warn('[pi-mono-auth-host] session push failed', e)
  }
}

async function clearSession(): Promise<void> {
  try {
    await window.omi.pimonoSetSession(null)
  } catch (e) {
    console.warn('[pi-mono-auth-host] session clear failed', e)
  }
}

/**
 * Start the relay once. Idempotent: `started` is set SYNCHRONOUSLY before
 * subscribing, so a StrictMode double-mount can't register a second listener
 * (which would double every push).
 */
export function startPiMonoAuthHost(): void {
  if (started) return
  started = true
  onIdTokenChanged(auth, (user) => {
    const seq = ++authSeq
    // Fire-and-forget: an auth listener must not return a rejected promise.
    if (user) void pushSession(user, seq)
    else void clearSession()
  })
}
