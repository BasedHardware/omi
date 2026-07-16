// Sync-engine behavior tests. The engine is hermetic here: `electron` (net.fetch +
// BrowserWindow) and the storage wrappers (`../ipc/db`, a native better-sqlite3
// module that can't load under plain-node vitest) are mocked; the REAL
// core/session drives the epoch guard. Covers the ported Mac behaviors: local-first
// hydration → sync, reconcile hard-delete (+ empty-guard + 5-min throttle),
// optimistic create/toggle/update/delete (markSynced / revert / keep-local), the
// FIX-ii deletion listener, and retryUnsynced.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActionItemRecord } from '../../shared/types'

// --- Hoisted mocks -----------------------------------------------------------
const h = vi.hoisted(() => {
  const jsonResponse = (data: unknown, ok = true, status = 200): unknown => ({
    ok,
    status,
    json: async () => data
  })
  return {
    jsonResponse,
    // Routed by HTTP method; individual tests override for failures/echoes.
    serverItems: [] as unknown[],
    netFetch: vi.fn(),
    // storage wrappers
    getLocalActionItems: vi.fn((): ActionItemRecord[] => []),
    getFilteredActionItems: vi.fn((): ActionItemRecord[] => []),
    getUnsyncedActionItems: vi.fn((): ActionItemRecord[] => []),
    insertLocalActionItem: vi.fn(),
    updateCompletionStatus: vi.fn(),
    updateActionItemFields: vi.fn(),
    deleteActionItemByBackendId: vi.fn((): number[] => []),
    markSyncedActionItem: vi.fn(() => ({ merged: false, keptId: 0 })),
    syncTaskActionItems: vi.fn(() => ({ skipped: 0, adopted: 0, inserted: 0, updated: 0 })),
    hardDeleteAbsentTasks: vi.fn((): number[] => []),
    getAppMeta: vi.fn((): string | null => '1'), // full-sync flag set → skip full sync by default
    setAppMeta: vi.fn(),
    // Event-driven promotion trigger (create.ts) — mocked so the engine's toggle/
    // delete promote calls are observable without pulling create's real deps.
    promoteIfNeeded: vi.fn(async () => {}),
    // `tasks:changed` broadcast spy — a fake window's webContents.send.
    send: vi.fn()
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
  getUnsyncedActionItems: h.getUnsyncedActionItems,
  insertLocalActionItem: h.insertLocalActionItem,
  updateCompletionStatus: h.updateCompletionStatus,
  updateActionItemFields: h.updateActionItemFields,
  deleteActionItemByBackendId: h.deleteActionItemByBackendId,
  markSyncedActionItem: h.markSyncedActionItem,
  syncTaskActionItems: h.syncTaskActionItems,
  hardDeleteAbsentTasks: h.hardDeleteAbsentTasks,
  getAppMeta: h.getAppMeta,
  setAppMeta: h.setAppMeta
}))

vi.mock('../assistants/tasks/create', () => ({ promoteIfNeeded: h.promoteIfNeeded }))

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

// Default net.fetch: GET returns h.serverItems, writes echo a plausible item.
function defaultRoute(): void {
  h.netFetch.mockImplementation(async (_url: string, init?: { method?: string }) => {
    const method = init?.method ?? 'GET'
    if (method === 'GET') return h.jsonResponse({ action_items: h.serverItems, has_more: false })
    if (method === 'POST') return h.jsonResponse(backendItem({ id: 'srv-new' }))
    if (method === 'PATCH') return h.jsonResponse(backendItem({ completed: true }))
    if (method === 'DELETE') return h.jsonResponse({}, true, 204)
    return h.jsonResponse({})
  })
}

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
  h.getAppMeta.mockReturnValue('1')
  h.getLocalActionItems.mockReturnValue([])
  h.hardDeleteAbsentTasks.mockReturnValue([])
  defaultRoute()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => vi.restoreAllMocks())

