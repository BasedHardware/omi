// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach, beforeAll, afterAll } from 'vitest'
import {
  render,
  cleanup,
  waitFor,
  fireEvent,
  screen,
  within,
  configure,
  getConfig
} from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ActionItemRecord } from '../../../shared/types'

// Same suite-load headroom as Tasks.test.tsx: every assertion rides async IPC
// mocks + React commits, and a CPU-starved parallel worker can push a commit past
// the 1000ms default. Raised at module scope (it() captures timeouts at
// collection), restored after the file.
vi.setConfig({ testTimeout: 15000 })
let prevAsyncUtilTimeout = 1000
beforeAll(() => {
  prevAsyncUtilTimeout = getConfig().asyncUtilTimeout
  configure({ asyncUtilTimeout: 5000 })
})
afterAll(() => {
  configure({ asyncUtilTimeout: prevAsyncUtilTimeout })
  vi.resetConfig()
})

// The feature surfaces under test here:
//  - the task detail panel (open from a row, priority edit, action wiring)
//  - the per-task Investigate chat panel handoff (mutually exclusive with detail)
//  - multi-select mode with the bulk complete/delete/reschedule bar
//  - the priority filter chips
//  - the escape hierarchy (chat -> detail -> select mode -> keyboard selection)

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: (...args: unknown[]) => getMock(...args) }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
// The chat panel's send path calls the agent LLM + local-context gather; neither
// belongs in these tests — the handoff (which panel renders) is what's pinned.
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn(() => Promise.resolve('ok')) }))
vi.mock('../lib/localAgent', () => ({ gatherLocalContext: vi.fn(() => Promise.resolve('')) }))

const rec = (over: Partial<ActionItemRecord>): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'b1',
    backendSynced: true,
    description: 'task',
    completed: false,
    deleted: false,
    source: null,
    conversationId: null,
    priority: null,
    category: null,
    tags: [],
    dueAt: null,
    confidence: null,
    sourceApp: null,
    windowTitle: null,
    relevanceScore: null,
    fromStaged: false,
    sortOrder: null,
    indentLevel: null,
    createdAt: 1_000,
    updatedAt: 1_000,
    ...over
  }) as ActionItemRecord

let incomplete: ActionItemRecord[]
let completed: ActionItemRecord[]
let tasks: {
  tasksListIncomplete: ReturnType<typeof vi.fn>
  tasksListCompleted: ReturnType<typeof vi.fn>
  tasksCreate: ReturnType<typeof vi.fn>
  tasksToggle: ReturnType<typeof vi.fn>
  tasksUpdate: ReturnType<typeof vi.fn>
  tasksDelete: ReturnType<typeof vi.fn>
  tasksReconcile: ReturnType<typeof vi.fn>
  onTasksChanged: ReturnType<typeof vi.fn>
  onTasksOpFailed: ReturnType<typeof vi.fn>
}

beforeEach(() => {
  incomplete = []
  completed = []
  getMock.mockReset()
  Element.prototype.scrollIntoView = vi.fn()
  // jsdom implements neither; the chat panel pins its transcript to the bottom.
  ;(Element.prototype as unknown as { scrollTo: () => void }).scrollTo = vi.fn()
  getMock.mockImplementation((url: string) => {
    if (url === '/v1/conversations') return Promise.resolve({ data: [] })
    throw new Error(`unexpected GET ${url}`)
  })
  tasks = {
    tasksListIncomplete: vi.fn(() => Promise.resolve(incomplete)),
    tasksListCompleted: vi.fn(() => Promise.resolve(completed)),
    tasksCreate: vi.fn(() => Promise.resolve(rec({}))),
    tasksToggle: vi.fn(() => Promise.resolve()),
    tasksUpdate: vi.fn(() => Promise.resolve()),
    tasksDelete: vi.fn(() => Promise.resolve()),
    tasksReconcile: vi.fn(() => Promise.resolve()),
    onTasksChanged: vi.fn(() => () => {}),
    onTasksOpFailed: vi.fn(() => () => {})
  }
  ;(window as unknown as { omi: unknown }).omi = tasks
})

afterEach(() => {
  cleanup()
  vi.resetModules()
  window.localStorage.clear()
})

async function renderTasks(): Promise<void> {
  const { Tasks } = await import('./Tasks')
  render(
    <MemoryRouter>
      <Tasks />
    </MemoryRouter>
  )
}

async function openDetailFor(description: string, id: number): Promise<void> {
  await waitFor(() => expect(screen.queryByText(description)).not.toBeNull())
  fireEvent.click(screen.getByTestId(`task-details-${id}`))
  await waitFor(() => expect(screen.queryByTestId('task-detail-panel')).not.toBeNull())
}

