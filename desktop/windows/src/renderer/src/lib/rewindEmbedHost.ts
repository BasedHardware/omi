// Renderer host for the Rewind embedding indexer (Track 4).
//
// Same shape, and the same reason for existing, as `aiProfileHost.ts`: the
// main-process service (src/main/rewind/embeddingService.ts) owns the indexing —
// the queue, the batching, the launch backfill, the query embedder — but on
// Windows (unlike macOS) the Firebase token lives ONLY in the renderer, so the
// service is inert until a session is relayed in.
//
// This is a PURE SESSION RELAY and nothing more. It pushes {desktopApiBase,
// token} to main on sign-in and on every id-token refresh (~hourly, which keeps
// main's token from expiring mid-backfill), and clears it on sign-out so a
// background flush can't keep spending the previous user's credentials.
//
// Kept separate from aiProfileHost rather than folded into it: the two consumers
// are owned by different tracks and neither should be able to break the other's
// session by changing its own relay.
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
      console.log('[rewind-embed-host] dropping stale session push')
      return
    }
    await window.omi.rewindSetEmbedSession({
      desktopApiBase: import.meta.env.VITE_OMI_DESKTOP_API_BASE as string,
      token
    })
  } catch (e) {
    console.warn('[rewind-embed-host] session push failed', e)
  }
}

async function clearSession(): Promise<void> {
  try {
    await window.omi.rewindSetEmbedSession(null)
  } catch (e) {
    console.warn('[rewind-embed-host] session clear failed', e)
  }
}

/**
 * Start the relay once. Idempotent: `started` is set SYNCHRONOUSLY before
 * subscribing, so a StrictMode double-mount can't register a second listener
 * (which would double every push).
 */
export function startRewindEmbedHost(): void {
  if (started) return
  started = true
  onIdTokenChanged(auth, (user) => {
    const seq = ++authSeq
    // Fire-and-forget: an auth listener must not return a rejected promise.
    if (user) void pushSession(user, seq)
    else void clearSession()
  })
}
