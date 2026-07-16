// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ActionItemRecord } from '../../../shared/types'

// The Tasks page is now local-first: it reads the task store over IPC
// (window.omi.tasksListIncomplete + tasksListCompleted) instead of paging the
// backend /v1/action-items endpoint, and every mutation is a thin IPC call that
// lets MAIN own optimism + revert. This suite pins that contract:
//  - reads come from the store IPC, not the backend action-items endpoint
//  - the open/completed buckets render from the store rows
//  - create/toggle/delete call the matching IPC with the row's backendId
//  - a freshly-created row (backendId:null) is id-gated — no mutation may fire
//  - onTasksChanged triggers a re-read (replaces the old mount/focus refetch)

const getMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: (...args: unknown[]) => getMock(...args) }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

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
let changedCb: (() => void) | null
let tasks: {
  tasksListIncomplete: ReturnType<typeof vi.fn>
  tasksListCompleted: ReturnType<typeof vi.fn>
  tasksCreate: ReturnType<typeof vi.fn>
  tasksToggle: ReturnType<typeof vi.fn>
  tasksUpdate: ReturnType<typeof vi.fn>
  tasksDelete: ReturnType<typeof vi.fn>
  tasksReconcile: ReturnType<typeof vi.fn>
  onTasksChanged: ReturnType<typeof vi.fn>
}

beforeEach(() => {
  incomplete = []
  completed = []
  changedCb = null
  getMock.mockReset()
  // The page fetches a conversation title map for the source links (still a
  // backend call — out of scope for the local store).
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
    onTasksChanged: vi.fn((cb: () => void) => {
      changedCb = cb
      return () => {
        changedCb = null
      }
    })
  }
  ;(window as unknown as { omi: unknown }).omi = tasks
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

async function renderTasks(): Promise<void> {
  const { Tasks } = await import('./Tasks')
  render(
    <MemoryRouter>
      <Tasks />
    </MemoryRouter>
  )
}

describe('Tasks — local-first reads from the store', () => {
  it('reads via the task-store IPC, never the backend action-items endpoint', async () => {
    incomplete = [rec({ id: 1, backendId: 'b1', description: 'open one' })]
    await renderTasks()

    await waitFor(() => expect(tasks.tasksListIncomplete).toHaveBeenCalled())
    expect(tasks.tasksListCompleted).toHaveBeenCalled()
    // The old page paged /v1/action-items; that endpoint must no longer be hit.
    expect(getMock.mock.calls.some((c) => c[0] === '/v1/action-items')).toBe(false)
  })

  it('renders open and completed rows from the store buckets', async () => {
    incomplete = [
      rec({ id: 1, backendId: 'b1', description: 'write spec' }),
      rec({ id: 2, backendId: 'b2', description: 'ship it' })
    ]
    completed = [rec({ id: 3, backendId: 'b3', description: 'done thing', completed: true })]
    await renderTasks()

    await waitFor(() => expect(document.body.textContent).toContain('2 open · 1 done'))
    expect(screen.getByText('write spec')).not.toBeNull()
    expect(screen.getByText('ship it')).not.toBeNull()
  })

  it('sorts the completed list by updatedAt desc (newest done first)', async () => {
    completed = [
      rec({ id: 1, backendId: 'b1', description: 'older done', completed: true, updatedAt: 100 }),
      rec({ id: 2, backendId: 'b2', description: 'newer done', completed: true, updatedAt: 200 })
    ]
    await renderTasks()
    // With only completed rows the default 'open' view says "All caught up"; wait
    // for the load, then switch to the completed view to assert order.
    await waitFor(() => expect(document.body.textContent).toContain('2 done'))
    fireEvent.click(screen.getByRole('button', { name: 'done' }))
    const rows = screen.getAllByRole('listitem').map((li) => li.textContent)
    const newerIdx = rows.findIndex((t) => t?.includes('newer done'))
    const olderIdx = rows.findIndex((t) => t?.includes('older done'))
    expect(newerIdx).toBeLessThan(olderIdx)
  })
})

describe('Tasks — mutations are thin IPC calls', () => {
  it('creates through tasksCreate and closes the composer', async () => {
    await renderTasks()
    await waitFor(() => expect(tasks.tasksListIncomplete).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'New' }))
    const input = screen.getByPlaceholderText('What needs to get done?')
    fireEvent.change(input, { target: { value: 'new task' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add task' }))

    await waitFor(() =>
      expect(tasks.tasksCreate).toHaveBeenCalledWith(
        expect.objectContaining({ description: 'new task' })
      )
    )
    // Composer closed — the create is surfaced by onTasksChanged, not a reload.
    await waitFor(() => expect(screen.queryByPlaceholderText('What needs to get done?')).toBeNull())
  })

  it('toggles through tasksToggle with the row backendId', async () => {
    incomplete = [rec({ id: 7, backendId: 'srv-7', description: 'toggle me' })]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('toggle me')).not.toBeNull())

    fireEvent.click(screen.getByRole('button', { name: 'Mark as done' }))
    expect(tasks.tasksToggle).toHaveBeenCalledWith({ backendId: 'srv-7', completed: true })
  })

  it('deletes through tasksDelete with the row backendId', async () => {
    incomplete = [rec({ id: 9, backendId: 'srv-9', description: 'delete me' })]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('delete me')).not.toBeNull())

    fireEvent.click(screen.getByRole('button', { name: 'Delete task' }))
    expect(tasks.tasksDelete).toHaveBeenCalledWith({ backendId: 'srv-9' })
  })
})

