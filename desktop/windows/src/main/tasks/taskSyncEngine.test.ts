// Sync-engine behavior tests. The engine is hermetic here: `electron` (net.fetch +
// BrowserWindow) and the storage wrappers (`../ipc/db`, a native better-sqlite3
// module that can't load under plain-node vitest) are mocked; the REAL
// core/session drives the epoch guard. Covers the ported Mac behaviors: local-first
// reads → throttled census-based background sync, reconcile hard-delete (+
// empty-guard + throttle), optimistic create/toggle/update/delete (markSynced /
// revert / keep-local), the FIX-ii deletion listener, and retryUnsynced.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActionItemRecord } from '../../shared/types'

// --- Hoisted mocks -----------------------------------------------------------
const h = vi.hoisted(() => {
  const jsonResponse = (data: unknown, ok = true, status = 200): unknown => ({
    ok,
    status,
    json: async () => data
  })
  // Mutable app_meta store keyed by flag name. A holder object (not a reassigned
  // binding) so the getAppMeta implementation below always reads the current
  // values across tests.
  const appMeta = { values: { tasksFullSyncCompleted_v2_u1: '1' } as Record<string, string> }
  return {
    jsonResponse,
    // Routed by HTTP method; individual tests override for failures/echoes.
    serverItems: [] as unknown[],
    // The ID census (GET /v1/action-items/ids?completed=…) per bucket.
    censusIncomplete: [] as string[],
    censusCompleted: [] as string[],
    // Per-id document store for GET /v1/action-items/{id} (census diff fetches).
    itemsById: {} as Record<string, Record<string, unknown>>,
    netFetch: vi.fn(),
    // storage wrappers
    getLocalActionItems: vi.fn((): ActionItemRecord[] => []),
    getFilteredActionItems: vi.fn((): ActionItemRecord[] => []),
    getSyncedActionItemIds: vi.fn((): { backendId: string; completed: boolean }[] => []),
    getUnsyncedActionItems: vi.fn((): ActionItemRecord[] => []),
    insertLocalActionItem: vi.fn(),
    updateCompletionStatus: vi.fn(),
    updateActionItemFields: vi.fn(),
    deleteActionItemByBackendId: vi.fn((): number[] => []),
    markSyncedActionItem: vi.fn(() => ({ merged: false, keptId: 0 })),
    syncTaskActionItems: vi.fn(() => ({ skipped: 0, adopted: 0, inserted: 0, updated: 0 })),
    hardDeleteAbsentTasks: vi.fn((): number[] => []),
    hardDeleteAbsentCompletedTasks: vi.fn((): number[] => []),
    appMeta,
    getAppMeta: vi.fn((key: string): string | null => appMeta.values[key] ?? null),
    setAppMeta: vi.fn(),
    // Event-driven promotion trigger (create.ts) — mocked so the engine's toggle/
    // delete promote calls are observable without pulling create's real deps.
    promoteIfNeeded: vi.fn(async () => {}),
    // `tasks:changed` broadcast spy — a fake window's webContents.send.
    send: vi.fn(),
    // 429-degraded signal — the completed-reconcile guard. Default: healthy.
    isBackendDegraded: vi.fn(() => false)
  }
})

vi.mock('electron', () => ({
  net: { fetch: h.netFetch },
  BrowserWindow: {
    getAllWindows: () => [{ isDestroyed: () => false, webContents: { send: h.send } }]
  }
}))

vi.mock('../ipc/db', () => ({
  getLocalActionItems: h.getLocalActionItems,
  getFilteredActionItems: h.getFilteredActionItems,
  getSyncedActionItemIds: h.getSyncedActionItemIds,
  getUnsyncedActionItems: h.getUnsyncedActionItems,
  insertLocalActionItem: h.insertLocalActionItem,
  updateCompletionStatus: h.updateCompletionStatus,
  updateActionItemFields: h.updateActionItemFields,
  deleteActionItemByBackendId: h.deleteActionItemByBackendId,
  markSyncedActionItem: h.markSyncedActionItem,
  syncTaskActionItems: h.syncTaskActionItems,
  hardDeleteAbsentTasks: h.hardDeleteAbsentTasks,
  hardDeleteAbsentCompletedTasks: h.hardDeleteAbsentCompletedTasks,
  getAppMeta: h.getAppMeta,
  setAppMeta: h.setAppMeta
}))

vi.mock('../assistants/tasks/create', () => ({ promoteIfNeeded: h.promoteIfNeeded }))
// The REAL core/session (used here) also imports noteBackendStatus from this
// module and calls it after every fetch — mock it as a no-op so the shared module
// mock doesn't strip it out and break session.ts's apiFetch.
vi.mock('../observability/backendDegraded', () => ({
  isBackendDegraded: h.isBackendDegraded,
  noteBackendStatus: vi.fn()
}))

// Firebase-ish token: payload decodes to a uid (used only to key the full-sync flag).
const TOKEN = `x.${Buffer.from(JSON.stringify({ user_id: 'u1' })).toString('base64')}.y`
const SESSION = {
  apiBase: 'https://api.example',
  desktopApiBase: 'https://desktop.example',
  token: TOKEN
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

function backendItem(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'b1',
    description: 'from server',
    completed: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...over
  }
}

// Default net.fetch: GET serves the census buckets, per-id documents, and the
// legacy full listing; writes echo a plausible item.
function defaultRoute(): void {
  h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
    const method = init?.method ?? 'GET'
    const u = String(url)
    if (method === 'GET') {
      if (u.includes('/v1/action-items/ids')) {
        return h.jsonResponse({
          ids: u.includes('completed=true') ? h.censusCompleted : h.censusIncomplete
        })
      }
      const byId = u.match(/\/v1\/action-items\/([^/?]+)$/)
      if (byId) {
        const item = h.itemsById[byId[1]]
        return item ? h.jsonResponse(item) : h.jsonResponse({ detail: 'nf' }, false, 404)
      }
      return h.jsonResponse({ action_items: h.serverItems, has_more: false })
    }
    if (method === 'POST') return h.jsonResponse(backendItem({ id: 'srv-new' }))
    if (method === 'PATCH') return h.jsonResponse(backendItem({ completed: true }))
    if (method === 'DELETE') return h.jsonResponse({}, true, 204)
    return h.jsonResponse({})
  })
}

