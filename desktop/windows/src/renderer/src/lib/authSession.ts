// Firebase session health for the primary API client. Mirrors the macOS
// AuthSessionCoordinator refresh→retry→classify model (INV-AUTH-1): on a 401 the
// client force-refreshes the ID token once and retries; the outcome is then
// classified as a DEFINITIVE death (→ sign-in) or a TRANSIENT failure (→ keep the
// session, retry later). Critically, a network blip during refresh must NOT sign
// the user out. The definitive path is LIGHT — it never wipes local data; a full
// teardown is reserved for a user-initiated Sign Out (firebase.signOutUser →
// authTeardown).
import { signOut } from 'firebase/auth'
import { auth, onAuthStateChanged } from './firebase'
import { toast } from './toast'

// Firebase Auth error codes that mean the credential is permanently dead — the
// JS-SDK equivalents of macOS's INVALID_REFRESH_TOKEN / USER_DISABLED /
// USER_NOT_FOUND / TOKEN_EXPIRED. Anything else (network-request-failed, unknown)
// is treated as transient so a blip can't spuriously kick the user to sign-in.
const DEFINITIVE_AUTH_CODES = new Set([
  'auth/user-token-expired', // refresh token expired (TOKEN_EXPIRED)
  'auth/user-disabled', // USER_DISABLED
  'auth/user-not-found', // USER_NOT_FOUND
  'auth/invalid-user-token' // INVALID_REFRESH_TOKEN
])

export type RefreshOutcome =
  | { status: 'ok'; token: string }
  | { status: 'dead' } // no session, or a permanent refresh failure → needs reauth
  | { status: 'transient' } // network/unknown refresh failure → keep creds, retry later

// One reauth prompt per burst: a page load fires many requests at once, and a
// dead session 401s them all. Without this guard each 401 would sign out + toast
// again. Reset when a user signs back in so a LATER session death in the same app
// run still routes to Login.
let reauthInFlight = false

/**
 * Force a network refresh of the current user's Firebase ID token, classifying
 * the result so the caller can distinguish "the session is dead, prompt sign-in"
 * from "a transient failure, keep the session and retry later".
 */
export async function refreshIdToken(): Promise<RefreshOutcome> {
  const user = auth.currentUser
  if (!user) return { status: 'dead' }
  try {
    return { status: 'ok', token: await user.getIdToken(true) }
  } catch (e) {
    const code = (e as { code?: string })?.code ?? ''
    return DEFINITIVE_AUTH_CODES.has(code) ? { status: 'dead' } : { status: 'transient' }
  }
}

/**
 * The Firebase session is definitively dead: no user, a permanent refresh
 * failure, or the backend rejected even a freshly-refreshed token. Drop the
 * Firebase SDK session so onAuthStateChanged emits null and the router falls back
 * to the Login screen (the sign-in CTA), and surface a one-time prompt. Does NOT
 * wipe local data — that is the user-initiated Sign Out path. Guarded so a burst
 * of concurrent 401s triggers exactly one sign-out + toast.
 */
export async function forceReauth(): Promise<void> {
  if (reauthInFlight) return
  reauthInFlight = true
  toast('Your session expired — please sign in again', { tone: 'warn' })
  try {
    await signOut(auth)
  } catch {
    /* best-effort; a partial sign-out still emits null from onAuthStateChanged */
  }
}

// Re-arm the guard whenever a user signs in, so a session death later in the same
// app run can prompt again. Wrapped in try/catch: in the node/vitest fallback
// `auth` (getAuth) this subscription may be a no-op stub.
try {
  onAuthStateChanged(auth, (u) => {
    if (u) reauthInFlight = false
  })
} catch {
  /* non-browser env (vitest) — tests reset the guard via __resetReauthGuardForTest */
}

/** Test hook: reset the concurrent-401 guard (module state persists across tests). */
export function __resetReauthGuardForTest(): void {
  reauthInFlight = false
}
