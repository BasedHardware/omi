// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'

// The cache's only I/O: Firebase auth (uid) and the Python-backend client.
const { get, currentUser } = vi.hoisted(() => ({
  get: vi.fn(),
  currentUser: { uid: 'u1' } as { uid: string } | null
}))
vi.mock('../firebase', () => ({
  auth: {
    get currentUser() {
      return currentUser
    }
  }
}))
vi.mock('../apiClient', () => ({ omiApi: { get } }))

import {
  getUserVocabulary,
  refreshUserVocabulary,
  resetUserVocabulary,
  whenUserVocabularySettled
} from './userVocabulary'

beforeEach(() => {
  get.mockReset()
  resetUserVocabulary()
  currentUser!.uid = 'u1'
})

describe('getUserVocabulary / refreshUserVocabulary — cache', () => {
  it('returns [] before the first refresh and the list after it settles', async () => {
    get.mockResolvedValue({ data: { vocabulary: ['Photoshop', 'Figma'] } })
    expect(getUserVocabulary()).toEqual([])
    refreshUserVocabulary()
    await whenUserVocabularySettled()
    expect(getUserVocabulary()).toEqual(['Photoshop', 'Figma'])
  })

  it('hits the transcription-preferences endpoint and tolerates a missing vocabulary field', async () => {
    get.mockResolvedValue({ data: {} })
    refreshUserVocabulary()
    await whenUserVocabularySettled()
    expect(get).toHaveBeenCalledWith('/v1/users/transcription-preferences')
    expect(getUserVocabulary()).toEqual([])
  })

  it('dedupes a second refresh while the first is in flight for the same account', async () => {
    get.mockReturnValue(new Promise(() => {})) // never settles
    refreshUserVocabulary()
    refreshUserVocabulary()
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('does not serve another account’s cached vocabulary', async () => {
    get.mockResolvedValue({ data: { vocabulary: ['Figma'] } })
    refreshUserVocabulary()
    await whenUserVocabularySettled()
    expect(getUserVocabulary()).toEqual(['Figma'])
    currentUser!.uid = 'u2'
    expect(getUserVocabulary()).toEqual([])
    currentUser!.uid = 'u1'
  })
})

describe('cross-account safety', () => {
  // The fetch runs against whatever token is current when it LANDS. An account
  // switch mid-fetch would otherwise file u2's vocabulary under u1's uid.
  it('discards a fetch whose account switched away while it was in flight', async () => {
    let release: (v: unknown) => void = () => {}
    get.mockReturnValue(new Promise((r) => (release = r)))

    refreshUserVocabulary() // starts for u1
    currentUser!.uid = 'u2'
    release({ data: { vocabulary: ['u2 secret'] } })
    await whenUserVocabularySettled()

    expect(getUserVocabulary()).toEqual([]) // u2 has no cache of its own yet
    currentUser!.uid = 'u1'
    expect(getUserVocabulary()).toEqual([]) // and u1 never inherits u2's fetch
  })

  // Dedupe is per-account: the switched-to account must start its own fetch even
  // while the abandoned one is still in flight.
  it('starts a fresh fetch for the new account despite an in-flight one', async () => {
    get.mockReturnValue(new Promise(() => {})) // u1's fetch never settles
    refreshUserVocabulary()

    currentUser!.uid = 'u2'
    get.mockResolvedValue({ data: { vocabulary: ['grace-term'] } })
    refreshUserVocabulary()
    await whenUserVocabularySettled()

    expect(getUserVocabulary()).toEqual(['grace-term'])
    currentUser!.uid = 'u1'
  })
})

describe('resetUserVocabulary — sign-out', () => {
  it('drops the cache', async () => {
    get.mockResolvedValue({ data: { vocabulary: ['Figma'] } })
    refreshUserVocabulary()
    await whenUserVocabularySettled()
    expect(getUserVocabulary()).toEqual(['Figma'])
    resetUserVocabulary()
    expect(getUserVocabulary()).toEqual([])
  })
})
