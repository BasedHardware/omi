import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const initializeApp = vi.fn()
const initializeAuth = vi.fn()

vi.mock('firebase/app', () => ({ initializeApp }))
vi.mock('firebase/auth', () => ({
  GoogleAuthProvider: class GoogleAuthProvider {},
  browserLocalPersistence: {},
  browserPopupRedirectResolver: {},
  getAuth: vi.fn(),
  initializeAuth,
  onAuthStateChanged: vi.fn(),
  signInWithPopup: vi.fn(),
  signOut: vi.fn()
}))

beforeEach(() => {
  vi.resetModules()
  initializeApp.mockClear()
  vi.stubEnv('VITE_FIREBASE_API_KEY', '')
  vi.stubEnv('VITE_FIREBASE_AUTH_DOMAIN', '')
  vi.stubEnv('VITE_FIREBASE_PROJECT_ID', '')
})

afterEach(() => vi.unstubAllEnvs())

it('uses the managed Firebase config when a packaged build has no env file', async () => {
  await import('./firebase')

  expect(initializeApp).toHaveBeenCalledWith({
    apiKey: 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8',
    authDomain: 'based-hardware.firebaseapp.com',
    projectId: 'based-hardware'
  })
})
