// Unit tests for the Tier-A product-tool executors (PR-3). Each executor is built
// with INJECTED fakes for its store/engine edge, so nothing here touches
// better-sqlite3, Electron, or the network. We assert: (1) the executor calls the
// backing function with the right args, (2) it formats the Mac-shaped output, and
// (3) missing/empty/invalid inputs return the right guard strings.

import { describe, it, expect, vi } from 'vitest'
import type { ActionItemRecord, RewindFrame } from '../../shared/types'
import type { TaskSearchResult } from '../assistants/tasks/toolBackends'
import {
  createSemanticSearchExecutor,
  createSearchTasksExecutor,
  createGetActionItemsExecutor,
  createCreateActionItemExecutor,
  createUpdateActionItemExecutor,
  createCompleteTaskExecutor,
  createDeleteTaskExecutor
} from './productToolExecutors'
import { defaultProductToolExecutors, WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from './toolRelayBridge'

const ctx = (signal?: AbortSignal) => ({
  sessionId: 's1',
  adapterId: 'pi-mono',
  signal: signal ?? new AbortController().signal
})

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 1,
    ts: Date.now(),
    app: 'Chrome',
    windowTitle: 'Docs',
    processName: 'chrome.exe',
    ocrText: '',
    imagePath: '/x.jpg',
    width: 100,
    height: 100,
    indexed: 1,
    ...over
  }
}

function action(over: Partial<ActionItemRecord>): ActionItemRecord {
  return {
    id: 1,
    backendId: 'b1',
    backendSynced: true,
    description: 'Task one',
    completed: false,
    deleted: false,
    deletedBy: null,
    source: 'omi',
    conversationId: null,
    priority: null,
    category: null,
    tags: [],
    dueAt: null,
    screenshotId: null,
    confidence: null,
    sourceApp: null,
    windowTitle: null,
    contextSummary: null,
    currentActivity: null,
    metadataJson: null,
    relevanceScore: null,
    scoredAt: null,
    fromStaged: false,
    sortOrder: null,
    indentLevel: null,
    createdAt: 1000,
    updatedAt: 1000,
    ...over
  }
}

// --- semantic_search ---------------------------------------------------------

describe('semantic_search', () => {
  const deps = (over?: Partial<Parameters<typeof createSemanticSearchExecutor>[0]>) => ({
    embedQuery: vi.fn(async () => new Float32Array([1, 0, 0])),
    search: vi.fn(async () => [
      { frameId: 1, similarity: 0.82 },
      { frameId: 2, similarity: 0.2 } // below 0.3 → dropped
    ]),
    framesByIds: vi.fn(async () => [
      frame({
        id: 1,
        app: 'Safari',
        windowTitle: 'Gmail',
        ocrText: 'invoice line\nnext',
        ts: Date.now()
      })
    ]),
    ...over
  })

  it('requires a query', async () => {
    const exec = createSemanticSearchExecutor(deps())
    expect(await exec({}, ctx())).toBe('Error: query is required')
  })

  it('formats the Mac prose block and drops sub-0.3 hits', async () => {
    const d = deps()
    const exec = createSemanticSearchExecutor(d)
    const out = await exec({ query: 'invoice' }, ctx())
    expect(out).toContain('Found 1 screenshot(s) matching "invoice":')
    expect(out).toContain('Safari - Gmail (screenshot_id: 1, similarity: 0.82)')
    expect(out).toContain('Content: invoice line next') // newline collapsed to space
    expect(d.embedQuery).toHaveBeenCalledWith('invoice')
  })

  it('filters by app_filter (case-insensitive) and days window', async () => {
    const old = frame({ id: 9, app: 'Safari', ts: Date.now() - 40 * 24 * 60 * 60 * 1000 })
    const d = deps({
      search: vi.fn(async () => [{ frameId: 9, similarity: 0.9 }]),
      framesByIds: vi.fn(async () => [old])
    })
    const exec = createSemanticSearchExecutor(d)
    // 7-day default window excludes the 40-day-old frame → empty message.
    expect(await exec({ query: 'x' }, ctx())).toContain('No matching screen-history results')
  })

  it('returns the empty message when the query cannot be embedded (signed out)', async () => {
    const exec = createSemanticSearchExecutor(deps({ embedQuery: vi.fn(async () => null) }))
    expect(await exec({ query: 'x' }, ctx())).toContain(
      'No matching screen-history results for "x"'
    )
  })

  it('short-circuits to the empty message when the signal is already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const d = deps()
    const exec = createSemanticSearchExecutor(d)
    expect(await exec({ query: 'x' }, ctx(controller.signal))).toContain(
      'No matching screen-history results'
    )
    expect(d.framesByIds).not.toHaveBeenCalled()
  })
})

