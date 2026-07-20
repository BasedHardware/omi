import { initializeApp } from 'firebase/app'
import {
  initializeAuth,
  getAuth,
  GoogleAuthProvider,
  connectAuthEmulator,
  signInWithEmailAndPassword,
  signInWithPopup,
  signInWithCustomToken,
  signOut,
  onAuthStateChanged,
  browserLocalPersistence,
  browserPopupRedirectResolver,
  type User
} from 'firebase/auth'
import { native } from './native'

export const firebaseConfig = {
  apiKey: (import.meta.env.VITE_FIREBASE_API_KEY as string) || 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8',
  authDomain: (import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string) || 'based-hardware.firebaseapp.com',
  projectId: (import.meta.env.VITE_FIREBASE_PROJECT_ID as string) || 'based-hardware'
}

const localProfile = import.meta.env.VITE_OMI_DESKTOP_LOCAL_PROFILE === '1'
const authEmulatorHost = (import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_HOST as string | undefined)?.trim()
const localEmail = (import.meta.env.VITE_OMI_LOCAL_AUTH_EMAIL as string | undefined)?.trim()
const localPassword = import.meta.env.VITE_OMI_LOCAL_AUTH_PASSWORD as string | undefined

function emulatorUrl(host: string | undefined): string | null {
  if (!host || !/^(?:127\.0\.0\.1|localhost):\d+$/.test(host)) return null
  return `http://${host}`
}

const app = initializeApp(firebaseConfig)

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

const localAuthEmulator = emulatorUrl(authEmulatorHost)
if (localProfile && localAuthEmulator) connectAuthEmulator(auth, localAuthEmulator, { disableWarnings: true })

export async function signInWithGoogle(): Promise<User> {
  const provider = new GoogleAuthProvider()
  const result = await signInWithPopup(auth, provider)
  return result.user
}

export async function signInWithDesktopGoogle(): Promise<User> {
  if (localProfile) {
    if (!localAuthEmulator) throw new Error('Local Firebase Auth requires a loopback VITE_FIREBASE_AUTH_EMULATOR_HOST.')
    if (!localEmail || !localPassword) throw new Error('Local Firebase Auth requires seeded email and password credentials.')
    const result = await signInWithEmailAndPassword(auth, localEmail, localPassword)
    return result.user
  }
  const result = await signInWithCustomToken(auth, await native.authGoogleSignIn())
  return result.user
}

export async function signOutUser(): Promise<void> {
  await signOut(auth)
}

export { onAuthStateChanged }
