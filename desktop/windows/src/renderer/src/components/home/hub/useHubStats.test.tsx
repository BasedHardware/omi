// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'

// This suite pins the ONE cross-account path the pure-core cache tests can't reach:
// an in-place account switch (A -> B) WITHOUT this hook remounting. B must never
// DISPLAY or PERSIST account A's residual live counts. Today every switch also
// unmounts the shell, but the hook is hardened to stay correct without that.

// Controllable auth: a mutable currentUser + a captured onAuthStateChanged callback
// we fire to simulate a same-mount account switch.
const h = vi.hoisted(() => ({
  currentUser: { uid: 'A' } as { uid: string } | null,
  cb: null as ((u: { uid: string } | null) => void) | null,
  tasks: [] as { id: string }[],
  frames: 0
}))

vi.mock('../../../lib/firebase', () => ({
  auth: {
    get currentUser() {
      return h.currentUser
    }
  },
  onAuthStateChanged: (_a: unknown, cb: (u: { uid: string } | null) => void) => {
    h.cb = cb
    return () => {
      h.cb = null
    }
  }
}))

// memories stays "loading" so that cell is null throughout — this test is about the
// two live cells (tasks/screenshots) fed by []-dep fetch effects.
vi.mock('../../../hooks/useMemories', () => ({
  useMemories: () => ({ memories: [], loading: true, error: null })
}))

vi.mock('../../../lib/actionItems', () => ({
  fetchAllActionItems: () => Promise.resolve(h.tasks)
}))

import { invalidateConversationsCache } from '../../../lib/pageCache'
import { getCachedHubStats } from './hubStatsCache'
import { useHubStats } from './useHubStats'

beforeEach(() => {
  localStorage.clear()
  invalidateConversationsCache() // conversations cell stays null (unpublished)
  h.currentUser = { uid: 'A' }
  h.cb = null
  h.tasks = []
  h.frames = 0
  ;(window as unknown as { omi: unknown }).omi = {
    rewindFrameCount: () => Promise.resolve(h.frames),
    onTasksChanged: () => () => {}
  }
})

afterEach(() => {
  cleanup()
})

describe('useHubStats — in-place account switch (no remount)', () => {
  it('never displays or persists account A’s counts after an A→B uid swap', async () => {
    // A is signed in; its counts resolve and get cached under A.
    h.tasks = [{ id: 'a1' }, { id: 'a2' }, { id: 'a3' }] // 3
    h.frames = 5
    const { result } = renderHook(() => useHubStats())
    await waitFor(() => expect(result.current.tasks).toBe(3))
    await waitFor(() => expect(result.current.screenshots).toBe(5))
    expect(getCachedHubStats('A')).toMatchObject({ tasks: 3, screenshots: 5 })

    // B signs in on the SAME mount. B's fetches will return different numbers.
    h.tasks = [{ id: 'b1' }] // 1
    h.frames = 9
    h.currentUser = { uid: 'B' }
    act(() => h.cb?.({ uid: 'B' }))

    // Synchronously after the swap — before B's fetch resolves — B must NOT see A's
    // 3/5. The live cells reset and B's cache is empty, so both read as unknown, and
    // A's counts were NOT stamped under B.
    expect(result.current.tasks).toBeNull()
    expect(result.current.screenshots).toBeNull()
    expect(getCachedHubStats('B').tasks).toBeNull()
    expect(getCachedHubStats('B').screenshots).toBeNull()

    // Once B's own fetches land, B sees B's numbers, and only those are cached for B.
    await waitFor(() => expect(result.current.tasks).toBe(1))
    await waitFor(() => expect(result.current.screenshots).toBe(9))
    expect(getCachedHubStats('B')).toMatchObject({ tasks: 1, screenshots: 9 })
    // A's blob was overwritten by B's write (the uid stamp discards the prior owner).
    expect(getCachedHubStats('A').tasks).toBeNull()
  })
})
