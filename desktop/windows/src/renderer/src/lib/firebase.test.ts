import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const initializeApp = vi.fn()
const initializeAuth = vi.fn()
const connectAuthEmulator = vi.fn()
const signInWithCustomToken = vi.fn()
const signInWithEmailAndPassword = vi.fn()

vi.mock('firebase/app', () => ({ initializeApp }))
vi.mock('firebase/auth', () => ({
  GoogleAuthProvider: class GoogleAuthProvider {},
  browserLocalPersistence: {},
  browserPopupRedirectResolver: {},
  connectAuthEmulator,
  getAuth: vi.fn(),
  initializeAuth,
  onAuthStateChanged: vi.fn(),
  signInWithCustomToken,
  signInWithEmailAndPassword,
  signInWithPopup: vi.fn(),
  signOut: vi.fn()
}))

beforeEach(() => {
  vi.resetModules()
  initializeApp.mockClear()
  connectAuthEmulator.mockClear()
  signInWithCustomToken.mockClear()
  signInWithEmailAndPassword.mockClear()
  vi.stubEnv('VITE_FIREBASE_API_KEY', '')
  vi.stubEnv('VITE_FIREBASE_AUTH_DOMAIN', '')
  vi.stubEnv('VITE_FIREBASE_PROJECT_ID', '')
  vi.stubEnv('VITE_OMI_DESKTOP_LOCAL_PROFILE', '')
  vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_EMAIL', '')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_PASSWORD', '')
})

afterEach(() => vi.unstubAllEnvs())

it('uses the managed Firebase config when a packaged build has no env file', async () => {
  await import('./firebase')

  expect(initializeApp).toHaveBeenCalledWith({
    apiKey: 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8',
    authDomain: 'based-hardware.firebaseapp.com',
    projectId: 'based-hardware'
  })
  expect(connectAuthEmulator).not.toHaveBeenCalled()
})

it('uses the seeded Firebase Auth emulator account for a local profile', async () => {
  vi.stubEnv('VITE_OMI_DESKTOP_LOCAL_PROFILE', '1')
  vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '127.0.0.1:9099')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_EMAIL', 'alice@local.omi.invalid')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_PASSWORD', 'alice-local-password-030')
  const user = { uid: 'alice' }
  signInWithEmailAndPassword.mockResolvedValue({ user })

  const firebase = await import('./firebase')
  await expect(firebase.signInWithDesktopGoogle()).resolves.toBe(user)

  expect(connectAuthEmulator).toHaveBeenCalledWith(firebase.auth, 'http://127.0.0.1:9099', { disableWarnings: true })
  expect(signInWithEmailAndPassword).toHaveBeenCalledWith(
    firebase.auth,
    'alice@local.omi.invalid',
    'alice-local-password-030'
  )
  expect(signInWithCustomToken).not.toHaveBeenCalled()
})

it('rejects an invalid local Auth configuration instead of using managed OAuth', async () => {
  vi.stubEnv('VITE_OMI_DESKTOP_LOCAL_PROFILE', '1')
  vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', 'api.omi.me:9099')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_EMAIL', 'alice@local.omi.invalid')
  vi.stubEnv('VITE_OMI_LOCAL_AUTH_PASSWORD', 'alice-local-password-030')
  const firebase = await import('./firebase')

  await expect(firebase.signInWithDesktopGoogle()).rejects.toThrow('loopback')
  expect(connectAuthEmulator).not.toHaveBeenCalled()
  expect(signInWithCustomToken).not.toHaveBeenCalled()
})