// Request classifiers shared by the cost-guard tests.
type Call = [url: string, init: { method?: string } | undefined]
const asCalls = (calls: unknown[][]): Call[] => calls as Call[]
const methodOf = (c: Call): string => c[1]?.method ?? 'GET'
const urlOf = (c: Call): string => String(c[0])
const listingCalls = (): Call[] =>
  asCalls(h.netFetch.mock.calls).filter(
    (c) => methodOf(c) === 'GET' && urlOf(c).includes('/v1/action-items?')
  )
const censusCalls = (): Call[] =>
  asCalls(h.netFetch.mock.calls).filter(
    (c) => methodOf(c) === 'GET' && urlOf(c).includes('/v1/action-items/ids')
  )
const byIdCalls = (): Call[] =>
  asCalls(h.netFetch.mock.calls).filter(
    (c) => methodOf(c) === 'GET' && /\/v1\/action-items\/[^/?]+$/.test(urlOf(c))
  )

// Each test gets a fresh engine + session module pair (module-scoped state:
// lastReconcileAt, retrying, in-flight promises, deletionListener).
async function freshEngine(): Promise<{
  engine: typeof import('./taskSyncEngine')
  session: typeof import('../assistants/core/session')
}> {
  vi.resetModules()
  const session = await import('../assistants/core/session')
  const engine = await import('./taskSyncEngine')
  session.setBackendSession(SESSION)
  return { engine, session }
}

beforeEach(() => {
  vi.clearAllMocks()
  h.serverItems = [backendItem()]
  h.censusIncomplete = []
  h.censusCompleted = []
  h.itemsById = {}
  h.appMeta.values = { tasksFullSyncCompleted_v2_u1: '1' } // full-sync flag set by default
  h.getLocalActionItems.mockReturnValue([])
  h.getSyncedActionItemIds.mockReturnValue([])
  h.hardDeleteAbsentTasks.mockReturnValue([])
  h.hardDeleteAbsentCompletedTasks.mockReturnValue([])
  h.isBackendDegraded.mockReturnValue(false)
  defaultRoute()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => vi.restoreAllMocks())

describe('reads + throttled background sync (local-first)', () => {
  it('listIncomplete returns local rows immediately, then the background sync lands new backend rows', async () => {
    const local = [{ id: 1, description: 'local' } as unknown as ActionItemRecord]
    h.getLocalActionItems.mockReturnValue(local)
    h.censusIncomplete = ['b1']
    h.itemsById = { b1: backendItem({ id: 'b1' }) }
    const { engine } = await freshEngine()

    const rows = engine.listIncomplete()
    expect(rows).toBe(local) // instant local read
    expect(h.getLocalActionItems).toHaveBeenCalledWith({
      completed: false,
      limit: undefined,
      offset: undefined
    })

    await engine.scheduleBackgroundSync() // await the background run
    // Census diff: b1 is new locally → per-id GET → synced.
    expect(byIdCalls().map((c) => urlOf(c))).toEqual(['https://api.example/v1/action-items/b1'])
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1)
    const items = (h.syncTaskActionItems.mock.calls[0] as unknown[])[0]
    expect(items).toEqual([
      expect.objectContaining({ backendId: 'b1', description: 'from server', completed: false })
    ])
  })

  it('is a local-only no-op with no session (never touches the network)', async () => {
    const { engine, session } = await freshEngine()
    session.setBackendSession(null)

    engine.listIncomplete()
    await engine.scheduleBackgroundSync()

    expect(h.netFetch).not.toHaveBeenCalled()
    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
  })

  // Regression: a sync that changes nothing MUST NOT emit `tasks:changed`. The
  // renderer re-reads on that event, and pre-fix every read kicked another sync —
  // an unconditional broadcast turns steady state into an unbounded polling loop.
  it('a steady-state no-op sync fetches no documents and stays silent', async () => {
    h.censusIncomplete = ['b1']
    h.getSyncedActionItemIds.mockReturnValue([{ backendId: 'b1', completed: false }])
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(byIdCalls()).toHaveLength(0) // matching census → zero document reads
    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
    expect(h.send).not.toHaveBeenCalledWith('tasks:changed')
  })

  it('broadcasts tasks:changed when the sync actually changes a row', async () => {
    h.censusIncomplete = ['b1']
    h.itemsById = { b1: backendItem({ id: 'b1' }) }
    h.syncTaskActionItems.mockReturnValue({ skipped: 0, adopted: 0, inserted: 1, updated: 0 })
    const { engine } = await freshEngine()
    await engine.scheduleBackgroundSync()
    expect(h.send).toHaveBeenCalledWith('tasks:changed')
  })

  it('throttles: one background sync per 5-minute window however many reads ask', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    h.censusIncomplete = ['b1']
    h.getSyncedActionItemIds.mockReturnValue([{ backendId: 'b1', completed: false }])
    const { engine } = await freshEngine()

    engine.listIncomplete()
    engine.listCompleted()
    engine.dashboardSlices()
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(2) // exactly one census round (one per bucket)

    nowSpy.mockReturnValue(t0 + 60_000) // +1 min: reads are throttled away
    engine.listIncomplete()
    engine.listCompleted()
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(2)

    nowSpy.mockReturnValue(t0 + 5 * 60_000 + 1) // past the window
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(4) // second round
  })

  it('dedupes: concurrent schedule calls share the one in-flight run', async () => {
    h.censusIncomplete = ['b1']
    h.itemsById = { b1: backendItem({ id: 'b1' }) }
    const { engine } = await freshEngine()
    const a = engine.scheduleBackgroundSync()
    const b = engine.scheduleBackgroundSync()
    await Promise.all([a, b])
    expect(censusCalls()).toHaveLength(2)
  })
})

