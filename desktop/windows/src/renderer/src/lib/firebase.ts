import { initializeApp } from 'firebase/app'
import {
  initializeAuth,
  getAuth,
  signInWithCustomToken,
  signOut,
  updateProfile,
  onAuthStateChanged,
  browserLocalPersistence,
  type User
} from 'firebase/auth'
import { teardownUserData } from './authTeardown'
import { encryptedAuthPersistence, scrubLegacyPlaintextAuth } from './encryptedAuthPersistence'

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string
})

// Initialize auth with persistence set SYNCHRONOUSLY at init so the saved session
// is rehydrated deterministically. The previous getAuth(app) + async
// setPersistence() raced: onAuthStateChanged could emit null before the persisted
// user loaded, which made the (reloaded) overlay window falsely show signed-out.
// Falls back to getAuth in non-browser environments (node/Vitest), where
// initializeAuth's browser persistence can't initialize — keeps importing
// modules that touch firebase unit-testable without changing runtime behavior.
// Persistence hierarchy: the encrypted-at-rest store (safeStorage/DPAPI via the
// main process) is primary; browserLocalPersistence stays as a permanent fallback
// so a machine without OS encryption degrades to plaintext rather than locking the
// user out. Firebase auto-migrates any existing plaintext session INTO the
// encrypted store on init and deletes the plaintext copy (see
// encryptedAuthPersistence — _shouldAllowMigration).
export const auth = (() => {
  try {
    return initializeAuth(app, {
      persistence: [encryptedAuthPersistence, browserLocalPersistence]
    })
  } catch {
    return getAuth(app)
  }
})()

// Belt-and-suspenders: once auth init has settled, sweep any lingering plaintext
// `firebase:authUser:*` key that Firebase's own migration didn't clear (e.g. a
// window that loaded mid-migration). Guarded so it only removes a key the
// encrypted store already holds. Fire-and-forget; never blocks boot.
onAuthStateChanged(auth, () => {
  void scrubLegacyPlaintextAuth()
})

/**
 * Google sign-in via the backend-mediated OAuth flow in the SYSTEM browser.
 * The main process runs the whole PKCE + loopback dance (Google blocks OAuth
 * inside embedded webviews, so the old signInWithPopup path is gone for good)
 * and hands back a Firebase CUSTOM token; from signInWithCustomToken on,
 * persistence and onAuthStateChanged behave exactly as before.
 */
export async function signInWithGoogle(): Promise<User> {
  const result = await window.omi.signInWithGoogle()
  if (!result.ok) throw new Error(result.error)
  const cred = await signInWithCustomToken(auth, result.customToken)
  // Custom-token sessions can start with an empty displayName (fresh Firebase
  // user record); best-effort seed it from the Google profile claims so the
  // sidebar/home greeting show a name immediately.
  const name = [result.givenName, result.familyName].filter(Boolean).join(' ')
  if (name && !cred.user.displayName) {
    try {
      await updateProfile(cred.user, { displayName: name })
    } catch {
      /* cosmetic only */
    }
  }
  return cred.user
}

export async function signOutUser(): Promise<void> {
  // User-initiated sign-out is the NUCLEAR path (vs the LIGHT session
  // invalidation on a 401 — see authSession.forceReauth): tear down all
  // user-scoped local data FIRST so a second account on this machine can't see
  // it, THEN drop the Firebase session.
  //
  // Grab the token BEFORE signing out so we can deactivate BYOK server-side while
  // the session is still valid: teardownUserData wipes the local keys, and this
  // DELETE drops the matching backend enrollment so this account isn't left
  // "enrolled" with no keys (which would 403 its own next requests). Best-effort.
  const token = await auth.currentUser?.getIdToken().catch(() => undefined)
  await teardownUserData()
  if (token) {
    try {
      await window.omi.byokDeactivate(token)
    } catch {
      /* best-effort; the backend heartbeat TTL also lapses the activation */
    }
  }
  await signOut(auth)
}

export { onAuthStateChanged }