describe('hydration (local-first)', () => {
  it('listIncomplete returns local rows immediately, then background-syncs the backend page', async () => {
    const local = [{ id: 1, description: 'local' } as unknown as ActionItemRecord]
    h.getLocalActionItems.mockReturnValue(local)
    const { engine } = await freshEngine()

    const rows = engine.listIncomplete()
    expect(rows).toBe(local) // instant local read
    expect(h.getLocalActionItems).toHaveBeenCalledWith({
      completed: false,
      limit: undefined,
      offset: undefined
    })

    await engine.hydrateIncomplete() // await the background run
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
    await engine.hydrateIncomplete()

    expect(h.netFetch).not.toHaveBeenCalled()
    expect(h.syncTaskActionItems).not.toHaveBeenCalled()
  })

  // Regression: a hydrate that changes nothing MUST NOT emit `tasks:changed`. The
  // renderer re-reads on that event, and every read kicks another hydrate — an
  // unconditional broadcast turns steady state into an unbounded backend-poll loop.
  it('a no-op hydrate stays silent (no tasks:changed broadcast)', async () => {
    const { engine } = await freshEngine()
    // Defaults: syncTaskActionItems → all-zero counts, hardDeleteAbsentTasks → [].
    await engine.hydrateIncomplete()
    expect(h.syncTaskActionItems).toHaveBeenCalledTimes(1)
    expect(h.send).not.toHaveBeenCalledWith('tasks:changed')
  })

  it('broadcasts tasks:changed when the sync actually changes a row', async () => {
    h.syncTaskActionItems.mockReturnValue({ skipped: 0, adopted: 0, inserted: 1, updated: 0 })
    const { engine } = await freshEngine()
    await engine.hydrateIncomplete()
    expect(h.send).toHaveBeenCalledWith('tasks:changed')
  })
})

describe('reconcile (hardDeleteAbsentTasks)', () => {
  it('hard-deletes tasks absent from the backend listing and evicts them (FIX ii)', async () => {
    h.hardDeleteAbsentTasks.mockReturnValue([42])
    const { engine } = await freshEngine()
    const evicted: unknown[] = []
    engine.setTaskDeletionListener((d) => evicted.push(...d))

    await engine.hydrateIncomplete()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
    expect(evicted).toEqual([{ source: 'action_item', id: 42 }])
  })

  it('empty-guard: when the store deletes nothing, the deletion listener is not called', async () => {
    h.hardDeleteAbsentTasks.mockReturnValue([])
    const { engine } = await freshEngine()
    const listener = vi.fn()
    engine.setTaskDeletionListener(listener)

    await engine.hydrateIncomplete()

    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledWith(['b1'])
    expect(listener).not.toHaveBeenCalled()
  })

  it('throttles reconcile to once per 5 minutes', async () => {
    const t0 = 1_700_000_000_000
    const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(t0)
    const { engine } = await freshEngine()

    await engine.hydrateIncomplete()
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledTimes(1)

    nowSpy.mockReturnValue(t0 + 60_000) // +1 min, within throttle
    await engine.hydrateIncomplete()
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledTimes(1)

    nowSpy.mockReturnValue(t0 + 6 * 60_000) // +6 min, past throttle
    await engine.hydrateIncomplete()
    expect(h.hardDeleteAbsentTasks).toHaveBeenCalledTimes(2)
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
  it('pages everything once when the flag is unset, then persists the flag', async () => {
    h.getAppMeta.mockReturnValue(null) // not yet done
    const { engine } = await freshEngine()

    await engine.hydrateIncomplete()

    expect(h.setAppMeta).toHaveBeenCalledWith('tasksFullSyncCompleted_v1_u1', '1')
    // Both completed=false and completed=true pages were fetched during the full sync.
    const gets = h.netFetch.mock.calls
      .filter((c) => ((c[1] as { method?: string })?.method ?? 'GET') === 'GET')
      .map((c) => String(c[0]))
    expect(gets.some((u) => u.includes('completed=true'))).toBe(true)
    expect(gets.some((u) => u.includes('completed=false'))).toBe(true)
  })
})