describe('reconcile (hardDeleteAbsentTasks, census-driven)', () => {
  it('hard-deletes tasks absent from the census and evicts them (FIX ii)', async () => {
    h.censusIncomplete = ['b1']
    h.getSyncedActionItemIds.mockReturnValue([
      { backendId: 'b1', completed: false },
      { backendId: 'gone', completed: false }
    ])
    h.hardDeleteAbsentTasks.mockReturnValue([42])
    const { engine } = await freshEngine()
    const evicted: unknown[] = []
    engine.setTaskDeletionListener((d) => evicted.push(...d))

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
    expect(evicted).toEqual([{ source: 'action_item', id: 42 }])
  })

  it('empty-guard: when the store deletes nothing, the deletion listener is not called', async () => {
    h.censusIncomplete = ['b1']
    h.hardDeleteAbsentTasks.mockReturnValue([])
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
    expect(listener).not.toHaveBeenCalled()
  })

  it('empty census never wipes local rows (the storage empty-guard holds)', async () => {
    // Local rows exist; both census buckets come back empty. The reconcile must
    // not hand storage an empty sweep that could drop everything.
    h.getSyncedActionItemIds.mockReturnValue([{ backendId: 'b1', completed: false }])
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith([]) // storage no-ops on []
    expect(h.hardDeleteAbsentCompletedTasks).toHaveBeenCalledWith([], expect.any(Number))
    expect(h.deleteActionItemByBackendId).not.toHaveBeenCalled()
  })
})

describe('completed-phantom reconcile (hardDeleteAbsentCompletedTasks, census-driven)', () => {
  it('reconciles a completed row absent from the completed census + evicts it', async () => {
    h.censusCompleted = ['b1']
    h.hardDeleteAbsentCompletedTasks.mockReturnValue([77])
    const { engine } = await freshEngine()
    const evicted: unknown[] = []
    engine.setTaskDeletionListener((d) => evicted.push(...d))

    await engine.scheduleBackgroundSync()

    // Called with the census's completed ids; its deletions are evicted from
    // the embedding index + broadcast.
    expect(h.hardDeleteAbsentCompletedTasks).toHaveBeenCalledWith(['b1'], expect.any(Number))
    expect(evicted).toEqual([{ source: 'action_item', id: 77 }])
    expect(h.send).toHaveBeenCalledWith('tasks:changed')
  })

  it('empty-guard: a deletion of nothing does not fire the listener or broadcast', async () => {
    h.censusCompleted = ['b1']
    h.hardDeleteAbsentCompletedTasks.mockReturnValue([])
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentCompletedTasks).toHaveBeenCalledWith(['b1'], expect.any(Number))
    expect(listener).not.toHaveBeenCalled()
    expect(h.send).not.toHaveBeenCalledWith('tasks:changed')
  })

  // The mass-flip guard: a 429 storm can return a thin/partial list, so the
  // delete-by-absence sweep MUST be skipped entirely while degraded.
  it('SKIPS the completed reconcile in the 429-degraded state', async () => {
    h.censusCompleted = ['b1']
    h.isBackendDegraded.mockReturnValue(true)
    h.hardDeleteAbsentCompletedTasks.mockReturnValue([77]) // would delete if it ran
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentCompletedTasks).not.toHaveBeenCalled()
    expect(listener).not.toHaveBeenCalled()
  })

  // THE fail-closed regression: the sweep must NEVER run off an incomplete
  // picture of the backend. A census request that fails (500/429) makes the
  // whole round abort — no sync, no delete-by-absence off a partial census.
  it('fail-closed: a failed census aborts the round (no sync, no reconcile, no wipe)', async () => {
    h.hardDeleteAbsentCompletedTasks.mockReturnValue([99]) // would delete a real row if ever called
    h.hardDeleteAbsentTasks.mockReturnValue([98])
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if ((init?.method ?? 'GET') !== 'GET') return h.jsonResponse({})
      if (String(url).includes('/v1/action-items/ids')) return h.jsonResponse({}, false, 500)
      return h.jsonResponse({ action_items: [backendItem()], has_more: false })
    })
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    await engine.scheduleBackgroundSync() // swallows the census error

    expect(h.hardDeleteAbsentTasks).not.toHaveBeenCalled()
    expect(h.hardDeleteAbsentCompletedTasks).not.toHaveBeenCalled()
    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
    expect(listener).not.toHaveBeenCalled()
  })
})

describe('optimistic create', () => {
  it('inserts locally, returns the row, and marks it synced on POST success', async () => {
    h.insertLocalActionItem.mockReturnValue({ id: 7 } as unknown as ActionItemRecord)
    const { engine } = await freshEngine()

    const rec = engine.createTask({ description: 'buy milk' })
    expect(rec).toEqual({ id: 7 })
    expect(h.insertLocalActionItem).toHaveBeenCalledWith(
      expect.objectContaining({ description: 'buy milk', source: 'manual', completed: false })
    )

    await flush()
    expect(h.markSyncedActionItem).toHaveBeenCalledWith(7, 'srv-new', expect.any(Number))
  })

  it('stays unsynced on POST failure (no revert, no markSynced)', async () => {
    h.insertLocalActionItem.mockReturnValue({ id: 7 } as unknown as ActionItemRecord)
    h.netFetch.mockImplementation(async () => h.jsonResponse({}, false, 500))
    const { engine } = await freshEngine()

    engine.createTask({ description: 'buy milk' })
    await flush()

    expect(h.markSyncedActionItem).not.toHaveBeenCalled()
    expect(h.deleteActionItemByBackendId).not.toHaveBeenCalled() // never reverted
  })
})

describe('optimistic toggle', () => {
  it('reverts the local completion when the PATCH fails', async () => {
    h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
      if (init?.method === 'PATCH') return h.jsonResponse({}, false, 500)
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    const { engine } = await freshEngine()

    engine.toggleTask('b1', true)
    expect(h.updateCompletionStatus).toHaveBeenCalledWith('b1', true, expect.any(Number)) // optimistic

    await flush()
    // Revert = set completion back to the previous value.
    expect(h.updateCompletionStatus).toHaveBeenLastCalledWith('b1', false, expect.any(Number))
    expect(h.updateCompletionStatus).toHaveBeenCalledTimes(2)
  })

  it('absorbs the server echo on PATCH success (no revert)', async () => {
    const { engine } = await freshEngine()

    engine.toggleTask('b1', true)
    await flush()

    expect(h.updateCompletionStatus).toHaveBeenCalledTimes(1) // no revert
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1) // echo absorbed
  })
})

describe('optimistic update', () => {
  it('keeps the local edit when the PATCH fails (no revert)', async () => {
    h.netFetch.mockImplementation(async () => h.jsonResponse({}, false, 500))
    const { engine } = await freshEngine()

    engine.updateTask('b1', { description: 'edited' })
    expect(h.updateActionItemFields).toHaveBeenCalledWith(
      'b1',
      { description: 'edited' },
      expect.any(Number)
    )

    await flush()
    expect(h.updateActionItemFields).toHaveBeenCalledTimes(1) // not undone
  })
})

