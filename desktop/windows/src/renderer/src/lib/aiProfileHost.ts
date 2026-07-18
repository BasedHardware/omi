// Renderer host for the AI User Profile service (Track 3).
//
// The main-process service (src/main/assistants/aiUserProfile/service.ts) owns
// everything about the profile: the >24h cadence, the daily timer, generation,
// storage and backend sync. It is INERT until it has a backend session, because
// on Windows (unlike macOS) the Firebase auth token lives only in the RENDERER.
//
// So this host is a PURE SESSION RELAY and nothing more. It forwards
// {apiBase, desktopApiBase, token} to main on sign-in and on every Firebase
// id-token refresh (~hourly), and clears it on sign-out. It deliberately does
// NOT decide when to generate: no due-check, no aiProfileGetLatest() age math,
// no generateNow() on this path. Cadence stays in main, where the real
// `generatedAt` timestamp lives — configureAiProfileSession() kicks a runIfDue()
// on each push, gated by shouldGenerate(), so hourly refreshes still yield at
// most one generation per day. (generateNow remains exposed over IPC purely for
// a manual "regenerate now" affordance / smoke harness.)
//
// Relaying on every token refresh is the point, not a side effect: it keeps
// main's cached token fresh so its backend calls don't start 401ing after the
// initial token expires.
import { onIdTokenChanged, type User } from 'firebase/auth'
import { auth } from './firebase'

let started = false

// Monotonic id for the latest auth event. `user.getIdToken()` can be a real
// network refresh (hundreds of ms), so a sign-out landing during that await
// would otherwise let the resolved token overtake clearSession() and re-arm main
// with the signed-out user's credentials — exactly what clearSession exists to
// prevent. Every auth event bumps this; a push whose seq is stale by the time its
// token resolves is dropped.
let authSeq = 0

/** Relay a fresh session to main. Never throws (the caller is an auth listener)
 *  and never logs the token. */
async function pushSession(user: User, seq: number): Promise<void> {
  try {
    const token = await user.getIdToken()
    // Two independent staleness checks, both AFTER the await:
    //   seq      — a newer auth event (sign-out, or another user) has since fired.
    //   currentUser — belt-and-braces on Firebase's own view of who is signed in.
    if (seq !== authSeq || auth.currentUser !== user) {
      console.log('[ai-profile-host] dropping stale session push')
      return
    }
    await window.omi.aiProfileSetSession({
      apiBase: import.meta.env.VITE_OMI_API_BASE as string,
      desktopApiBase: import.meta.env.VITE_OMI_DESKTOP_API_BASE as string,
      token
    })
    console.log('[ai-profile-host] session pushed')
  } catch (e) {
    console.warn('[ai-profile-host] session push failed', e)
  }
}

/** Respond to a main-process token PULL. Main asks for a fresh token when its
 *  cached (push-relayed) one has gone stale — which happens when THIS hidden
 *  window's background refresh is throttled and stops re-pushing. `getIdToken(true)`
 *  forces a real refresh even while hidden, so the pull hands main a live token.
 *  A signed-out (or failed) state replies null: main treats null as "no token
 *  available", never as a sign-out (real sign-out flows through clearSession). */
async function respondTokenPull(requestId: number): Promise<void> {
  try {
    const user = auth.currentUser
    if (!user) {
      window.omi.respondSessionToken(requestId, null)
      return
    }
    const token = await user.getIdToken(true)
    // A sign-out could have landed during the refresh await — don't hand main a
    // departed user's token.
    if (auth.currentUser !== user) {
      window.omi.respondSessionToken(requestId, null)
      return
    }
    window.omi.respondSessionToken(requestId, {
      apiBase: import.meta.env.VITE_OMI_API_BASE as string,
      desktopApiBase: import.meta.env.VITE_OMI_DESKTOP_API_BASE as string,
      token
    })
  } catch (e) {
    console.warn('[ai-profile-host] token pull failed', e)
    // Settle main's pull promptly (it keeps its cached session on a null reply).
    try {
      window.omi.respondSessionToken(requestId, null)
    } catch {
      /* window torn down mid-pull */
    }
  }
}

/** Clear main's cached session on sign-out, so a background timer tick can't
 *  keep hitting the backend with the previous user's token. */
async function clearSession(): Promise<void> {
  try {
    await window.omi.aiProfileSetSession(null)
    console.log('[ai-profile-host] session cleared')
  } catch (e) {
    console.warn('[ai-profile-host] session clear failed', e)
  }
}

/**
 * Start the AI-profile session relay once. Idempotent: `started` is set
 * SYNCHRONOUSLY before subscribing, so a StrictMode double-mount / Home remount
 * can't register a second id-token listener (which would double every push).
 *
 * The subscription lives for the whole app session and is never torn down — the
 * renderer host has no unmount story, matching the insight engine's timer.
 */
export function startAiProfileHost(): void {
  if (started) return
  started = true
  onIdTokenChanged(auth, (user) => {
    const seq = ++authSeq
    // Fire-and-forget: an auth listener must not return a rejected promise.
    if (user) void pushSession(user, seq)
    else void clearSession()
  })
  // PULL counterpart to the push relay: answer main's on-demand token requests so
  // its backend calls survive a throttled push refresh. The subscription lives for
  // the whole app session (never torn down), same as the id-token listener above.
  window.omi.onSessionTokenRequest((requestId) => {
    void respondTokenPull(requestId)
  })
}
