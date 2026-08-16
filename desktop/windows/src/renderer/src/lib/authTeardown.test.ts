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
import { cache as memoriesCache } from './memoriesCache'
import { cache as goalsCache } from './goalsCache'

const LAST_UID_KEY = 'omi.lastSignedInUid'

const wipeUserData = vi.fn(async () => {})
const byokClearAll = vi.fn(async () => {})
const mcpClearKey = vi.fn(async () => {})
const gmailSessionDisconnect = vi.fn(async () => ({ connected: false }))

beforeEach(() => {
  wipeUserData.mockClear()
  byokClearAll.mockClear()
  mcpClearKey.mockClear()
  gmailSessionDisconnect.mockClear()
  h.invalidateConversationsCache.mockClear()
  h.clearPendingConversations.mockClear()
  h.clearUserScopedPreferences.mockClear()
  h.clearMemoryCache.mockClear()
  ;(globalThis as { window: { omi: unknown } }).window.omi = {
    wipeUserData,
    byokClearAll,
    mcpClearKey,
    gmailSessionDisconnect,
    byokGetAll: vi.fn(async () => ({}))
  }
  localStorage.setItem('omi-chat-infinite-id', 'chat-123')
  localStorage.setItem('omi.syncBackfillPosts', '["a","b"]')
  localStorage.setItem('omi-windows-prefs-v1', '{"language":"en"}') // device blob — must survive
})
afterEach(() => localStorage.clear())

describe('teardownUserData', () => {
  it('wipes SQLite, clears caches, removes user localStorage, and clears identity prefs', async () => {
    await teardownUserData()

    expect(wipeUserData).toHaveBeenCalledTimes(1)
    // BYOK keys must be cleared so a second account can't send them (leak fix).
    expect(byokClearAll).toHaveBeenCalledTimes(1)
    // Hosted MCP export key likewise — cleared on sign-out / account switch.
    expect(mcpClearKey).toHaveBeenCalledTimes(1)
    // Gmail session partition cleared so a second account can't fetch the prior
    // user's mail through the install-wide persist:omi-gmail cookie jar (leak fix).
    expect(gmailSessionDisconnect).toHaveBeenCalledTimes(1)
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

  it('resets the Memories module cache and purges per-uid cold-start snapshots (cross-account leak fix)', async () => {
    // Simulate an in-session account with warm Memories + Goals caches + snapshots.
    memoriesCache.list = [{ id: 'a-secret' }] as never
    memoriesCache.loaded = true
    goalsCache.goals = [{ id: 'g-secret' }] as never
    goalsCache.loaded = true
    localStorage.setItem('omi.cache.memories.userA', JSON.stringify([{ id: 'a-secret' }]))
    localStorage.setItem('omi.cache.conversations.userA', JSON.stringify([{ id: 'c1' }]))
    localStorage.setItem('omi.cache.goals.userA', JSON.stringify([{ id: 'g-secret' }]))

    await teardownUserData()

    // In-memory singletons reset so a second account can't read them before refetch.
    expect(memoriesCache.list).toBeNull()
    expect(memoriesCache.loaded).toBe(false)
    expect(goalsCache.goals).toBeNull()
    expect(goalsCache.loaded).toBe(false)
    // Every per-uid cold-start snapshot is purged from localStorage.
    expect(localStorage.getItem('omi.cache.memories.userA')).toBeNull()
    expect(localStorage.getItem('omi.cache.conversations.userA')).toBeNull()
    expect(localStorage.getItem('omi.cache.goals.userA')).toBeNull()
    // The device-prefs blob (non-cache) still survives.
    expect(localStorage.getItem('omi-windows-prefs-v1')).toBe('{"language":"en"}')
  })
})

describe('reconcileAccountForSignIn — account-switch guard', () => {
  it('wipes exactly once and stores the new uid when a DIFFERENT account signs in', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')

    await reconcileAccountForSignIn('userB')

    expect(wipeUserData).toHaveBeenCalledTimes(1)
    // The prior account's BYOK keys + Gmail session are cleared before B hydrates.
    expect(byokClearAll).toHaveBeenCalledTimes(1)
    expect(gmailSessionDisconnect).toHaveBeenCalledTimes(1)
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
