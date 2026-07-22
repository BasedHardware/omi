// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, cleanup, waitFor, act } from '@testing-library/react'

// The hook fetches via memoriesBulk.fetchAllMemoriesPaged; stub that seam so the
// revalidating fetch resolves deterministically without a network call.
const fetchAllMemoriesPaged = vi.fn()
vi.mock('../lib/memoriesBulk', () => ({
  fetchAllMemoriesPaged: (...a: unknown[]) => fetchAllMemoriesPaged(...a)
}))
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
}))

import { useMemories } from './useMemories'
import { cache as memoriesCacheState, resetMemoriesCache } from '../lib/memoriesCache'

const LAST_UID_KEY = 'omi.lastSignedInUid'
const KEY_A = 'omi.cache.memories.userA'
const mem = (id: string): unknown => ({
  id,
  uid: 'u',
  content: id,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
})

beforeEach(() => {
  localStorage.clear()
  // Fresh module cache per test (the singleton survives across tests in a file).
  resetMemoriesCache()
  fetchAllMemoriesPaged.mockReset().mockResolvedValue([])
})
afterEach(cleanup)

describe('useMemories — cold-start cache-first', () => {
  it('renders the persisted snapshot immediately with no loading spinner', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([mem('cached-1'), mem('cached-2')]))
    fetchAllMemoriesPaged.mockResolvedValue([mem('cached-1'), mem('cached-2')])

    const { result } = renderHook(() => useMemories())

    // First (synchronous) render already has the cached rows and no spinner.
    expect(result.current.loading).toBe(false)
    expect(result.current.memories.map((m) => m.id)).toEqual(['cached-1', 'cached-2'])
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('still shows the loading state on a true cold start with no snapshot', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    const { result } = renderHook(() => useMemories())
    expect(result.current.loading).toBe(true)
    expect(result.current.memories).toEqual([])
  })

  it('revalidates and overwrites the cached snapshot with fresh data', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([mem('stale')]))
    fetchAllMemoriesPaged.mockResolvedValue([mem('fresh')])

    const { result } = renderHook(() => useMemories())
    // Instant: the stale snapshot renders before the network returns.
    expect(result.current.memories.map((m) => m.id)).toEqual(['stale'])
    // Then revalidation swaps in the fresh list...
    await waitFor(() => expect(result.current.memories.map((m) => m.id)).toEqual(['fresh']))
    // ...and mirrors it back to the per-uid snapshot for the next cold start.
    const persisted = JSON.parse(localStorage.getItem(KEY_A) as string) as { id: string }[]
    expect(persisted.map((m) => m.id)).toEqual(['fresh'])
  })

  it('does not leak the snapshot across accounts (per-uid scoping)', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([mem('a-secret')]))
    // A different account signs in (teardown resets the in-memory cache).
    resetMemoriesCache()
    localStorage.setItem(LAST_UID_KEY, 'userB')

    const { result } = renderHook(() => useMemories())
    expect(result.current.memories).toEqual([])
    await waitFor(() => expect(result.current.loading).toBe(false))
  })

  it('clears a mounted Memories view immediately when teardown resets the cache', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([mem('a-visible')]))

    const { result } = renderHook(() => useMemories())
    // The mounted view shows account A's cached memory.
    expect(result.current.memories.map((m) => m.id)).toEqual(['a-visible'])

    // Teardown (sign-out / account switch) must clear it in-place, not leave A's
    // list on screen until a remount.
    await act(async () => {
      resetMemoriesCache()
    })
    expect(result.current.memories).toEqual([])
  })

  it('does not persist memories cross-account when the account switches mid-fetch', async () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    // The fetch resolves AFTER a switch to userB (teardown already ran, uid flipped).
    fetchAllMemoriesPaged.mockImplementation(async () => {
      localStorage.setItem(LAST_UID_KEY, 'userB')
      return [mem('a-memory')]
    })

    renderHook(() => useMemories())
    await waitFor(() => expect(fetchAllMemoriesPaged).toHaveBeenCalled())

    // A's memories must NOT be written under B's uid (nor re-created under A's).
    expect(localStorage.getItem('omi.cache.memories.userB')).toBeNull()
    expect(localStorage.getItem('omi.cache.memories.userA')).toBeNull()
    // And `loaded` must stay false so account B still revalidates (doesn't skip
    // the fetch and show an empty list).
    expect(memoriesCacheState.loaded).toBe(false)
  })
})
