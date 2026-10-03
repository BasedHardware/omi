// @vitest-environment jsdom
//
// The Search page drives window.omi.searchLocal plus the conversation search
// endpoint. These tests mock both and assert the behaviors that decide whether
// someone trusts the result list: that a capped list says so, that an
// unreachable corpus is named rather than shown as empty, that "nothing matches"
// names the text that was searched, and that Escape does not strand the page.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { DesktopSearchResult } from '../../../shared/types'

const searchLocal = vi.fn()
const post = vi.fn()
const navigate = vi.fn()

vi.mock('../lib/apiClient', () => ({ omiApi: { post: (...a: unknown[]) => post(...a) } }))
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const { Search } = await import('./Search')

const EPOCH = Date.parse('2026-08-15T10:00:00Z')

const local = (over: Partial<DesktopSearchResult> = {}): DesktopSearchResult => ({
  memories: { hits: [], total: 0 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 },
  ...over
})

const memoryHits = (n: number): DesktopSearchResult['memories']['hits'] =>
  Array.from({ length: n }, (_v, i) => ({
    kind: 'memory' as const,
    id: String(i),
    title: `memory ${i}`,
    detail: '',
    timestamp: EPOCH
  }))

const conversationsResponse = (
  items: Array<{ id: string; title: string }>,
  totalPages = 1
): { data: unknown } => ({
  data: {
    items: items.map((i) => ({
      id: i.id,
      created_at: '2026-08-15T10:00:00Z',
      started_at: '2026-08-15T10:00:00Z',
      finished_at: null,
      structured: { title: i.title, overview: '' }
    })),
    current_page: 1,
    per_page: 20,
    total_pages: totalPages
  }
})

beforeEach(() => {
  searchLocal.mockReset().mockResolvedValue(local())
  post.mockReset().mockResolvedValue(conversationsResponse([]))
  navigate.mockReset()
  ;(window as unknown as { omi: unknown }).omi = { searchLocal }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const mount = (): void => {
  render(
    <MemoryRouter>
      <Search />
    </MemoryRouter>
  )
}

const type = (text: string): void => {
  fireEvent.change(screen.getByLabelText('Search'), { target: { value: text } })
}

describe('Search page', () => {
  it('prompts before anything is typed and does not search', async () => {
    mount()
    expect(screen.getByText('Search everything Omi has kept for you.')).toBeTruthy()
    expect(searchLocal).not.toHaveBeenCalled()
  })

  it('asks for more characters instead of searching a single letter', async () => {
    mount()
    type('l')
    await waitFor(() => expect(screen.getByText('Type at least 2 characters.')).toBeTruthy())
    expect(searchLocal).not.toHaveBeenCalled()
  })

  it('shows results grouped by corpus', async () => {
    post.mockResolvedValue(conversationsResponse([{ id: 'c1', title: 'Lease renewal' }]))
    searchLocal.mockResolvedValue(local({ memories: { hits: memoryHits(2), total: 2 } }))
    mount()
    type('lease')

    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())
    expect(screen.getByText('Conversations')).toBeTruthy()
    expect(screen.getByText('Memories')).toBeTruthy()
    // Tasks and Screen had nothing and did not fail, so they are left out
    // entirely rather than shown as empty headings.
    expect(screen.queryByText('Tasks')).toBeNull()
  })

  it('says how much of a capped corpus it is showing', async () => {
    searchLocal.mockResolvedValue(local({ memories: { hits: memoryHits(20), total: 300 } }))
    mount()
    type('standup')
    // Showing 20 while 300 matched, without saying so, would stop someone
    // looking any further.
    await waitFor(() => expect(screen.getByText('Showing 20 of 300')).toBeTruthy())
  })

  it('marks a multi-page conversation total as a lower bound', async () => {
    post.mockResolvedValue(
      conversationsResponse(
        Array.from({ length: 20 }, (_v, i) => ({ id: `c${i}`, title: `conv ${i}` })),
        3
      )
    )
    mount()
    type('lease')
    await waitFor(() => expect(screen.getByText('Showing 20 of 41+')).toBeTruthy())
  })

  it('names an unreachable corpus rather than showing it as empty', async () => {
    post.mockRejectedValue(new Error('offline'))
    searchLocal.mockResolvedValue(local({ tasks: { hits: memoryHits(1), total: 1 } }))
    mount()
    type('lease')

    await waitFor(() => expect(screen.getByText('Could not be searched')).toBeTruthy())
    // The distinction that matters: "could not be searched" is not the same
    // claim as "you have nothing about that".
    expect(
      screen.getByText('Conversations could not be searched, so these results are incomplete.')
    ).toBeTruthy()
  })

  it('reports search as unavailable when nothing at all could be searched', async () => {
    post.mockRejectedValue(new Error('offline'))
    searchLocal.mockRejectedValue(new Error('database is locked'))
    mount()
    type('lease')
    await waitFor(() => expect(screen.getByText('Search unavailable')).toBeTruthy())
  })

  it('names the searched text when nothing matches', async () => {
    mount()
    type('quarterly')
    await waitFor(() => expect(screen.getByText('Nothing matches “quarterly”.')).toBeTruthy())
  })

  it('opens a conversation result at its detail route', async () => {
    post.mockResolvedValue(conversationsResponse([{ id: 'abc123', title: 'Lease renewal' }]))
    mount()
    type('lease')
    await waitFor(() => expect(screen.getByText('Lease renewal')).toBeTruthy())

    fireEvent.click(screen.getByText('Lease renewal'))
    expect(navigate).toHaveBeenCalledWith('/conversations/abc123')
  })

  it('clears the box on Escape, and leaves the page on a second Escape', async () => {
    mount()
    const box = screen.getByLabelText('Search') as HTMLInputElement
    type('lease')
    await waitFor(() => expect(box.value).toBe('lease'))

    fireEvent.keyDown(box, { key: 'Escape' })
    await waitFor(() => expect(box.value).toBe(''))
    expect(navigate).not.toHaveBeenCalled()

    // useKeyboardNav ignores keys pressed inside an input, so without the page
    // handling this an empty box would swallow Escape and strand the page.
    fireEvent.keyDown(box, { key: 'Escape' })
    expect(navigate).toHaveBeenCalledWith('/home')
  })

  it('sends one search for a burst of typing, not one per letter', async () => {
    mount()
    type('l')
    type('le')
    type('lea')
    type('lease')
    await waitFor(() => expect(searchLocal).toHaveBeenCalled())
    expect(searchLocal).toHaveBeenCalledTimes(1)
    expect(searchLocal).toHaveBeenCalledWith('lease')
  })

  it('keeps showing the searching state until the first answer arrives', async () => {
    let release!: (v: unknown) => void
    post.mockReturnValue(
      new Promise((r) => {
        release = r
      })
    )
    mount()
    type('lease')
    await waitFor(() => expect(screen.getByText('Searching…')).toBeTruthy())
    // Rendering "nothing found" here would claim the data is missing when it
    // simply has not arrived.
    expect(screen.queryByText('No matches')).toBeNull()
    release(conversationsResponse([]))
  })
})