describe('Tasks — detail panel', () => {
  it('opens from the row details affordance and shows the task', async () => {
    incomplete = [
      rec({ id: 5, backendId: 'b5', description: 'inspect me', priority: 'high', category: 'work' })
    ]
    await renderTasks()
    await openDetailFor('inspect me', 5)

    const panel = within(screen.getByTestId('task-detail-panel'))
    expect(panel.getByText('inspect me')).not.toBeNull()
    // 'Active' appears both as the header subtitle and the Status detail row.
    expect(panel.getAllByText('Active').length).toBeGreaterThan(0)
    expect(panel.getByTestId('task-detail-why').textContent).toBe('You added this task directly.')
  })

  it('edits priority through tasksUpdate; the selected chip is a no-op', async () => {
    incomplete = [rec({ id: 5, backendId: 'b5', description: 'prio task', priority: 'medium' })]
    await renderTasks()
    await openDetailFor('prio task', 5)

    fireEvent.click(screen.getByTestId('task-detail-priority-high'))
    expect(tasks.tasksUpdate).toHaveBeenCalledWith({
      backendId: 'b5',
      fields: { priority: 'high' }
    })

    tasks.tasksUpdate.mockClear()
    fireEvent.click(screen.getByTestId('task-detail-priority-medium'))
    expect(tasks.tasksUpdate).not.toHaveBeenCalled()
  })

  it('hides the priority section for completed tasks (mac gate)', async () => {
    completed = [rec({ id: 6, backendId: 'b6', description: 'done one', completed: true })]
    await renderTasks()
    await waitFor(() => expect(document.body.textContent).toContain('1 done'))
    fireEvent.click(screen.getByRole('button', { name: 'done' }))
    await openDetailFor('done one', 6)
    expect(screen.queryByTestId('task-detail-priority-high')).toBeNull()
    expect(
      within(screen.getByTestId('task-detail-panel')).getAllByText('Completed').length
    ).toBeGreaterThan(0)
  })

  it('Edit closes the panel and opens the inline row editor', async () => {
    incomplete = [rec({ id: 5, backendId: 'b5', description: 'edit me' })]
    await renderTasks()
    await openDetailFor('edit me', 5)

    fireEvent.click(screen.getByTestId('task-detail-edit'))
    await waitFor(() => expect(screen.queryByTestId('task-detail-panel')).toBeNull())
    // The row's inline editor holds the description.
    expect((screen.getByDisplayValue('edit me') as HTMLInputElement).tagName).toBe('INPUT')
  })

  it('Delete closes the panel and deletes through IPC', async () => {
    incomplete = [rec({ id: 5, backendId: 'b5', description: 'remove me' })]
    await renderTasks()
    await openDetailFor('remove me', 5)

    fireEvent.click(screen.getByTestId('task-detail-delete'))
    await waitFor(() => expect(screen.queryByTestId('task-detail-panel')).toBeNull())
    expect(tasks.tasksDelete).toHaveBeenCalledWith({ backendId: 'b5' })
  })

  it('Investigate swaps the detail panel for the task chat panel', async () => {
    incomplete = [rec({ id: 5, backendId: 'b5', description: 'research me' })]
    await renderTasks()
    await openDetailFor('research me', 5)

    fireEvent.click(screen.getByTestId('task-detail-chat'))
    await waitFor(() => expect(screen.queryByTestId('task-chat-panel')).not.toBeNull())
    expect(screen.queryByTestId('task-detail-panel')).toBeNull()
  })
})

describe('Tasks — priority on rows and filter chips', () => {
  it('flags prioritized rows and filters by exact priority', async () => {
    incomplete = [
      rec({ id: 1, backendId: 'b1', description: 'urgent thing', priority: 'high' }),
      rec({ id: 2, backendId: 'b2', description: 'someday thing', priority: 'low' }),
      rec({ id: 3, backendId: 'b3', description: 'plain thing' })
    ]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('urgent thing')).not.toBeNull())

    expect(screen.getAllByLabelText('high priority')).toHaveLength(1)

    fireEvent.click(screen.getByTestId('tasks-priority-filter-high'))
    await waitFor(() => expect(screen.queryByText('someday thing')).toBeNull())
    expect(screen.queryByText('urgent thing')).not.toBeNull()
    expect(screen.queryByText('plain thing')).toBeNull()

    fireEvent.click(screen.getByTestId('tasks-priority-filter-any'))
    await waitFor(() => expect(screen.queryByText('plain thing')).not.toBeNull())
  })
})