describe('Tasks — a freshly-created row is id-gated until synced', () => {
  it('disables the controls and fires no mutation while backendId is null', async () => {
    incomplete = [rec({ id: 5, backendId: null, description: 'just created' })]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('just created')).not.toBeNull())

    const row = screen.getByText('just created').closest('li') as HTMLElement
    const toggle = within(row).getByRole('button', { name: 'Mark as done' }) as HTMLButtonElement
    expect(toggle.disabled).toBe(true)

    fireEvent.click(toggle)
    expect(tasks.tasksToggle).not.toHaveBeenCalled()
  })
})

describe('Tasks — due-date buckets fold overdue into Today (Mac parity: 4 buckets)', () => {
  const DAY = 86_400_000

  it('renders no Overdue section — overdue tasks appear under Today', async () => {
    incomplete = [
      rec({ id: 1, backendId: 'b1', description: 'overdue task', dueAt: Date.now() - 3 * DAY }),
      rec({ id: 2, backendId: 'b2', description: 'today task', dueAt: Date.now() })
    ]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('overdue task')).not.toBeNull())

    // There is no separate "Overdue" bucket header.
    const headers = screen.getAllByRole('heading').map((h) => h.textContent ?? '')
    expect(headers.some((h) => /Overdue/i.test(h))).toBe(false)

    // Both the overdue and today tasks live inside the single "Today" section.
    const todaySection = screen
      .getAllByRole('heading')
      .find((h) => /^Today/.test(h.textContent ?? ''))
      ?.closest('section') as HTMLElement
    expect(todaySection).toBeTruthy()
    expect(within(todaySection).getByText('overdue task')).not.toBeNull()
    expect(within(todaySection).getByText('today task')).not.toBeNull()
  })

  it('flags an overdue row with the rose date badge; a task due today is not flagged', async () => {
    // The user-visible artifact of splitting isOverdue from bucketing: overdue
    // rows live in Today but still render their date in rose (text-rose-300/90),
    // while a task actually due today renders neutral.
    incomplete = [
      rec({ id: 1, backendId: 'b1', description: 'overdue task', dueAt: Date.now() - 3 * DAY }),
      rec({ id: 2, backendId: 'b2', description: 'today task', dueAt: Date.now() })
    ]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('overdue task')).not.toBeNull())

    const overdueRow = screen.getByText('overdue task').closest('li') as HTMLElement
    expect(within(overdueRow).getByTitle('Set due date').className).toContain('text-rose-300/90')

    const todayRow = screen.getByText('today task').closest('li') as HTMLElement
    expect(within(todayRow).getByTitle('Set due date').className).not.toContain('text-rose-300/90')
  })

  it('labels the far-future bucket "Later" (not "Upcoming")', async () => {
    incomplete = [
      rec({ id: 3, backendId: 'b3', description: 'tomorrow task', dueAt: Date.now() + DAY }),
      rec({ id: 4, backendId: 'b4', description: 'later task', dueAt: Date.now() + 5 * DAY })
    ]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('later task')).not.toBeNull())

    const headers = screen.getAllByRole('heading').map((h) => h.textContent ?? '')
    expect(headers.some((h) => /^Later/.test(h))).toBe(true)
    expect(headers.some((h) => /Upcoming/i.test(h))).toBe(false)

    const laterSection = screen
      .getAllByRole('heading')
      .find((h) => /^Later/.test(h.textContent ?? ''))
      ?.closest('section') as HTMLElement
    expect(within(laterSection).getByText('later task')).not.toBeNull()
  })
})

describe('Tasks — freshness via onTasksChanged', () => {
  it('subscribes once and re-reads the store when the change event fires', async () => {
    incomplete = [rec({ id: 1, backendId: 'b1', description: 'first' })]
    await renderTasks()
    await waitFor(() => expect(screen.queryByText('first')).not.toBeNull())
    expect(tasks.onTasksChanged).toHaveBeenCalledTimes(1)

    const before = tasks.tasksListIncomplete.mock.calls.length
    incomplete = [rec({ id: 2, backendId: 'b2', description: 'second' })]
    changedCb?.()

    await waitFor(() => expect(tasks.tasksListIncomplete.mock.calls.length).toBeGreaterThan(before))
    await waitFor(() => expect(screen.queryByText('second')).not.toBeNull())
  })
})
