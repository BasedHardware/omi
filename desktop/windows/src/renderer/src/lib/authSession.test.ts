// 401 session-health behavior: refreshIdToken (force-refresh / dead-session
// classification) and forceReauth (light reauth — one prompt per burst, re-armed
// on sign-in). ./firebase and ./toast are fully mocked so this never touches the
// real Firebase SDK or the preferences/localStorage import chain.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  authObj: {
    currentUser: null as { getIdToken: (force?: boolean) => Promise<string> } | null
  },
  signOut: vi.fn(async () => {}),
  toast: vi.fn(),
  authCb: undefined as ((u: unknown) => void) | undefined
}))

// A FirebaseError-shaped rejection: getIdToken throws an object carrying `.code`.
function authError(code: string): Error & { code: string } {
  return Object.assign(new Error(code), { code })
}

vi.mock('firebase/auth', () => ({ signOut: h.signOut }))
vi.mock('./firebase', () => ({
  auth: h.authObj,
  onAuthStateChanged: (_a: unknown, cb: (u: unknown) => void) => {
    h.authCb = cb
    return () => {}
  }
}))
vi.mock('./toast', () => ({ toast: h.toast }))

import { forceReauth, refreshIdToken, __resetReauthGuardForTest } from './authSession'

beforeEach(() => {
  h.authObj.currentUser = null
  h.signOut.mockClear()
  h.toast.mockClear()
  __resetReauthGuardForTest()
})
afterEach(() => vi.restoreAllMocks())

describe('refreshIdToken — classifies the outcome', () => {
  it('is dead when no user is signed in', async () => {
    expect(await refreshIdToken()).toEqual({ status: 'dead' })
  })

  it('is ok with a force-refreshed token when the session is alive', async () => {
    const getIdToken = vi.fn(async () => 'fresh-token')
    h.authObj.currentUser = { getIdToken }
    expect(await refreshIdToken()).toEqual({ status: 'ok', token: 'fresh-token' })
    expect(getIdToken).toHaveBeenCalledWith(true) // forced network refresh
  })

  it('is dead on a permanent Firebase code (revoked/expired/disabled)', async () => {
    for (const code of [
      'auth/user-token-expired',
      'auth/user-disabled',
      'auth/user-not-found',
      'auth/invalid-user-token'
    ]) {
      h.authObj.currentUser = { getIdToken: vi.fn(async () => Promise.reject(authError(code))) }
      expect(await refreshIdToken()).toEqual({ status: 'dead' })
    }
  })

  it('is TRANSIENT on a network blip — must not be treated as dead', async () => {
    h.authObj.currentUser = {
      getIdToken: vi.fn(async () => Promise.reject(authError('auth/network-request-failed')))
    }
    expect(await refreshIdToken()).toEqual({ status: 'transient' })
  })

  it('is transient on an unknown/uncoded error (fail-safe, keep the session)', async () => {
    h.authObj.currentUser = {
      getIdToken: vi.fn(async () => Promise.reject(new Error('boom')))
    }
    expect(await refreshIdToken()).toEqual({ status: 'transient' })
  })
})

describe('forceReauth (light reauth)', () => {
  it('signs out and prompts exactly once for a burst of concurrent 401s', async () => {
    await Promise.all([forceReauth(), forceReauth(), forceReauth()])
    expect(h.signOut).toHaveBeenCalledTimes(1)
    expect(h.toast).toHaveBeenCalledTimes(1)
  })

  it('re-arms after a sign-in so a later session death prompts again', async () => {
    await forceReauth()
    expect(h.signOut).toHaveBeenCalledTimes(1)

    // Simulate the user signing back in — the module's auth listener resets the guard.
    h.authCb?.({ uid: 'u1' })

    await forceReauth()
    expect(h.signOut).toHaveBeenCalledTimes(2)
  })
})
