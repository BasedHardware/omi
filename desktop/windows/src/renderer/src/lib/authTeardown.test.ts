// @vitest-environment jsdom
// Sign-out teardown must clear ALL user-scoped local state: the SQLite store (via
// the wipeUserData bridge), in-memory caches, user localStorage keys, and the
// user-identity prefs — so a second account on the machine starts clean.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  invalidateConversationsCache: vi.fn(),
  clearPendingConversations: vi.fn(),
  clearUserScopedPreferences: vi.fn(),
  clearMemoryCache: vi.fn()
}))

vi.mock('./pageCache', () => ({
  invalidateConversationsCache: h.invalidateConversationsCache,
  clearPendingConversations: h.clearPendingConversations
}))
vi.mock('./preferences', () => ({ clearUserScopedPreferences: h.clearUserScopedPreferences }))
vi.mock('./localAgentMemoryCache', () => ({ clearMemoryCache: h.clearMemoryCache }))

import { reconcileAccountForSignIn, teardownUserData } from './authTeardown'

const LAST_UID_KEY = 'omi.lastSignedInUid'

const wipeUserData = vi.fn(async () => {})

beforeEach(() => {
  wipeUserData.mockClear()
  h.invalidateConversationsCache.mockClear()
  h.clearPendingConversations.mockClear()
  h.clearUserScopedPreferences.mockClear()
  h.clearMemoryCache.mockClear()
  ;(globalThis as { window: { omi: unknown } }).window.omi = { wipeUserData }
  localStorage.setItem('omi-chat-infinite-id', 'chat-123')
  localStorage.setItem('omi.syncBackfillPosts', '["a","b"]')
  localStorage.setItem('omi-windows-prefs-v1', '{"language":"en"}') // device blob — must survive
})
afterEach(() => localStorage.clear())

describe('teardownUserData', () => {
  it('wipes SQLite, clears caches, removes user localStorage, and clears identity prefs', async () => {
    await teardownUserData()

    expect(wipeUserData).toHaveBeenCalledTimes(1)
    expect(h.invalidateConversationsCache).toHaveBeenCalledTimes(1)
    expect(h.clearPendingConversations).toHaveBeenCalledTimes(1)
    expect(h.clearMemoryCache).toHaveBeenCalledTimes(1)
    expect(h.clearUserScopedPreferences).toHaveBeenCalledTimes(1)

    expect(localStorage.getItem('omi-chat-infinite-id')).toBeNull()
    expect(localStorage.getItem('omi.syncBackfillPosts')).toBeNull()
    // The device-prefs blob is machine-scoped and must NOT be removed here (its
    // user-identity fields are cleared surgically by clearUserScopedPreferences).
    expect(localStorage.getItem('omi-windows-prefs-v1')).toBe('{"language":"en"}')
  })

  it('still clears caches + localStorage even if the SQLite wipe fails', async () => {
    wipeUserData.mockRejectedValueOnce(new Error('ipc down'))

    await teardownUserData()

    expect(h.invalidateConversationsCache).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('omi-chat-infinite-id')).toBeNull()
  })
})

describe('reconcileAccountForSignIn — account-switch guard', () => {
  it('wipes exactly once and stores the new uid when a DIFFERENT account signs in', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')

    await reconcileAccountForSignIn('userB')

    expect(wipeUserData).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(LAST_UID_KEY)).toBe('userB')
    // The uid pointer must survive teardown (it's machine-scoped, not in the
    // user-scoped key list) so the NEXT switch is still detected.
  })

  it('does NOT wipe when the SAME uid re-authenticates (light-401 recovery)', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')

    await reconcileAccountForSignIn('userA')

    expect(wipeUserData).not.toHaveBeenCalled()
    expect(localStorage.getItem(LAST_UID_KEY)).toBe('userA')
  })

  it('does NOT wipe on the first-ever sign-in (no stored uid), just records it', async () => {
    // No LAST_UID_KEY set.
    await reconcileAccountForSignIn('userA')

    expect(wipeUserData).not.toHaveBeenCalled()
    expect(localStorage.getItem(LAST_UID_KEY)).toBe('userA')
  })

  it('leaves the stored uid untouched on sign-out (uid null) so the next switch is detected', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')

    await reconcileAccountForSignIn(null)

    expect(wipeUserData).not.toHaveBeenCalled()
    expect(localStorage.getItem(LAST_UID_KEY)).toBe('userA')
  })
})
