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

// --- Pull-based token freshness (Windows-specific) --------------------------
//
// The PUSH relay above only keeps `cached` fresh while the renderer's ~hourly
// id-token refresh keeps firing. But the renderer lives in a HIDDEN main window
// whose background timers Chromium throttles, so that refresh can stall — and
// then every main-side REST call 401s against a dead token (GETs and POSTs
// alike). macOS never hits this: it mints tokens in the main process.
//
// The fix is a PULL fallback: main can ask the renderer for a fresh token on
// demand (the renderer's getIdToken() auto-refreshes even while hidden). The
// crux is the EPOCH. A same-user refresh swaps the token IN PLACE and
// DELIBERATELY DOES NOT bump the epoch: a new token for the same user does not
// change which account the in-flight job's data belongs to, so dooming that job
// (as a push refresh does) would defeat the whole point — the retry would be
// discarded before it could land. Only a real account change routes through
// setBackendSession. The push relay stays untouched; pull is a strictly additive
// fallback layer.

/** The renderer-pull seam: resolve a fresh session for the CURRENT user, or null
 *  when the renderer can't provide one right now. A null result means "no refresh
 *  available" (renderer hung/gone, or momentarily signed out) — it is NEVER treated
 *  as a sign-out here; real sign-out stays owned by the push relay's clear. Injected
 *  at app startup; left unset in tests / before wiring, so pull is then a no-op. */
export type TokenRefresher = () => Promise<BackendSession | null>

let tokenRefresher: TokenRefresher | null = null
let pullInFlight: Promise<BackendSession | null> | null = null

/** Wire (or clear) the renderer-pull seam. */
export function setTokenRefresher(fn: TokenRefresher | null): void {
  tokenRefresher = fn
}

/** Refresh this far before the real `exp` so we swap the token just BEFORE it dies
 *  rather than just after (and skip a doomed request in the skew window). */
const TOKEN_EXP_SKEW_MS = 30_000

/** Decode a JWT payload (base64url), tolerating Node's lenient base64 decode — the
 *  same idiom as taskSyncEngine.uidFromToken. Never verifies; the claims only drive
 *  local freshness/identity decisions. */
function decodeJwt(token: string): Record<string, unknown> | null {
  try {
    const seg = token.split('.')[1] ?? ''
    return JSON.parse(Buffer.from(seg, 'base64').toString('utf8')) as Record<string, unknown>
  } catch {
    return null
  }
}

function tokenExpMs(token: string): number | null {
  const exp = decodeJwt(token)?.exp
  return typeof exp === 'number' ? exp * 1000 : null
}

function tokenUid(token: string): string | null {
  const payload = decodeJwt(token)
  const uid = payload?.user_id ?? payload?.sub
  return typeof uid === 'string' && uid.length > 0 ? uid : null
}

/** True when the cached token is within the skew window of (or past) its `exp`. An
 *  undecodable `exp` returns false: we can't prove staleness, so we defer to the
 *  401 path rather than pulling on every request. */
export function isSessionExpired(now: number = Date.now()): boolean {
  if (!cached) return false
  const exp = tokenExpMs(cached.token)
  if (exp === null) return false
  return exp - now <= TOKEN_EXP_SKEW_MS
}

/** Apply a pulled session. A null pull is ignored (see TokenRefresher). A pull for
 *  the SAME user (uid + both bases match) swaps the token in place with the epoch
 *  PRESERVED; a different user is a real switch → setBackendSession bumps the epoch,
 *  dooming the caller's in-flight run exactly as a fresh sign-in would.
 *  An UNDECODABLE pulled uid (null) is treated as NOT-same-user: we can't prove it
 *  is the current user, so we conservatively route through setBackendSession rather
 *  than let `null === null` swap it in place while preserving the epoch. */
function applyPulledSession(pulled: BackendSession | null): void {
  if (!pulled || !cached) return
  const pulledUid = tokenUid(pulled.token)
  const sameUser =
    pulledUid !== null &&
    pulledUid === tokenUid(cached.token) &&
    pulled.apiBase === cached.apiBase &&
    pulled.desktopApiBase === cached.desktopApiBase
  if (sameUser) cached = { ...cached, token: pulled.token }
  else setBackendSession(pulled)
}

/** Pull a fresh token from the renderer, COALESCING concurrent callers onto one
 *  in-flight round-trip (no hot loop of parallel pulls). A failed/absent pull
 *  leaves the cached session untouched. */
export async function pullFreshSession(): Promise<void> {
  const refresher = tokenRefresher
  if (!refresher) return
  if (!pullInFlight) {
    pullInFlight = refresher().finally(() => {
      pullInFlight = null
    })
  }
  try {
    applyPulledSession(await pullInFlight)
  } catch {
    // Renderer unreachable / timed out: keep the stale session — the caller's
    // request will 401 and fail as before. Never logs the token.
  }
}

/** Issue a backend request with pull-based token freshness. `doFetch` receives the
 *  session to use and MUST read its token from that argument (not a captured one).
 *   - Pre-check: if the cached token is already expired, pull a fresh one first, so
 *     we skip a doomed 401 round-trip.
 *   - On a 401: pull once and retry EXACTLY once — but only when the pull was a
 *     same-user refresh (the epoch did not move). A pull that moved the epoch is an
 *     account switch / sign-out whose result the caller's own epoch guard drops, so
 *     the 401 is surfaced instead of retried (never a hot retry loop).
 *
 *  CONTRACT: this helper guarantees token FRESHNESS, not identity safety. If the
 *  pre-emptive pull switches accounts, the FIRST doFetch runs against the new
 *  user's session — that is safe only because the caller composes the session abort
 *  signal (getAbortSignal) into the request AND drops the result via its own epoch
 *  guard (getSessionEpoch pinned at entry). Callers must keep doing both. */
export async function fetchWithFreshToken(
  doFetch: (session: BackendSession) => Promise<Response>
): Promise<Response> {
  if (isSessionExpired()) await pullFreshSession()
  const s1 = getBackendSession()
  if (!s1) throw new Error('backend session unavailable')
  const res = await doFetch(s1)
  if (res.status !== 401) return res
  const epoch = getSessionEpoch()
  await pullFreshSession()
  if (getSessionEpoch() !== epoch) return res
  const s2 = getBackendSession()
  if (!s2 || s2.token === s1.token) return res
  return doFetch(s2)
}