describe('optimistic delete', () => {
  it('hard-deletes locally, fires the deletion listener with the ids, and keeps the deletion on DELETE failure', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    h.netFetch.mockImplementation(async () => h.jsonResponse({}, false, 500))
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    engine.deleteTask('b1')
    expect(h.deleteActionItemByBackendId).toHaveBeenCalledWith('b1', 'user')
    expect(listener).toHaveBeenCalledWith([{ source: 'action_item', id: 9 }])

    await flush()
    // keep-local-deleted: nothing re-inserted, delete not retried/undone.
    expect(h.deleteActionItemByBackendId).toHaveBeenCalledTimes(1)
    expect(h.insertLocalActionItem).not.toHaveBeenCalled()
  })

  it('a background sync during an in-flight delete does not resurrect the row (passes the tombstone guard)', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    // DELETE never resolves → the tombstone stays set while the sync runs.
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const method = init?.method ?? 'GET'
      const u = String(url)
      if (method === 'DELETE') return new Promise(() => {}) // hang forever
      if (u.includes('/v1/action-items/ids')) return h.jsonResponse({ ids: ['b1'] })
      return h.jsonResponse(backendItem({ id: 'b1' })) // the per-id census fetch
    })
    const { engine } = await freshEngine()
    engine.deleteTask('b1') // sets the tombstone
    await engine.scheduleBackgroundSync()
    // The sync's item fetch carries a guard that reports the deleted id as pending,
    // so the storage insert branch skips it (proven against a real DB in dbTasks.test).
    const lastSync = h.syncTaskActionItems.mock.calls.at(-1) as unknown as
      | [unknown, { isTombstoned?: (id: string) => boolean }]
      | undefined
    expect(lastSync?.[1]?.isTombstoned?.('b1')).toBe(true)
  })

  it('verify: a failed delete whose task is still on the server restores the row + signals failure', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
      const method = init?.method ?? 'GET'
      if (method === 'DELETE') return h.jsonResponse({}, false, 429) // storm: delete rejected
      if (method === 'GET') return h.jsonResponse(backendItem({ id: 'b1' })) // still present
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()
    engine.deleteTask('b1')
    await flush()
    // Restored through the normal sync path…
    const restore = h.syncTaskActionItems.mock.calls.at(-1) as unknown as
      | [{ backendId: string }[], unknown]
      | undefined
    expect(restore?.[0]?.[0]?.backendId).toBe('b1')
    // …and the failure is surfaced (not silent), and the tombstone retired.
    expect(h.send).toHaveBeenCalledWith('tasks:opFailed', expect.objectContaining({ op: 'delete' }))
    expect(engine.__isTombstonedForTest('b1')).toBe(false)
  })

  it('verify: a failed delete whose task is GONE stays deleted and clears the tombstone', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
      const method = init?.method ?? 'GET'
      if (method === 'DELETE') return h.jsonResponse({}, false, 429)
      if (method === 'GET') return h.jsonResponse({ detail: 'not found' }, false, 404) // gone
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()
    engine.deleteTask('b1')
    await flush()
    expect(h.syncTaskActionItems).not.toHaveBeenCalled() // no restore
    expect(h.send).not.toHaveBeenCalledWith('tasks:opFailed', expect.anything())
    expect(engine.__isTombstonedForTest('b1')).toBe(false) // guard cleared (delete stuck)
  })

  // MAJOR fix: when the DELETE AND the first verify GET are both inconclusive (429
  // storm), the delete must be RE-VERIFIED later — not left to silently resurrect at
  // TTL. Both later outcomes are exercised: still-present → restore + toast;
  // gone → stays deleted. Uses fake timers to cross the re-verify backoff.
  describe('inconclusive-delete re-verify (MAJOR)', () => {
    it('re-verifies a 429/429 delete and RESTORES + signals when it is later still present', async () => {
      vi.useFakeTimers()
      const rnd = vi.spyOn(Math, 'random').mockReturnValue(0) // deterministic backoff
      h.deleteActionItemByBackendId.mockReturnValue([9])
      let getCount = 0
      h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
        const method = init?.method ?? 'GET'
        if (method === 'DELETE') return h.jsonResponse({}, false, 429)
        if (method === 'GET') {
          getCount++
          if (getCount === 1) return h.jsonResponse({}, false, 429) // first verify inconclusive
          return h.jsonResponse(backendItem({ id: 'b1' })) // re-verify: still present
        }
        return h.jsonResponse({})
      })
      const { engine } = await freshEngine()
      engine.deleteTask('b1')
      await vi.advanceTimersByTimeAsync(0) // DELETE 429 → verify 429 → schedule re-verify
      expect(engine.__isTombstonedForTest('b1')).toBe(true) // held, not resolved
      expect(h.send).not.toHaveBeenCalledWith('tasks:opFailed', expect.anything())

      await vi.advanceTimersByTimeAsync(16_000) // fire the re-verify (15s + jitter)
      expect(h.syncTaskActionItems).toHaveBeenCalled() // restored
      expect(h.send).toHaveBeenCalledWith(
        'tasks:opFailed',
        expect.objectContaining({ op: 'delete' })
      )
      expect(engine.__isTombstonedForTest('b1')).toBe(false)

      rnd.mockRestore()
      vi.useRealTimers()
    })

    it('re-verifies a 429/429 delete and STAYS deleted when it is later confirmed gone', async () => {
      vi.useFakeTimers()
      const rnd = vi.spyOn(Math, 'random').mockReturnValue(0)
      h.deleteActionItemByBackendId.mockReturnValue([9])
      let getCount = 0
      h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
        const method = init?.method ?? 'GET'
        if (method === 'DELETE') return h.jsonResponse({}, false, 429)
        if (method === 'GET') {
          getCount++
          if (getCount === 1) return h.jsonResponse({}, false, 429) // inconclusive
          return h.jsonResponse({ detail: 'not found' }, false, 404) // re-verify: gone
        }
        return h.jsonResponse({})
      })
      const { engine } = await freshEngine()
      engine.deleteTask('b1')
      await vi.advanceTimersByTimeAsync(0)
      expect(engine.__isTombstonedForTest('b1')).toBe(true)

      await vi.advanceTimersByTimeAsync(16_000) // re-verify → 404
      expect(h.syncTaskActionItems).not.toHaveBeenCalled() // no restore
      expect(h.send).not.toHaveBeenCalledWith('tasks:opFailed', expect.anything())
      expect(engine.__isTombstonedForTest('b1')).toBe(false) // cleared, stays deleted

      rnd.mockRestore()
      vi.useRealTimers()
    })
  })

  it('resetPendingDeletes drops tombstones (cross-account hygiene on sign-out)', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    // Keep the DELETE pending so the tombstone stays set.
    h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
      if ((init?.method ?? 'GET') === 'DELETE') return new Promise(() => {})
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()
    engine.deleteTask('b1')
    expect(engine.__isTombstonedForTest('b1')).toBe(true)
    engine.resetPendingDeletes()
    expect(engine.__isTombstonedForTest('b1')).toBe(false)
  })
})

