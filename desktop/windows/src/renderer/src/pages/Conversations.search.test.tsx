// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mobile/macOS parity: the Conversations search field runs a debounced
// server-side search (POST /v1/conversations/search) instead of filtering the
// already-loaded page by title. This suite pins the page-level wiring through
// the real component: debounce coalescing, the request body, hits that would
// never match a title/preview filter being shown (with the spoken-word snippet
// as the preview), teardown on clear, and the error → retry path.

const getMock = vi.fn()
const postMock = vi.fn()
vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

import { Conversations } from './Conversations'
import { SEARCH_DEBOUNCE_MS } from '../lib/conversations/search'

const LIST = [
  {
    id: 'recent',
    created_at: '2026-09-10T10:00:00Z',
    structured: { title: 'Weekly sync', overview: 'Talked about hiring.' }
  }
]

const HITS = {
  items: [
    {
      id: 'deep',
      created_at: '2026-02-01T10:00:00Z',
      structured: { title: 'Q1 planning', overview: 'Roadmap for the quarter.' },
      match_snippets: [{ text: 'we should trim the budget before March' }]
    }
  ],
  total_pages: 1,
  current_page: 1,
  per_page: 50
}

const omiStub = {
  listLocalConversations: vi.fn().mockResolvedValue([]),
  listConversationFolders: vi.fn().mockResolvedValue([]),
  replaceConversationFolders: vi.fn().mockResolvedValue(undefined),
  updateLocalConversationSync: vi.fn().mockResolvedValue(undefined),
  deleteJitConversationKeyframe: vi.fn().mockResolvedValue(undefined)
}

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={['/conversations']}>
      <Conversations />
    </MemoryRouter>
  )
}

async function typeQuery(value: string): Promise<void> {
  fireEvent.change(await screen.findByLabelText('Search conversations'), { target: { value } })
}

beforeEach(() => {
  localStorage.clear()
  ;(window as unknown as { omi: unknown }).omi = omiStub
  getMock.mockReset()
  postMock.mockReset()
  getMock.mockImplementation((url: string) =>
    Promise.resolve({ data: url === '/v1/folders' ? [] : LIST })
  )
  postMock.mockResolvedValue({ data: HITS })
})
afterEach(cleanup)

describe('Conversations — server-side search', () => {
  it('POSTs the debounced query and shows hits the title filter could never find, with the snippet as preview', async () => {
    renderPage()
    await screen.findByText('Weekly sync')

    await typeQuery('budget')

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1))
    expect(postMock).toHaveBeenCalledWith('/v1/conversations/search', {
      query: 'budget',
      page: 1,
      per_page: 50,
      include_discarded: false
    })
    // The hit's title/overview don't contain "budget" — only its spoken words do.
    await screen.findByText('Q1 planning')
    expect(screen.getByText('“we should trim the budget before March”')).toBeTruthy()
    // The hits ARE the list while searching: the unrelated recent row is gone.
    expect(screen.queryByText('Weekly sync')).toBeNull()
    expect(screen.getByText('1 result')).toBeTruthy()
  })

  it('coalesces rapid keystrokes into a single request for the final text', async () => {
    renderPage()
    await screen.findByText('Weekly sync')

    await typeQuery('b')
    await typeQuery('bu')
    await typeQuery('budget')

    await screen.findByText('Q1 planning')
    expect(postMock).toHaveBeenCalledTimes(1)
    expect(postMock.mock.calls[0][1]).toMatchObject({ query: 'budget' })
  })

  it('never hits the network for a whitespace-only query', async () => {
    renderPage()
    await screen.findByText('Weekly sync')
    // Fake timers from here so the debounce window can be driven deterministically.
    vi.useFakeTimers()
    try {
      fireEvent.change(screen.getByLabelText('Search conversations'), { target: { value: '   ' } })
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 4)
      expect(postMock).not.toHaveBeenCalled()
      expect(screen.getByText('Weekly sync')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('clearing the field tears the search down and restores the list without another request', async () => {
    renderPage()
    await screen.findByText('Weekly sync')
    await typeQuery('budget')
    await screen.findByText('Q1 planning')

    fireEvent.click(screen.getByText('Clear'))

    await screen.findByText('Weekly sync')
    expect(screen.queryByText('Q1 planning')).toBeNull()
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('shows the error state when the search endpoint fails, and Try again re-runs the same query', async () => {
    postMock
      .mockImplementationOnce(() => Promise.reject(new Error('503')))
      .mockResolvedValue({ data: HITS })
    renderPage()
    await screen.findByText('Weekly sync')
    await typeQuery('budget')

    await screen.findByText('Couldn’t search conversations')
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }))

    await screen.findByText('Q1 planning')
    expect(postMock).toHaveBeenCalledTimes(2)
    expect(postMock.mock.calls[1][1]).toMatchObject({ query: 'budget' })
  })

  it('applies the starred refinement to hits client-side without a second request', async () => {
    postMock.mockResolvedValue({
      data: {
        ...HITS,
        items: [
          { ...HITS.items[0], starred: false },
          {
            id: 'starred-hit',
            created_at: '2026-03-01T10:00:00Z',
            structured: { title: 'Budget review', overview: '' },
            starred: true
          }
        ]
      }
    })
    renderPage()
    await screen.findByText('Weekly sync')
    await typeQuery('budget')
    await screen.findByText('Budget review')
    expect(screen.getByText('Q1 planning')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Starred/ }))

    await waitFor(() => expect(screen.queryByText('Q1 planning')).toBeNull())
    expect(screen.getByText('Budget review')).toBeTruthy()
    expect(postMock).toHaveBeenCalledTimes(1)
  })
})
