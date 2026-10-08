import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationRow } from '../pageCache'
import type { ConversationSearchItem } from '../omiApi.generated'
import { NO_DATE_RANGE, type ConversationFilters } from './filtering'

const postMock = vi.fn()
vi.mock('../apiClient', () => ({
  omiApi: { post: (...args: unknown[]) => postMock(...args) }
}))

import {
  SEARCH_PAGE_SIZE,
  buildSearchRequest,
  composeSearchRows,
  isSearchActive,
  searchConversations,
  searchItemToRow
} from './search'

function item(over: Partial<ConversationSearchItem> = {}): ConversationSearchItem {
  return {
    id: 'c1',
    created_at: '2026-03-02T10:00:00Z',
    started_at: null,
    finished_at: null,
    structured: { title: 'Roadmap review', overview: 'We planned Q3.' } as never,
    ...over
  }
}

function row(over: Partial<ConversationRow> = {}): ConversationRow {
  return {
    id: 'r1',
    title: 'Untitled',
    subtitle: '',
    preview: '',
    source: 'cloud',
    sortAt: 0,
    ...over
  }
}

const ALL: ConversationFilters = {
  folder: { kind: 'all' },
  type: 'all',
  query: 'budget',
  dateRange: NO_DATE_RANGE
}

beforeEach(() => postMock.mockReset())

describe('isSearchActive', () => {
  it('is false for empty or whitespace-only input (never hits the network)', () => {
    expect(isSearchActive('')).toBe(false)
    expect(isSearchActive('   ')).toBe(false)
    expect(isSearchActive(' q ')).toBe(true)
  })
})

describe('buildSearchRequest', () => {
  it('mirrors the Mac client: page 1 of 50, discarded excluded, trimmed query', () => {
    expect(buildSearchRequest('  budget ', NO_DATE_RANGE)).toEqual({
      query: 'budget',
      page: 1,
      per_page: SEARCH_PAGE_SIZE,
      include_discarded: false
    })
  })

  it('serializes the date window as ISO strings (backend parses fromisoformat)', () => {
    const start = Date.UTC(2026, 0, 1)
    const end = Date.UTC(2026, 0, 31, 23, 59, 59)
    const body = buildSearchRequest('q', { start, end })
    expect(body.start_date).toBe(new Date(start).toISOString())
    expect(body.end_date).toBe(new Date(end).toISOString())
  })

  it('omits the date keys when the range is open', () => {
    const body = buildSearchRequest('q', NO_DATE_RANGE)
    expect('start_date' in body).toBe(false)
    expect('end_date' in body).toBe(false)
  })
})

describe('searchItemToRow', () => {
  it('maps a hit to a cloud row with title/emoji/star/folder', () => {
    const r = searchItemToRow(
      item({
        structured: { title: 'Standup', emoji: '📣', overview: 'Short one.' } as never,
        starred: true,
        folder_id: 'f9'
      })
    )
    expect(r).toMatchObject({
      id: 'c1',
      title: 'Standup',
      emoji: '📣',
      preview: 'Short one.',
      source: 'cloud',
      starred: true,
      folderId: 'f9',
      sortAt: new Date('2026-03-02T10:00:00Z').getTime()
    })
  })

  it('prefers the spoken-word match snippet over the overview as the preview', () => {
    const r = searchItemToRow(
      item({ match_snippets: [{ text: '  we need to cut the budget by ten percent  ' }] })
    )
    expect(r.preview).toBe('“we need to cut the budget by ten percent”')
  })

  it('falls back to the overview, then to a placeholder', () => {
    expect(searchItemToRow(item({ match_snippets: [{ text: '   ' }] })).preview).toBe(
      'We planned Q3.'
    )
    expect(searchItemToRow(item({ structured: {} as never })).preview).toBe('(no transcript)')
    expect(searchItemToRow(item({ structured: {} as never })).title).toBe('Untitled conversation')
  })
})

