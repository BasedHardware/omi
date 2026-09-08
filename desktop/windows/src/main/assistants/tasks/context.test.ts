// TaskAssistant context assembly: the four slices at their Mac limits, the
// top/recent/staged merge (dedup by id), the 300s goals cache, and per-source
// fail-open. Hermetic — every source is a mock; no DB, no network, no clock.
import { afterEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  fetch: vi.fn(),
  getBackendSession: vi.fn(() => ({ apiBase: 'https://api.test', token: 'tok' }) as unknown),
  getLatestProfileText: vi.fn(() => null as string | null),
  getTopRelevanceActionItems: vi.fn(() => [] as unknown[]),
  getRecentActiveActionItems: vi.fn(() => [] as unknown[]),
  getAllStagedTasks: vi.fn(() => [] as unknown[]),
  getLocalActionItems: vi.fn(() => [] as unknown[])
}))

vi.mock('electron', () => ({ net: { fetch: h.fetch } }))
vi.mock('../core/session', () => ({
  getAbortSignal: () => undefined,
  getBackendSession: h.getBackendSession
}))
vi.mock('../aiUserProfile/service', () => ({ getLatestProfileText: h.getLatestProfileText }))
vi.mock('../../ipc/db', () => ({
  getTopRelevanceActionItems: h.getTopRelevanceActionItems,
  getRecentActiveActionItems: h.getRecentActiveActionItems,
  getAllStagedTasks: h.getAllStagedTasks,
  getLocalActionItems: h.getLocalActionItems
}))

import {
  _resetTaskContextCache,
  buildTaskContextBlock,
  loadTaskContext,
  type TaskContextData
} from './context'

function okGoals(goals: unknown[]): { ok: true; status: 200; json: () => Promise<unknown> } {
  return { ok: true, status: 200, json: async () => ({ goals }) }
}

afterEach(() => {
  _resetTaskContextCache()
  vi.clearAllMocks()
  // Restore default happy-path stubs cleared above.
  h.getBackendSession.mockReturnValue({ apiBase: 'https://api.test', token: 'tok' })
  h.getLatestProfileText.mockReturnValue(null)
  h.getTopRelevanceActionItems.mockReturnValue([])
  h.getRecentActiveActionItems.mockReturnValue([])
  h.getAllStagedTasks.mockReturnValue([])
  h.getLocalActionItems.mockReturnValue([])
  h.fetch.mockReset()
})

describe('loadTaskContext — slice limits', () => {
  it('reads each slice at the Mac limit (30/30/30, completed 10)', async () => {
    h.fetch.mockResolvedValue(okGoals([]))
    await loadTaskContext(new Date('2026-07-15T12:00:00Z'))
    expect(h.getTopRelevanceActionItems).toHaveBeenCalledWith(30)
    expect(h.getRecentActiveActionItems).toHaveBeenCalledWith(30)
    expect(h.getAllStagedTasks).toHaveBeenCalledWith(30)
    expect(h.getLocalActionItems).toHaveBeenCalledWith({ completed: true, limit: 10 })
  })
})

describe('loadTaskContext — active-task merge', () => {
  it('puts top-relevance first, drops recent already in top, keeps staged (id 0)', async () => {
    h.fetch.mockResolvedValue(okGoals([]))
    h.getTopRelevanceActionItems.mockReturnValue([
      { id: 1, description: 'top one', priority: 'high', relevanceScore: 10 }
    ])
    h.getRecentActiveActionItems.mockReturnValue([
      { id: 1, description: 'dup of top', priority: 'high' }, // filtered — id already in top
      { id: 2, description: 'recent two', priority: null }
    ])
    h.getAllStagedTasks.mockReturnValue([
      { id: 99, description: 'staged one', priority: 'low' } // its real id is ignored → 0
    ])

    const ctx = await loadTaskContext()

    expect(ctx.activeTasks).toEqual([
      { id: 1, description: 'top one', priority: 'high' },
      { id: 2, description: 'recent two', priority: null },
      { id: 0, description: 'staged one', priority: 'low' }
    ])
  })
})