describe('Tasks — multi-select and bulk operations', () => {
  const threeRows = (): ActionItemRecord[] => [
    rec({ id: 1, backendId: 'b1', description: 'first' }),
    rec({ id: 2, backendId: 'b2', description: 'second' }),
    rec({ id: 3, backendId: 'b3', description: 'third' })
  ]

  async function enterSelectMode(): Promise<void> {
    fireEvent.click(screen.getByTestId('tasks-select-toggle'))
    await waitFor(() => expect(screen.queryByTestId('tasks-selection-bar')).not.toBeNull())
  }

  function rowFor(description: string): HTMLElement {
    const el = screen.getByText(description).closest('li')
    if (!el) throw new Error(`no row for ${description}`)
    return el as HTMLElement
  }

  it('selects rows by click, ctrl-click accumulates, and the count updates', async () => {
    incomplete = threeRows()
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    await enterSelectMode()

    fireEvent.click(rowFor('first'))
    expect(screen.getByTestId('tasks-selected-count').textContent).toBe('1 selected')

    fireEvent.click(rowFor('third'), { ctrlKey: true })
    expect(screen.getByTestId('tasks-selected-count').textContent).toBe('2 selected')

    // Plain click replaces the selection.
    fireEvent.click(rowFor('second'))
    expect(screen.getByTestId('tasks-selected-count').textContent).toBe('1 selected')
  })

  it('shift-click selects the contiguous range from the anchor', async () => {
    incomplete = threeRows()
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    await enterSelectMode()

    fireEvent.click(rowFor('first'))
    fireEvent.click(rowFor('third'), { shiftKey: true })
    expect(screen.getByTestId('tasks-selected-count').textContent).toBe('3 selected')
  })

  it('bulk complete toggles every selected synced row', async () => {
    incomplete = threeRows()
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    await enterSelectMode()

    fireEvent.click(rowFor('first'))
    fireEvent.click(rowFor('second'), { ctrlKey: true })
    fireEvent.click(screen.getByTestId('tasks-bulk-complete'))

    await waitFor(() => expect(tasks.tasksToggle).toHaveBeenCalledTimes(2))
    expect(tasks.tasksToggle).toHaveBeenCalledWith({ backendId: 'b1', completed: true })
    expect(tasks.tasksToggle).toHaveBeenCalledWith({ backendId: 'b2', completed: true })
    // A fully-successful bulk exits select mode.
    await waitFor(() => expect(screen.queryByTestId('tasks-selection-bar')).toBeNull())
  })

  it('bulk delete confirms first and deletes on accept', async () => {
    incomplete = threeRows()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    try {
      await renderTasks()
      await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
      await enterSelectMode()

      fireEvent.click(rowFor('second'))
      fireEvent.click(rowFor('third'), { ctrlKey: true })
      fireEvent.click(screen.getByTestId('tasks-bulk-delete'))

      expect(confirmSpy).toHaveBeenCalledWith('Delete 2 tasks? This cannot be undone.')
      await waitFor(() => expect(tasks.tasksDelete).toHaveBeenCalledTimes(2))
    } finally {
      confirmSpy.mockRestore()
    }
  })

  it('bulk delete does nothing when the confirm is declined', async () => {
    incomplete = threeRows()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    try {
      await renderTasks()
      await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
      await enterSelectMode()
      fireEvent.click(rowFor('first'))
      fireEvent.click(screen.getByTestId('tasks-bulk-delete'))
      expect(tasks.tasksDelete).not.toHaveBeenCalled()
    } finally {
      confirmSpy.mockRestore()
    }
  })

  it('bulk reschedule sends the picked date to every selected row', async () => {
    incomplete = threeRows()
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    await enterSelectMode()

    fireEvent.click(rowFor('first'))
    fireEvent.click(screen.getByTestId('tasks-bulk-reschedule'))
    fireEvent.change(screen.getByTestId('tasks-bulk-reschedule-date'), {
      target: { value: '2026-09-01' }
    })

    await waitFor(() => expect(tasks.tasksUpdate).toHaveBeenCalledTimes(1))
    const arg = tasks.tasksUpdate.mock.calls[0][0] as {
      backendId: string
      fields: { dueAt: number }
    }
    expect(arg.backendId).toBe('b1')
    const due = new Date(arg.fields.dueAt)
    expect([due.getFullYear(), due.getMonth(), due.getDate()]).toEqual([2026, 8, 1])
  })

  it('Ctrl+A selects every rendered row in select mode', async () => {
    incomplete = threeRows()
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    await enterSelectMode()

    fireEvent.keyDown(document.body, { key: 'a', ctrlKey: true })
    await waitFor(() =>
      expect(screen.getByTestId('tasks-selected-count').textContent).toBe('3 selected')
    )
  })
})

describe('Tasks — escape hierarchy', () => {
  it('Escape closes chat first, then detail, then exits select mode', async () => {
    incomplete = [rec({ id: 5, backendId: 'b5', description: 'layered' })]
    await renderTasks()
    await openDetailFor('layered', 5)
    fireEvent.click(screen.getByTestId('task-detail-chat'))
    await waitFor(() => expect(screen.queryByTestId('task-chat-panel')).not.toBeNull())

    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('task-chat-panel')).toBeNull())

    // Re-open the detail panel; Escape closes it next.
    fireEvent.click(screen.getByTestId('task-details-5'))
    await waitFor(() => expect(screen.queryByTestId('task-detail-panel')).not.toBeNull())
    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('task-detail-panel')).toBeNull())

    // Then select mode.
    fireEvent.click(screen.getByTestId('tasks-select-toggle'))
    await waitFor(() => expect(screen.queryByTestId('tasks-selection-bar')).not.toBeNull())
    fireEvent.keyDown(document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('tasks-selection-bar')).toBeNull())
  })
})
