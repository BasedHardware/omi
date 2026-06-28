import { initializeApp } from 'firebase/app'
import {
  initializeAuth,
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  browserLocalPersistence,
  browserPopupRedirectResolver,
  type User
} from 'firebase/auth'

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string
})

// Initialize auth with persistence set SYNCHRONOUSLY at init so the saved session
// is rehydrated deterministically. The previous getAuth(app) + async
// setPersistence() raced: onAuthStateChanged could emit null before the persisted
// user loaded, which made the (reloaded) overlay window falsely show signed-out.
// The popup resolver must be supplied explicitly here so signInWithPopup keeps working.
// Falls back to getAuth in non-browser environments (node/Vitest), where
// initializeAuth's browser persistence/resolver can't initialize — keeps importing
// modules that touch firebase unit-testable without changing runtime behavior.
export const auth = (() => {
  try {
    return initializeAuth(app, {
      persistence: browserLocalPersistence,
      popupRedirectResolver: browserPopupRedirectResolver
    })
  } catch {
    return getAuth(app)
  }
})()

export async function signInWithGoogle(): Promise<User> {
  const provider = new GoogleAuthProvider()
  const result = await signInWithPopup(auth, provider)
  return result.user
}

export async function signOutUser(): Promise<void> {
  await signOut(auth)
}

export { onAuthStateChanged }