describe('retryUnsynced', () => {
  it('re-POSTs each unsynced create and marks it synced', async () => {
    h.getUnsyncedActionItems.mockReturnValue([
      {
        id: 3,
        description: 'x',
        completed: false,
        dueAt: null,
        conversationId: null
      } as unknown as ActionItemRecord
    ])
    const { engine } = await freshEngine()

    await engine.retryUnsynced()

    const posts = h.netFetch.mock.calls.filter(
      (c) => (c[1] as { method?: string })?.method === 'POST'
    )
    expect(posts).toHaveLength(1)
    expect(h.markSyncedActionItem).toHaveBeenCalledWith(3, 'srv-new', expect.any(Number))
  })

  it('does nothing without a session', async () => {
    h.getUnsyncedActionItems.mockReturnValue([
      { id: 3, description: 'x', completed: false } as unknown as ActionItemRecord
    ])
    const { engine, session } = await freshEngine()
    session.setBackendSession(null)

    await engine.retryUnsynced()

    expect(h.netFetch).not.toHaveBeenCalled()
    expect(h.markSyncedActionItem).not.toHaveBeenCalled()
  })
})

describe('event-driven promotion (Mac TasksStore complete/delete triggers)', () => {
  it('completing a task fires a promote (vacated slot → pull the next staged task up)', async () => {
    const { engine } = await freshEngine()
    engine.toggleTask('b1', true)
    await flush()
    expect(h.promoteIfNeeded).toHaveBeenCalledTimes(1)
  })

  it('un-completing a task does NOT fire a promote (Mac triggers on complete only)', async () => {
    const { engine } = await freshEngine()
    engine.toggleTask('b1', false)
    await flush()
    expect(h.promoteIfNeeded).not.toHaveBeenCalled()
  })

  it('deleting a task fires a promote', async () => {
    h.deleteActionItemByBackendId.mockReturnValue([9])
    const { engine } = await freshEngine()
    engine.deleteTask('b1')
    await flush()
    expect(h.promoteIfNeeded).toHaveBeenCalledTimes(1)
  })

  it('the promote is fire-and-forget — a toggle FAILURE still reverts regardless', async () => {
    // promoteIfNeeded runs alongside the toggle; even if it never resolved, the
    // toggle's own revert-on-PATCH-failure path is independent and must still fire.
    h.promoteIfNeeded.mockReturnValue(new Promise(() => {})) // never settles
    h.netFetch.mockImplementation(async (_u: string, init?: { method?: string }) => {
      if (init?.method === 'PATCH') return h.jsonResponse({}, false, 500)
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    const { engine } = await freshEngine()

    engine.toggleTask('b1', true)
    expect(h.updateCompletionStatus).toHaveBeenCalledWith('b1', true, expect.any(Number))
    await flush()
    // Revert happened despite the never-settling promote.
    expect(h.updateCompletionStatus).toHaveBeenLastCalledWith('b1', false, expect.any(Number))
    expect(h.promoteIfNeeded).toHaveBeenCalledTimes(1)
  })
})

describe('one-time full sync (versioned flag)', () => {
  it('pages everything once when the flag is unset, then persists the flag (sweeps census-capped)', async () => {
    h.appMeta.values = {} // flag unset → full populate due
    h.censusIncomplete = ['b1']
    h.censusCompleted = []
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(h.setAppMeta).toHaveBeenCalledWith('tasksFullSyncCompleted_v2_u1', '1')
    // Both completed=false and completed=true pages were fetched for content…
    const urls = listingCalls().map(urlOf)
    expect(urls.some((u) => u.includes('completed=true'))).toBe(true)
    expect(urls.some((u) => u.includes('completed=false'))).toBe(true)
    expect(urls.every((u) => u.includes('limit=100'))).toBe(true)
    expect(urls.some((u) => u.includes('limit=500'))).toBe(false)
    // …and the forced sweeps took their keep-set from the (uncapped) census.
    expect(censusCalls()).toHaveLength(2)
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
  })

  it('full-sync sweeps keep listing-capped tail rows (census is the uncapped authority)', async () => {
    // A >2000-doc account: the listing is hard-capped server-side and reports
    // has_more=false, so the listing ids must NEVER drive the forced sweeps.
    h.appMeta.values = {}
    h.censusIncomplete = ['tail1', 'tail2'] // census sees past the cap
    h.censusCompleted = []
    h.serverItems = [] // the (capped) listing delivered nothing
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['tail1', 'tail2'])
    expect(h.deleteActionItemByBackendId).not.toHaveBeenCalled()
  })

  it('re-runs once for existing installs after the v1 → v2 bump (drift repair)', async () => {
    // v1 flag set by a pre-fix install, v2 unset → one more full populate.
    h.appMeta.values = { tasksFullSyncCompleted_v1_u1: '1' }
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(h.setAppMeta).toHaveBeenCalledWith('tasksFullSyncCompleted_v2_u1', '1')
    expect(listingCalls().length).toBeGreaterThan(0)
  })
})

describe('census diff (the steady-state cut)', () => {
  it('fetches ONLY new and bucket-moved ids — unchanged ids cost zero document reads', async () => {
    h.censusIncomplete = ['a', 'b'] // a is known-incomplete, b is new
    h.censusCompleted = ['c', 'd'] // c is known-completed, d is new
    h.getSyncedActionItemIds.mockReturnValue([
      { backendId: 'a', completed: false },
      { backendId: 'c', completed: true }
    ])
    h.itemsById = {
      b: backendItem({ id: 'b' }),
      d: backendItem({ id: 'd', completed: true })
    }
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(
      byIdCalls()
        .map((c) => urlOf(c))
        .sort()
    ).toEqual(['https://api.example/v1/action-items/b', 'https://api.example/v1/action-items/d'])
    const synced = (h.syncTaskActionItems.mock.calls[0] as unknown[])[0] as {
      backendId: string
    }[]
    expect(synced.map((i) => i.backendId).sort()).toEqual(['b', 'd'])
  })

  it('a remotely toggled id (bucket move) is fetched, flipped, and kept by the UNION keep-set', async () => {
    // b1 was incomplete locally; the backend moved it to completed.
    h.censusIncomplete = []
    h.censusCompleted = ['b1']
    h.getSyncedActionItemIds.mockReturnValue([{ backendId: 'b1', completed: false }])
    h.itemsById = { b1: backendItem({ id: 'b1', completed: true }) }
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    // The authoritative doc landed with the remote bucket…
    const synced = (h.syncTaskActionItems.mock.calls[0] as unknown[])[0] as {
      backendId: string
      completed: boolean
    }[]
    expect(synced).toEqual([expect.objectContaining({ backendId: 'b1', completed: true })])
    // …and BOTH sweeps ran against the census UNION, so the (now flipped) row is
    // in the keep-set either way — never delete-by-absence'd by its old bucket.
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
    expect(h.hardDeleteAbsentCompletedTasks).toHaveBeenCalledWith(['b1'], expect.any(Number))
  })

  // Swarm must-fix regression: a mover whose per-id GET failed (or was cut by
  // MAX_CENSUS_LOOKUPS) is PROVEN LIVE by the other bucket's census — the union
  // keep-set must hold it for the next tick instead of letting its old bucket's
  // sweep hard-delete it (which would destroy local-only fields on re-insert).
  it('a bucket-moved row whose per-id GET FAILS is kept (union keep-set), not deleted', async () => {
    h.censusIncomplete = ['x'] // non-empty old bucket — the dangerous case
    h.censusCompleted = ['b1'] // b1 moved here remotely
    h.getSyncedActionItemIds.mockReturnValue([
      { backendId: 'b1', completed: false },
      { backendId: 'x', completed: false }
    ])
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET') {
        if (u.includes('completed=true')) return h.jsonResponse({ ids: h.censusCompleted })
        if (u.includes('/v1/action-items/ids')) return h.jsonResponse({ ids: h.censusIncomplete })
        if (u.endsWith('/b1')) return h.jsonResponse({}, false, 503) // the flip fails
        return h.jsonResponse(backendItem({ id: 'x' }))
      }
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    // The sweep keep-set is the UNION: b1 is present in the completed census, so
    // the active-row sweep must NOT see it as absent.
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['x', 'b1'])
    expect(h.hardDeleteAbsentCompletedTasks).toHaveBeenCalledWith(['x', 'b1'], expect.any(Number))
  })

  it('a mover cut by MAX_CENSUS_LOOKUPS is kept the same way (no delete past the cap)', async () => {
    // 201 rows all moved buckets remotely; only 200 per-id GETs are allowed.
    const movers = Array.from({ length: 201 }, (_, i) => `m${i}`)
    h.censusIncomplete = []
    h.censusCompleted = movers
    h.getSyncedActionItemIds.mockReturnValue(
      movers.map((id) => ({ backendId: id, completed: false }))
    )
    h.itemsById = Object.fromEntries(movers.map((id) => [id, backendItem({ id, completed: true })]))
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(byIdCalls()).toHaveLength(200) // the cap
    // …but the sweep keep-set still carries every mover id (union), so the one
    // un-flipped row survives to the next tick.
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(expect.arrayContaining(movers))
  })

  it('a 404 on a census-fetched id is skipped (the reconciles handle absence)', async () => {
    h.censusIncomplete = ['gone']
    // No itemsById entry → per-id GET 404s.
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['gone']) // absent → sweep decides
  })

  // Swarm should-fix regression: a LOCKED item (backend 402 'paid plan required'
  // on the per-id GET) must not become a per-round zombie that re-bills forever
  // and starves MAX_CENSUS_LOOKUPS — it is negative-cached until its TTL.
  it('a 402 (locked) per-id GET is skipped on subsequent syncs until its TTL', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    let lockedGets = 0
    h.censusIncomplete = ['locked', 'fresh']
    h.getSyncedActionItemIds.mockReturnValue([]) // both ids are new locally
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET') {
        if (u.includes('completed=true')) return h.jsonResponse({ ids: [] })
        if (u.includes('/v1/action-items/ids')) return h.jsonResponse({ ids: h.censusIncomplete })
        if (u.endsWith('/locked')) {
          lockedGets++
          return h.jsonResponse({ detail: 'paid plan required' }, false, 402)
        }
        return h.jsonResponse(backendItem({ id: 'fresh' }))
      }
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()
    expect(lockedGets).toBe(1) // tried once…
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1) // …and the fresh id still synced

    nowSpy.mockReturnValue(t0 + 5 * 60_000 + 1) // next window: still inside the TTL
    await engine.scheduleBackgroundSync()
    expect(lockedGets).toBe(1) // not re-billed

    nowSpy.mockReturnValue(t0 + 61 * 60_000) // TTL expired (plan may have changed)
    await engine.scheduleBackgroundSync()
    expect(lockedGets).toBe(2) // retried
  })

  it('one unreadable id does not abort the round — the rest still sync', async () => {
    h.censusIncomplete = ['bad', 'ok']
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET') {
        if (u.includes('completed=true')) return h.jsonResponse({ ids: [] })
        if (u.includes('/v1/action-items/ids')) return h.jsonResponse({ ids: h.censusIncomplete })
        if (u.endsWith('/bad')) return h.jsonResponse({}, false, 500)
        return h.jsonResponse(backendItem({ id: 'ok' }))
      }
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()

    const synced = (h.syncTaskActionItems.mock.calls[0] as unknown[])[0] as {
      backendId: string
    }[]
    expect(synced.map((i) => i.backendId)).toEqual(['ok'])
  })

  it('caps per-sync lookups and converges the remainder on the next window', async () => {
    const ids = Array.from({ length: 201 }, (_, i) => `n${i}`)
    h.censusIncomplete = ids
    h.itemsById = Object.fromEntries(ids.map((id) => [id, backendItem({ id })]))
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync()
    expect(byIdCalls()).toHaveLength(200) // MAX_CENSUS_LOOKUPS

    // Storage has now absorbed the first 200 (this test plays storage's role);
    // only the 1 leftover is still "new" for the next window's diff.
    h.getSyncedActionItemIds.mockReturnValue(
      ids.slice(0, 200).map((id) => ({ backendId: id, completed: false }))
    )
    nowSpy.mockReturnValue(t0 + 5 * 60_000 + 1)
    await engine.scheduleBackgroundSync()
    expect(byIdCalls()).toHaveLength(201) // 200 + the 1 leftover picked up
  })
})