// --- search_tasks ------------------------------------------------------------

describe('search_tasks', () => {
  const results: TaskSearchResult[] = [
    {
      id: 42,
      description: 'Reply to Jane',
      status: 'active',
      similarity: 0.71,
      match_type: 'vector',
      relevance_score: null
    },
    {
      id: 9,
      description: 'Done thing',
      status: 'completed',
      similarity: 0.55,
      match_type: 'vector',
      relevance_score: null
    }
  ]

  it('requires a query', async () => {
    const exec = createSearchTasksExecutor({ vectorSearch: vi.fn(async () => results) })
    expect(await exec({}, ctx())).toBe('Error: query is required')
  })

  it('drops completed by default and formats rows', async () => {
    const vectorSearch = vi.fn(async () => results)
    const exec = createSearchTasksExecutor({ vectorSearch })
    const out = await exec({ query: 'email' }, ctx())
    expect(out).toContain('Found 1 task(s) matching "email":')
    expect(out).toContain('1. [ ] Reply to Jane (similarity: 0.71, id: 42)')
    expect(out).not.toContain('Done thing')
    expect(vectorSearch).toHaveBeenCalledWith('email')
  })

  it('includes completed when include_completed=true', async () => {
    const exec = createSearchTasksExecutor({ vectorSearch: vi.fn(async () => results) })
    const out = await exec({ query: 'x', include_completed: true }, ctx())
    expect(out).toContain('[x] Done thing')
  })

  it('empty results → no-tasks message', async () => {
    const exec = createSearchTasksExecutor({ vectorSearch: vi.fn(async () => []) })
    expect(await exec({ query: 'zzz' }, ctx())).toContain('No tasks found matching "zzz"')
  })
})

// --- get_action_items --------------------------------------------------------

describe('get_action_items', () => {
  it('lists tasks and passes completed/limit/offset through', async () => {
    const getItems = vi.fn(async () => [action({ description: 'A', backendId: 'ba' })])
    const exec = createGetActionItemsExecutor({ getItems })
    const out = await exec({ completed: false, limit: 10, offset: 5 }, ctx())
    expect(getItems).toHaveBeenCalledWith({ completed: false, limit: 10, offset: 5 })
    expect(out).toContain('Found 1 task(s):')
    expect(out).toContain('1. [ ] A (id: ba, due: none)')
  })

  it('empty → no matching tasks', async () => {
    const exec = createGetActionItemsExecutor({ getItems: vi.fn(async () => []) })
    expect(await exec({}, ctx())).toBe('No matching tasks found.')
  })

  it('rejects a malformed due_start_date', async () => {
    const exec = createGetActionItemsExecutor({ getItems: vi.fn(async () => []) })
    const out = await exec({ due_start_date: 'not-a-date' }, ctx())
    expect(out).toContain('Error: due_start_date must be ISO format')
  })

  it('filters by due-date range in-memory', async () => {
    const items = [
      action({ description: 'soon', dueAt: Date.parse('2026-02-01T00:00:00Z') }),
      action({ description: 'later', dueAt: Date.parse('2026-06-01T00:00:00Z') })
    ]
    const exec = createGetActionItemsExecutor({ getItems: vi.fn(async () => items) })
    const out = await exec(
      { due_start_date: '2026-01-01T00:00:00Z', due_end_date: '2026-03-01T00:00:00Z' },
      ctx()
    )
    expect(out).toContain('soon')
    expect(out).not.toContain('later')
  })
})

// --- create_action_item ------------------------------------------------------

describe('create_action_item', () => {
  it('requires a description', async () => {
    const exec = createCreateActionItemExecutor({ createTask: vi.fn(async () => action({})) })
    expect(await exec({}, ctx())).toBe('Error: description is required')
  })

  it('creates with parsed due date and confirms', async () => {
    const createTask = vi.fn(async () => action({}))
    const exec = createCreateActionItemExecutor({ createTask })
    const out = await exec({ description: 'Call Mom', due_at: '2026-05-01T17:00:00-04:00' }, ctx())
    expect(createTask).toHaveBeenCalledWith({
      description: 'Call Mom',
      dueAt: Date.parse('2026-05-01T17:00:00-04:00'),
      conversationId: null,
      source: 'omi'
    })
    expect(out).toBe('OK: task "Call Mom" created')
  })

  it('rejects a malformed due_at before writing', async () => {
    const createTask = vi.fn(async () => action({}))
    const exec = createCreateActionItemExecutor({ createTask })
    expect(await exec({ description: 'x', due_at: 'soon-ish' }, ctx())).toContain(
      'Error: due_at must be ISO format'
    )
    expect(createTask).not.toHaveBeenCalled()
  })
})

// --- update_action_item ------------------------------------------------------