describe('searchConversations', () => {
  it('POSTs to /v1/conversations/search and returns rows newest-first, dropping locked hits', async () => {
    postMock.mockResolvedValue({
      data: {
        items: [
          item({ id: 'old', created_at: '2026-01-01T00:00:00Z' }),
          item({ id: 'locked', is_locked: true }),
          item({ id: 'new', created_at: '2026-06-01T00:00:00Z' })
        ],
        total_pages: 1,
        current_page: 1,
        per_page: 50
      }
    })
    const rows = await searchConversations(' budget ', NO_DATE_RANGE)
    expect(postMock).toHaveBeenCalledWith('/v1/conversations/search', {
      query: 'budget',
      page: 1,
      per_page: SEARCH_PAGE_SIZE,
      include_discarded: false
    })
    expect(rows.map((r) => r.id)).toEqual(['new', 'old'])
  })

  it('tolerates a malformed body', async () => {
    postMock.mockResolvedValue({ data: {} })
    expect(await searchConversations('q', NO_DATE_RANGE)).toEqual([])
  })

  it('propagates transport failures so the page can show the error state', async () => {
    postMock.mockImplementationOnce(() => Promise.reject(new Error('503')))
    await expect(searchConversations('q', NO_DATE_RANGE)).rejects.toThrow('503')
  })

  it('fetches additional pages when total_pages > 1 and dedupes by id', async () => {
    postMock
      .mockResolvedValueOnce({
        data: {
          items: [item({ id: 'p1-a' }), item({ id: 'dup' })],
          total_pages: 2,
          current_page: 1,
          per_page: 50
        }
      })
      .mockResolvedValueOnce({
        data: {
          items: [item({ id: 'dup' }), item({ id: 'p2-b', created_at: '2026-07-01T00:00:00Z' })],
          total_pages: 2,
          current_page: 2,
          per_page: 50
        }
      })
    const rows = await searchConversations('budget', NO_DATE_RANGE)
    expect(postMock).toHaveBeenCalledTimes(2)
    expect(postMock.mock.calls[1][1]).toMatchObject({ page: 2 })
    expect(rows.map((r) => r.id)).toEqual(['p2-b', 'p1-a', 'dup'])
  })
})

describe('composeSearchRows', () => {
  const remote = [
    // Matched on spoken words only: neither title nor preview contains the query.
    row({
      id: 'deep',
      title: 'Sync',
      preview: 'Nothing relevant here',
      sortAt: 100,
      starred: false
    }),
    row({ id: 'starred', title: 'Budget planning', sortAt: 200, starred: true, folderId: 'f1' })
  ]
  const locals = [
    row({
      id: 'l-match',
      source: 'local',
      localKind: 'recording',
      title: 'budget talk',
      sortAt: 150
    }),
    row({ id: 'l-miss', source: 'local', localKind: 'recording', title: 'lunch', sortAt: 160 }),
    row({ id: 'l-chat', source: 'local', localKind: 'chat', title: 'budget chat', sortAt: 170 })
  ]

  it('keeps every remote hit regardless of title/preview text and appends client-matched locals, newest first', () => {
    const out = composeSearchRows(remote, locals, ALL)
    expect(out.map((r) => r.id)).toEqual(['starred', 'l-chat', 'l-match', 'deep'])
  })

  it('applies folder/starred/type refinements to remote hits without a second request', () => {
    expect(
      composeSearchRows(remote, locals, { ...ALL, folder: { kind: 'starred' } }).map((r) => r.id)
    ).toEqual(['starred'])
    expect(
      composeSearchRows(remote, locals, { ...ALL, folder: { kind: 'folder', id: 'f1' } }).map(
        (r) => r.id
      )
    ).toEqual(['starred'])
    expect(composeSearchRows(remote, locals, { ...ALL, type: 'chat' }).map((r) => r.id)).toEqual([
      'l-chat'
    ])
  })

  it('drops a local twin whose cloud row is already among the hits', () => {
    const twin = row({
      id: 'deep',
      source: 'local',
      localKind: 'recording',
      title: 'budget',
      sortAt: 1
    })
    expect(composeSearchRows(remote, [twin], ALL).filter((r) => r.id === 'deep')).toHaveLength(1)
  })

  it('ignores cloud rows passed in the local list (only locals are client-matched)', () => {
    const cloudInList = row({ id: 'page-row', source: 'cloud', title: 'budget page row' })
    expect(composeSearchRows([], [cloudInList], ALL)).toEqual([])
  })
})