describe('failure retry floor + timer', () => {
  it('a sync that got NO backend response (offline) retries after 30s; a served one waits the window', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    let offline = true
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET' && u.includes('/v1/action-items/ids') && offline) {
        throw new TypeError('net offline') // NO response — nothing billed
      }
      if ((init?.method ?? 'GET') === 'GET' && u.includes('/v1/action-items/ids')) {
        return h.jsonResponse({ ids: [] })
      }
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    const { engine } = await freshEngine()

    await engine.scheduleBackgroundSync() // offline: fails with no response
    nowSpy.mockReturnValue(t0 + 31_000)
    offline = false
    await engine.scheduleBackgroundSync() // within the 5-min window but past the retry floor
    expect(censusCalls()).toHaveLength(3) // 1 offline attempt + the online round's 2

    // Served-response failure: the reads are already billed, so the SAME 30s
    // shortcut must NOT re-buy a round (a partially-failing backend would be
    // re-scanned every 30s).
    let secondCensusFails = false
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET' && u.includes('/v1/action-items/ids')) {
        if (u.includes('completed=true') && secondCensusFails) {
          return h.jsonResponse({}, false, 500) // a RESPONSE — billed
        }
        return h.jsonResponse({ ids: [] })
      }
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    nowSpy.mockReturnValue(t0 + 331_000) // fresh window (online round stamped at +31s)
    secondCensusFails = true
    await engine.scheduleBackgroundSync() // census #1 served, census #2 500s
    expect(censusCalls()).toHaveLength(5) // 3 + 2 in the failed round
    nowSpy.mockReturnValue(t0 + 363_000) // 30s later — inside the window
    secondCensusFails = false
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(5) // NO 30s re-buy after a served response
  })

  // Swarm note regression: a sync that fails BECAUSE the session went away (the
  // abort lands in the catch) must not re-stamp the throttle window — sign-out
  // zeroed it via the session reset, and re-stamping would defer the NEXT
  // account's first sync (leaving it reading the previous account's rows).
  it('a sign-out mid-failed sync does not defer the next account’s first sync', async () => {
    h.netFetch.mockImplementation(
      async (url: string, init?: { method?: string; signal?: AbortSignal }) => {
        if ((init?.method ?? 'GET') === 'GET' && String(url).includes('/v1/action-items/ids')) {
          // Hang until the session abort kills the request (like real net.fetch).
          const { promise, reject } = Promise.withResolvers<unknown>()
          init?.signal?.addEventListener('abort', () => reject(new Error('aborted')))
          return promise
        }
        return h.jsonResponse({ action_items: [], has_more: false })
      }
    )
    const { engine, session } = await freshEngine()
    const pending = engine.scheduleBackgroundSync()
    // Sign-out: epoch bump + the app-wired reset (index.ts onSessionReset →
    // resetPendingDeletes) zeroes the throttle stamps.
    session.setBackendSession(null)
    engine.resetPendingDeletes()
    await pending.catch(() => {})

    // The next account signs in and reads: its first sync must run immediately.
    session.setBackendSession(SESSION)
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      if ((init?.method ?? 'GET') === 'GET' && String(url).includes('/v1/action-items/ids')) {
        return h.jsonResponse({ ids: [] })
      }
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(2) // the new account's round ran NOW
  })

  it('startTaskBackgroundSync ticks a throttled census; a signed-out app stays idle', async () => {
    const fresh = await freshEngine()
    vi.useFakeTimers()
    try {
      fresh.engine.startTaskBackgroundSync()

      // No session → the tick no-ops.
      fresh.session.setBackendSession(null)
      await vi.advanceTimersByTimeAsync(5 * 60_000)
      expect(h.netFetch).not.toHaveBeenCalled()

      fresh.session.setBackendSession(SESSION)
      await vi.advanceTimersByTimeAsync(5 * 60_000)
      expect(censusCalls()).toHaveLength(2) // one round per tick
      await vi.advanceTimersByTimeAsync(5 * 60_000)
      expect(censusCalls()).toHaveLength(4)
    } finally {
      fresh.engine.__stopTaskBackgroundSyncForTest()
      vi.useRealTimers()
    }
  })
})