describe('update_action_item', () => {
  const mutate = (task: ActionItemRecord | null) => ({
    findByBackendId: vi.fn(async () => task),
    toggleTask: vi.fn(async () => {}),
    updateTask: vi.fn(async () => {}),
    deleteTask: vi.fn(async () => {})
  })

  it('requires action_item_id', async () => {
    const exec = createUpdateActionItemExecutor(mutate(action({})))
    expect(await exec({}, ctx())).toBe('Error: action_item_id is required')
  })

  it('not found → error string', async () => {
    const exec = createUpdateActionItemExecutor(mutate(null))
    expect(await exec({ action_item_id: 'nope' }, ctx())).toBe(
      "Error: task not found with id 'nope'"
    )
  })

  it('applies description/due via updateTask and completion via toggleTask', async () => {
    const d = mutate(action({ backendId: 'b1', description: 'old' }))
    const exec = createUpdateActionItemExecutor(d)
    const out = await exec(
      { action_item_id: 'b1', description: 'new', due_at: '2026-05-01T00:00:00Z', completed: true },
      ctx()
    )
    expect(d.updateTask).toHaveBeenCalledWith('b1', {
      description: 'new',
      dueAt: Date.parse('2026-05-01T00:00:00Z')
    })
    expect(d.toggleTask).toHaveBeenCalledWith('b1', true)
    expect(out).toBe("OK: task 'old' updated")
  })
})

// --- complete_task -----------------------------------------------------------

describe('complete_task', () => {
  const mutate = (task: ActionItemRecord | null) => ({
    findByBackendId: vi.fn(async () => task),
    toggleTask: vi.fn(async () => {}),
    updateTask: vi.fn(async () => {}),
    deleteTask: vi.fn(async () => {})
  })

  it('requires task_id', async () => {
    const exec = createCompleteTaskExecutor(mutate(action({})))
    expect(await exec({}, ctx())).toBe('Error: task_id is required')
  })

  it('not found → Mac error', async () => {
    const exec = createCompleteTaskExecutor(mutate(null))
    expect(await exec({ task_id: 'x' }, ctx())).toBe("Error: task not found with id 'x'")
  })

  it('already completed → OK-already string, no toggle', async () => {
    const d = mutate(action({ description: 'Done', completed: true }))
    const exec = createCompleteTaskExecutor(d)
    expect(await exec({ task_id: 'b1' }, ctx())).toBe("OK: task 'Done' is already completed")
    expect(d.toggleTask).not.toHaveBeenCalled()
  })

  it('completes and confirms', async () => {
    const d = mutate(action({ description: 'Do it', completed: false }))
    const exec = createCompleteTaskExecutor(d)
    expect(await exec({ task_id: 'b1' }, ctx())).toBe("OK: task 'Do it' marked as completed")
    expect(d.toggleTask).toHaveBeenCalledWith('b1', true)
  })
})

// --- delete_task -------------------------------------------------------------

describe('delete_task', () => {
  const mutate = (task: ActionItemRecord | null) => ({
    findByBackendId: vi.fn(async () => task),
    toggleTask: vi.fn(async () => {}),
    updateTask: vi.fn(async () => {}),
    deleteTask: vi.fn(async () => {})
  })

  it('requires task_id', async () => {
    const exec = createDeleteTaskExecutor(mutate(action({})))
    expect(await exec({}, ctx())).toBe('Error: task_id is required')
  })

  it('not found → Mac error', async () => {
    const exec = createDeleteTaskExecutor(mutate(null))
    expect(await exec({ task_id: 'x' }, ctx())).toBe("Error: task not found with id 'x'")
  })

  it('deletes and confirms', async () => {
    const d = mutate(action({ description: 'Trash me' }))
    const exec = createDeleteTaskExecutor(d)
    expect(await exec({ task_id: 'b1' }, ctx())).toBe("OK: task 'Trash me' deleted")
    expect(d.deleteTask).toHaveBeenCalledWith('b1')
  })
})

// --- registry wiring ---------------------------------------------------------

describe('Tier-A tools are registered + serviceable', () => {
  const names = [
    'semantic_search',
    'search_tasks',
    'get_action_items',
    'create_action_item',
    'update_action_item',
    'complete_task',
    'delete_task'
  ]

  it('every Tier-A tool is in the default registry and the serviceable allowlist', () => {
    for (const n of names) {
      expect(defaultProductToolExecutors.has(n)).toBe(true)
      expect(WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(n)).toBe(true)
    }
  })

  it('does NOT register load_skill (answered in-process by the extension) or search_screen_history', () => {
    expect(defaultProductToolExecutors.has('load_skill')).toBe(false)
    expect(defaultProductToolExecutors.has('search_screen_history')).toBe(false)
  })
})
