// The ONE backend session every main-process assistant reads.
//
// TOKEN MODEL (Windows-specific): unlike macOS, the Firebase auth token lives in
// the RENDERER, not the main process. Main can't mint its own token — the
// renderer relays a session ({apiBase, desktopApiBase, token}) over IPC on
// sign-in and on every id-token refresh (~hourly). This module owns that cached
// session so we get one renderer relay and many main-side readers, instead of a
// private cache per assistant.
//
// Two safety properties (hard-won in the AI-profile audit; keep both):
//
//  1. A monotonic EPOCH, bumped on EVERY change including null (sign-out). A job
//     pins the epoch at entry and discards its result if the epoch has moved.
//     Without this, a job started under user A can finish after A signed out and
//     B signed in — writing A's data into B's account, past the sign-out wipe.
//     A same-user token refresh also bumps it, so a refresh landing mid-job
//     discards that run (it retries later). That is deliberate: main receives
//     only {bases, token} and cannot tell "same user, new token" from "new user",
//     so it fails safe toward never writing a departed session's data.
//
//  2. An ABORT SIGNAL, aborted on every change, so in-flight HTTP dies promptly
//     instead of running for another 10-90s carrying a token the user just
//     invalidated. The epoch already dooms the result; aborting stops us burning
//     the call as well.

/** Credentials the renderer hands the main process to reach the backend. */
export type BackendSession = {
  /** Python backend base (VITE_OMI_API_BASE) — user data + sync. */
  apiBase: string
  /** Rust desktop backend base (VITE_OMI_DESKTOP_API_BASE) — chat/completions, Gemini proxy. */
  desktopApiBase: string
  /** Fresh Firebase ID token. */
  token: string
}

let cached: BackendSession | null = null
let epoch = 0
let abortController: AbortController | null = null

/** Set/refresh (or clear, on null) the shared session. Every in-flight job for
 *  the previous session is invalidated: its epoch check now fails, and its
 *  network work is aborted. */
export function setBackendSession(session: BackendSession | null): void {
  // Bump FIRST: anything already in flight belongs to the previous session and
  // must be stale from this instant on (jobs re-read the epoch at each write).
  epoch += 1
  cached = session

  abortController?.abort()
  abortController = session ? new AbortController() : null
}

/** The current session, or null when signed out / not yet relayed. */
export function getBackendSession(): BackendSession | null {
  return cached
}

/** Monotonic id of the current session. Pin it at job entry; if it has moved by
 *  the time the job writes, drop the result. */
export function getSessionEpoch(): number {
  return epoch
}

/** Abort signal for the current session — attach it to every request so a
 *  session change kills the request. undefined when there is no session. */
export function getAbortSignal(): AbortSignal | undefined {
  return abortController?.signal
}