describe('explicit reconcile (strong path, tasks:reconcile)', () => {
  it('full-lists both buckets, force-reconciles against the census, and restarts the throttle window', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    h.getSyncedActionItemIds.mockReturnValue([{ backendId: 'b1', completed: false }])
    h.censusIncomplete = ['b1']
    const { engine } = await freshEngine()

    await engine.reconcile()

    // The strong path pages both full listings for content…
    expect(listingCalls().length).toBeGreaterThanOrEqual(2)
    expect(listingCalls().map(urlOf).every((u) => u.includes('limit=100'))).toBe(true)
    // …censuses for the sweep keep-set (uncapped, unlike the 2000-doc listing
    // cap), and its reconciles are forced (run even at t0, where a throttled
    // call would have skipped).
    expect(censusCalls()).toHaveLength(2)
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])

    // Fresh data just landed: the background window restarts, so an immediate
    // scheduleBackgroundSync is throttled away instead of censusing over it.
    nowSpy.mockReturnValue(t0 + 10_000)
    await engine.scheduleBackgroundSync()
    expect(censusCalls()).toHaveLength(2)
  })

  it('dedupes concurrent reconciles', async () => {
    const { engine } = await freshEngine()
    const a = engine.reconcile()
    const b = engine.reconcile()
    await Promise.all([a, b])
    expect(listingCalls()).toHaveLength(2) // one run's worth (incomplete + completed)
  })

  it('pages at 100 and advances offset by delivered items, not a stale 500 step', async () => {
    h.appMeta.values = {}
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const method = init?.method ?? 'GET'
      const u = String(url)
      if (method === 'GET' && u.includes('/v1/action-items/ids')) {
        return h.jsonResponse({
          ids: u.includes('completed=true') ? [] : ['i0', 'i1']
        })
      }
      if (method === 'GET' && u.includes('/v1/action-items?')) {
        if (u.includes('completed=false') && u.includes('offset=0')) {
          expect(u).toContain('limit=100')
          return h.jsonResponse({
            action_items: [backendItem({ id: 'i0' })],
            has_more: true
          })
        }
        if (u.includes('completed=false') && u.includes('offset=1')) {
          return h.jsonResponse({
            action_items: [backendItem({ id: 'i1' })],
            has_more: false
          })
        }
        if (u.includes('completed=false') && u.includes('offset=100')) {
          throw new Error('offset advanced by PAGE_LIMIT instead of delivered length')
        }
        return h.jsonResponse({ action_items: [], has_more: false })
      }
      if (method === 'POST') return h.jsonResponse(backendItem({ id: 'srv-new' }))
      if (method === 'PATCH') return h.jsonResponse(backendItem({ completed: true }))
      if (method === 'DELETE') return h.jsonResponse({}, true, 204)
      return h.jsonResponse({})
    })
    const { engine } = await freshEngine()
    await engine.scheduleBackgroundSync()
    const incompleteOffsets = listingCalls()
      .map(urlOf)
      .filter((u) => u.includes('completed=false'))
    expect(incompleteOffsets.some((u) => u.includes('offset=1'))).toBe(true)
    expect(incompleteOffsets.some((u) => u.includes('offset=100'))).toBe(false)
  })

  it('a listing abort during populate does not retry the same dual-bucket fetch at 30s', async () => {
    h.appMeta.values = {}
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    h.netFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
      const u = String(url)
      if ((init?.method ?? 'GET') === 'GET' && u.includes('/v1/action-items?')) {
        const err = new Error('aborted')
        err.name = 'AbortError'
        throw err
      }
      if ((init?.method ?? 'GET') === 'GET' && u.includes('/v1/action-items/ids')) {
        return h.jsonResponse({ ids: [] })
      }
      return h.jsonResponse({ action_items: [], has_more: false })
    })
    const { engine } = await freshEngine()
    await engine.scheduleBackgroundSync()
    const listingsAfterFirst = listingCalls().length
    expect(listingsAfterFirst).toBeGreaterThan(0)
    nowSpy.mockReturnValue(t0 + 31_000)
    await engine.scheduleBackgroundSync()
    expect(listingCalls()).toHaveLength(listingsAfterFirst)
  })
})

