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
export const auth = (() => {
  try {
    return initializeAuth(app, {
      persistence: browserLocalPersistence
    })
  } catch {
    return getAuth(app)
  }
})()

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
  await teardownUserData()
  await signOut(auth)
}

export { onAuthStateChanged }
