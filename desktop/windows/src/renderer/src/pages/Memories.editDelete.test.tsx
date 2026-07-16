// @vitest-environment jsdom
import { StrictMode } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { Memory } from '../hooks/useMemories'

// Drive the Memories page's edit/delete handlers through the real UI. The data
// hook is mocked so we can assert exactly which backend mutations fire, and the
// brain-map hook returns an empty graph so the WebGL canvas (unavailable in
// jsdom) is never mounted.
const editMemory = vi.fn()
const deleteMemory = vi.fn()
const setMemoryVisibility = vi.fn()
const createMemory = vi.fn()
const refresh = vi.fn()
let memoriesList: Memory[] = []

vi.mock('../hooks/useMemories', () => ({
  useMemories: () => ({
    memories: memoriesList,
    loading: false,
    error: null,
    canonicalLifecycleExposed: false,
    createMemory,
    editMemory,
    setMemoryVisibility,
    deleteMemory,
    refresh
  })
}))

vi.mock('../hooks/useMemoryGraph', () => ({
  useMemoryGraph: () => ({
    graph: { nodes: [], edges: [] },
    centerNodeId: undefined,
    rebuild: vi.fn(),
    rebuilding: false
  })
}))

vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
// memoriesBulk (pulled in for manage mode) imports the axios client at module
// load; stub it so the import doesn't touch the network. Manage mode isn't
// exercised here, so the methods are never called.
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
}))

const mem = (id: string, content: string): Memory => ({
  id,
  uid: 'u',
  content,
  visibility: 'private',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
})

async function renderPage(strict = false): Promise<void> {
  const { Memories } = await import('./Memories')
  const tree = (
    <MemoryRouter>
      <Memories />
    </MemoryRouter>
  )
  render(strict ? <StrictMode>{tree}</StrictMode> : tree)
}

beforeEach(() => {
  memoriesList = []
  editMemory.mockReset().mockResolvedValue(undefined)
  deleteMemory.mockReset().mockResolvedValue(undefined)
  setMemoryVisibility.mockReset().mockResolvedValue(undefined)
  createMemory.mockReset().mockResolvedValue(undefined)
  refresh.mockReset().mockResolvedValue(undefined)
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

describe('Memories — detail sheet stays in sync after an edit (FIX 1)', () => {
  it('shows the edited content in the open sheet instead of reverting to the stale prop', async () => {
    memoriesList = [mem('m1', 'Original content')]
    await renderPage()

    // Open the detail sheet, then enter edit mode.
    fireEvent.click(screen.getByText('Original content'))
    fireEvent.click(await screen.findByTitle('Click to edit'))

    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByRole('textbox'), {
      target: { value: 'Updated content' }
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(editMemory).toHaveBeenCalledWith('m1', 'Updated content'))

    // The sheet reflects the edit. The background card still shows the old text
    // (the mocked list is unchanged), so 'Updated content' uniquely marks the
    // sheet. Before the fix, detailMemory stayed stale and this text never
    // appeared — the sheet kept rendering 'Original content'.
    const openSheet = screen.getByRole('dialog')
    await waitFor(() => expect(within(openSheet).getByText('Updated content')).toBeTruthy())
    expect(within(openSheet).queryByText('Original content')).toBeNull()
  })
})

describe('Memories — a delete commits at most once (FIX 2)', () => {
  it('fires the backend delete exactly once when the pending delete is replaced under StrictMode', async () => {
    // StrictMode (on in main.tsx) double-invokes state updaters in dev. The old
    // code called commitDelete from INSIDE the setPendingDelete updater, so the
    // replacement path double-fired DELETE for the first memory (the second
    // hitting a 404 + spurious error toast). The commit now runs outside the
    // updater, and commitDelete is idempotent per id — so exactly one delete.
    memoriesList = [mem('a', 'Memory A'), mem('b', 'Memory B')]
    await renderPage(true)

    // Delete A → held in the undo window, nothing sent yet.
    fireEvent.click(screen.getByText('Memory A'))
    fireEvent.click(await screen.findByLabelText('Delete memory'))
    await screen.findByText('Memory deleted')
    expect(deleteMemory).not.toHaveBeenCalled()

    // Delete B → replaces the pending A, committing A's delete immediately.
    fireEvent.click(screen.getByText('Memory B'))
    fireEvent.click(await screen.findByLabelText('Delete memory'))

    await waitFor(() => expect(deleteMemory).toHaveBeenCalledWith('a'))
    expect(deleteMemory.mock.calls.filter((c) => c[0] === 'a')).toHaveLength(1)
  })
})