describe('loadTaskContext — goals cache (300s)', () => {
  it('does not refetch within the TTL, refetches after it', async () => {
    h.fetch.mockResolvedValue(okGoals([{ title: 'Ship PR-B', is_active: true }]))
    const t0 = new Date('2026-07-15T12:00:00Z')

    const first = await loadTaskContext(t0)
    expect(first.goals).toEqual([{ title: 'Ship PR-B', description: null }])
    expect(h.fetch).toHaveBeenCalledTimes(1)

    // 299s later — inside the window → cache hit, no second fetch.
    await loadTaskContext(new Date(t0.getTime() + 299_000))
    expect(h.fetch).toHaveBeenCalledTimes(1)

    // 301s later — window expired → refetch.
    await loadTaskContext(new Date(t0.getTime() + 301_000))
    expect(h.fetch).toHaveBeenCalledTimes(2)
  })
})

describe('loadTaskContext — fail-open per source', () => {
  it('a throwing local read yields an empty slice; assembly still returns', async () => {
    h.fetch.mockResolvedValue(okGoals([]))
    h.getTopRelevanceActionItems.mockImplementation(() => {
      throw new Error('db down')
    })
    h.getRecentActiveActionItems.mockReturnValue([{ id: 5, description: 'r', priority: null }])
    h.getLocalActionItems.mockImplementation(() => {
      throw new Error('db down')
    })
    h.getLatestProfileText.mockImplementation(() => {
      throw new Error('no profile')
    })

    const ctx = await loadTaskContext()

    expect(ctx.activeTasks).toEqual([{ id: 5, description: 'r', priority: null }])
    expect(ctx.completedTasks).toEqual([])
    expect(ctx.profileText).toBeNull()
    expect(ctx.goals).toEqual([])
  })

  it('goals fail-open: no session → [] and no fetch', async () => {
    h.getBackendSession.mockReturnValue(null)
    const ctx = await loadTaskContext()
    expect(ctx.goals).toEqual([])
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('goals fail-open: non-OK status → []', async () => {
    h.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    const ctx = await loadTaskContext()
    expect(ctx.goals).toEqual([])
  })
})

describe('buildTaskContextBlock — rendering', () => {
  const data: TaskContextData = {
    profileText: 'A busy founder.',
    activeTasks: [
      { id: 42, description: 'Reply to Stan', priority: 'high' },
      { id: 0, description: 'staged item', priority: null }
    ],
    completedTasks: [{ description: 'Sent Nik the deck' }],
    goals: [{ title: 'Grow revenue', description: 'to $1M ARR' }]
  }

  it('renders all present sections in Mac order and format', () => {
    const block = buildTaskContextBlock(data)
    expect(block).toContain('USER PROFILE (who this user is')
    expect(block).toContain('A busy founder.')
    expect(block).toContain(
      'ACTIVE TASKS (use only for semantic duplicate/refinement evidence; never globally rank new captures):'
    )
    expect(block).toContain('1. [id:42] Reply to Stan [high]')
    expect(block).toContain('2. [id:0] staged item')
    expect(block).toContain('RECENTLY COMPLETED TASKS')
    expect(block).toContain('1. Sent Nik the deck')
    expect(block).toContain('ACTIVE GOALS:')
    expect(block).toContain('1. Grow revenue — to $1M ARR')
  })

  it('omits empty sections entirely', () => {
    const block = buildTaskContextBlock({
      profileText: null,
      activeTasks: [],
      completedTasks: [],
      goals: []
    })
    expect(block).toBe('')
  })

  it('renders an active task with no priority without a trailing bracket', () => {
    const block = buildTaskContextBlock({
      profileText: null,
      activeTasks: [{ id: 7, description: 'do thing', priority: null }],
      completedTasks: [],
      goals: []
    })
    expect(block).toContain('1. [id:7] do thing\n')
    expect(block).not.toContain('[id:7] do thing [')
  })
})