// The deterministic cost guard. The script mirrors what the renderer actually
// does over 5 minutes of Tasks use (mount reads; every `tasks:changed` broadcast
// re-reads from the Tasks page, the Hub stats hook, and the Quick Task widget;
// then a toggle, a create, and a rename). Under origin/main EVERY one of these
// reads kicked a paged `GET /v1/action-items?limit=100` hydrate — measured by
// running the identical flushed script against an origin/main worktree:
// 22 listing requests / 500 listing documents / 25 requests total, vs 0 / 0 / 5
// on this branch (see the PR body's before/after request log).
describe('steady-state cost guard (scripted 5-min UI session)', () => {
  it('makes ZERO full-listing requests and ≤2 census requests; only mutations hit the backend', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    h.insertLocalActionItem.mockReturnValue({ id: 99 } as unknown as ActionItemRecord)
    // Populated steady state: 30 incomplete + 10 completed synced rows, census
    // buckets matching exactly (no remote changes during the window).
    const local = [
      ...Array.from({ length: 30 }, (_, i) => ({ backendId: `i${i}`, completed: false })),
      ...Array.from({ length: 10 }, (_, i) => ({ backendId: `c${i}`, completed: true }))
    ]
    h.getSyncedActionItemIds.mockReturnValue(local)
    h.censusIncomplete = local.filter((r) => !r.completed).map((r) => r.backendId)
    h.censusCompleted = local.filter((r) => r.completed).map((r) => r.backendId)
    const { engine } = await freshEngine()

    // --- the script (renderer-faithful read/mutation pattern) ---
    // Mount: Tasks page (incomplete + completed), Hub stats (incomplete +
    // completed), Quick Task widget (incomplete).
    engine.listIncomplete()
    engine.listCompleted()
    engine.dashboardSlices()
    await flush()
    // User: view incomplete, switch to completed, open the dashboard.
    engine.listIncomplete()
    engine.listCompleted()
    engine.dashboardSlices()
    await flush()
    // Toggle → broadcast → the three subscribers re-read.
    engine.toggleTask('i0', true)
    await flush()
    for (let i = 0; i < 5; i++) {
      engine.listIncomplete()
      engine.listCompleted()
    }
    // Create → broadcast → re-reads.
    engine.createTask({ description: 'new task' })
    await flush()
    for (let i = 0; i < 5; i++) {
      engine.listIncomplete()
      engine.listCompleted()
    }
    // Rename → broadcast → re-reads.
    engine.updateTask('i1', { description: 'renamed' })
    await flush()
    for (let i = 0; i < 5; i++) {
      engine.listIncomplete()
      engine.listCompleted()
    }
    // The window ends just before the timer's second tick.
    nowSpy.mockReturnValue(t0 + 5 * 60_000 - 1)
    engine.listIncomplete()
    await flush()
    // --- end of script ---

    // The cut: zero full listings in the whole window…
    expect(listingCalls()).toHaveLength(0)
    // …exactly one census round (2 requests, one per bucket)…
    expect(censusCalls()).toHaveLength(2)
    // …zero per-id document fetches (the census matched the local store)…
    expect(byIdCalls()).toHaveLength(0)
    // …and the only other backend traffic is the three mutation writes
    // (toggle PATCH + create POST + rename PATCH), which are user-caused.
    const methods = h.netFetch.mock.calls.map((c) => c[1]?.method ?? 'GET')
    expect(methods.filter((m) => m === 'GET')).toHaveLength(2) // the census
    expect(methods.filter((m) => m === 'PATCH')).toHaveLength(2) // toggle + rename
    expect(methods.filter((m) => m === 'POST')).toHaveLength(1) // create

    // The reads stayed instant and local throughout.
    expect(h.getLocalActionItems).toHaveBeenCalled()
  })
})
