import { describe, expect, it, vi } from 'vitest'
import {
  MIN_QUERY_LENGTH,
  SearchRunner,
  conversationSlice,
  conversationTimestamp,
  conversationTitle,
  isSearchable,
  runSearch,
  type SearchDeps,
  type SearchResults
} from './runSearch'
import type { Conversation, SearchConversationsResponse } from '../omiApi.generated'
import type { DesktopSearchResult } from '../../../../shared/types'

const EPOCH_ISO = '2026-08-15T10:00:00Z'
const EPOCH_MS = Date.parse(EPOCH_ISO)

const conversation = (over: Partial<Conversation> = {}): Conversation =>
  ({
    id: 'c1',
    created_at: EPOCH_ISO,
    started_at: EPOCH_ISO,
    finished_at: EPOCH_ISO,
    structured: { title: 'Lease renewal', overview: 'We agreed to renew' },
    ...over
  }) as Conversation

const localResult = (over: Partial<DesktopSearchResult> = {}): DesktopSearchResult => ({
  memories: { hits: [], total: 0 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 },
  ...over
})

const deps = (over: Partial<SearchDeps> = {}): SearchDeps => ({
  searchLocal: async () => localResult(),
  searchConversations: async () => ({
    items: [conversation()],
    current_page: 1,
    per_page: 20,
    total_pages: 1
  }),
  ...over
})

const signal = (): AbortSignal => new AbortController().signal

describe('isSearchable', () => {
  it('needs more than a character before it will search', () => {
    expect(isSearchable('a')).toBe(false)
    expect(isSearchable('  a  ')).toBe(false)
    expect(isSearchable('ab')).toBe(true)
    expect(MIN_QUERY_LENGTH).toBe(2)
  })
})

describe('conversationTitle', () => {
  it('prefers the title, falls back to the overview, then to a label', () => {
    expect(conversationTitle(conversation())).toBe('Lease renewal')
    expect(
      conversationTitle(conversation({ structured: { title: '  ', overview: 'Just an overview' } }))
    ).toBe('Just an overview')
    // An untitled conversation is normal before processing finishes; a blank row
    // would look like a broken result.
    expect(conversationTitle(conversation({ structured: {} }))).toBe('Untitled conversation')
  })

  it('truncates a long overview used as a title', () => {
    const long = 'x'.repeat(200)
    const title = conversationTitle(conversation({ structured: { overview: long } }))
    expect(title.length).toBe(90)
    expect(title.endsWith('…')).toBe(true)
  })
})

describe('conversationTimestamp', () => {
  it('uses the capture time, falling back to creation', () => {
    expect(conversationTimestamp(conversation())).toBe(EPOCH_MS)
    expect(conversationTimestamp(conversation({ started_at: null }))).toBe(EPOCH_MS)
  })

  it('survives an unparseable date instead of producing NaN', () => {
    // NaN would sort unpredictably and render as "Invalid Date".
    expect(conversationTimestamp(conversation({ started_at: 'not a date', created_at: '' }))).toBe(
      0
    )
  })
})

describe('conversationSlice', () => {
  it('counts a single page exactly', () => {
    const slice = conversationSlice({
      items: [conversation(), conversation({ id: 'c2' })],
      current_page: 1,
      per_page: 20,
      total_pages: 1
    })
    expect(slice.total).toBe(2)
    expect(slice.atLeast).toBe(false)
    expect(slice.hits.map((h) => h.kind)).toEqual(['conversation', 'conversation'])
  })

  it('reports a multi-page result as an at-least, never as an exact count', () => {
    // The endpoint reports pages, not rows. Three pages of 20 means "at least
    // 41" — claiming 60 would invent up to 19 conversations.
    const slice = conversationSlice({
      items: Array.from({ length: 20 }, (_v, i) => conversation({ id: `c${i}` })),
      current_page: 1,
      per_page: 20,
      total_pages: 3
    })
    expect(slice.total).toBe(41)
    // A page count cannot say how full the last page is, so 41 is a floor.
    expect(slice.atLeast).toBe(true)
  })

  it('survives a malformed response instead of throwing at the page', () => {
    const slice = conversationSlice({} as SearchConversationsResponse)
    expect(slice).toEqual({ hits: [], total: 0, failed: false, atLeast: false })
  })
})

describe('runSearch', () => {
  it('searches both sources and labels every corpus', async () => {
    const out = await runSearch(
      'lease',
      signal(),
      deps({
        searchLocal: async () =>
          localResult({
            memories: {
              hits: [
                { kind: 'memory', id: '1', title: 'Prefers the lease', detail: '', timestamp: 1 }
              ],
              total: 4
            }
          })
      })
    )
    expect(out.query).toBe('lease')
    expect(out.conversations.hits.length).toBe(1)
    expect(out.memories.total).toBe(4)
    expect([out.conversations, out.memories, out.tasks, out.screen].every((s) => !s.failed)).toBe(
      true
    )
  })

  it('still shows local results when the conversation search fails', async () => {
    const out = await runSearch(
      'lease',
      signal(),
      deps({
        searchConversations: async () => {
          throw new Error('offline')
        },
        searchLocal: async () => localResult({ tasks: { hits: [], total: 7 } })
      })
    )
    // A blank page, or an empty list that reads as "you have nothing about
    // that", would both be wrong.
    expect(out.conversations.failed).toBe(true)
    expect(out.tasks.failed).toBe(false)
    expect(out.tasks.total).toBe(7)
  })

  it('still shows conversations when the local index is unusable', async () => {
    const out = await runSearch(
      'lease',
      signal(),
      deps({
        searchLocal: async () => {
          throw new Error('database is locked')
        }
      })
    )
    expect(out.conversations.hits.length).toBe(1)
    expect(out.memories.failed).toBe(true)
    expect(out.tasks.failed).toBe(true)
    expect(out.screen.failed).toBe(true)
  })

  it('marks every local corpus failed together, since one call serves all three', async () => {
    const out = await runSearch(
      'lease',
      signal(),
      deps({
        searchLocal: async () => {
          throw new Error('nope')
        }
      })
    )
    expect([out.memories.failed, out.tasks.failed, out.screen.failed]).toEqual([true, true, true])
  })

  it('does not search a query that is too short', async () => {
    const searchLocal = vi.fn()
    const searchConversations = vi.fn()
    const out = await runSearch('a', signal(), deps({ searchLocal, searchConversations }))
    expect(searchLocal).not.toHaveBeenCalled()
    expect(searchConversations).not.toHaveBeenCalled()
    expect(out.query).toBe('a')
  })

  it('searches the trimmed text and echoes back what it searched', async () => {
    const searchLocal = vi.fn(async () => localResult())
    const out = await runSearch('  lease  ', signal(), deps({ searchLocal }))
    expect(searchLocal).toHaveBeenCalledWith('lease')
    // The page renders "nothing for X" from this, never from the live input, so
    // the message can never name a different word than the one searched.
    expect(out.query).toBe('lease')
  })
})

describe('SearchRunner', () => {
  const resolvable = (): {
    promise: Promise<SearchConversationsResponse>
    resolve: (r: SearchConversationsResponse) => void
  } => {
    let resolve!: (r: SearchConversationsResponse) => void
    const promise = new Promise<SearchConversationsResponse>((r) => {
      resolve = r
    })
    return { promise, resolve }
  }

  it('drops a slow answer that lands after a newer one', async () => {
    const slow = resolvable()
    const fast = resolvable()
    const queue = [slow.promise, fast.promise]
    const runner = new SearchRunner(
      deps({
        searchConversations: async () => queue.shift() as Promise<SearchConversationsResponse>
      })
    )

    const delivered: SearchResults[] = []
    const first = runner.run('le', (r) => delivered.push(r))
    const second = runner.run('lease', (r) => delivered.push(r))

    // The newer query answers first, then the older one finally arrives.
    fast.resolve({
      items: [conversation({ id: 'new' })],
      current_page: 1,
      per_page: 20,
      total_pages: 1
    })
    await second
    slow.resolve({
      items: [conversation({ id: 'old' })],
      current_page: 1,
      per_page: 20,
      total_pages: 1
    })
    await first

    // Typing "lease" fires a request per keystroke; "le" resolving last must not
    // put its results back on screen.
    expect(delivered.length).toBe(1)
    expect(delivered[0].query).toBe('lease')
  })

  it('delivers results for a single run', async () => {
    const runner = new SearchRunner(deps())
    const delivered: SearchResults[] = []
    await runner.run('lease', (r) => delivered.push(r))
    expect(delivered.map((d) => d.query)).toEqual(['lease'])
  })

  it('aborts the request still in flight when a newer search starts', async () => {
    const aborted: string[] = []
    const first = resolvable()
    const queue = [first.promise]
    const runner = new SearchRunner(
      deps({
        searchConversations: async (q, s) => {
          s.addEventListener('abort', () => aborted.push(q))
          const queued = queue.shift()
          if (queued) return queued
          return { items: [], current_page: 1, per_page: 20, total_pages: 1 }
        }
      })
    )
    // Deliberately NOT awaited: the point is that the first request is still
    // open when the second starts, which is what typing produces.
    const pending = runner.run('lea', () => undefined)
    await runner.run('lease', () => undefined)
    expect(aborted).toEqual(['lea'])

    first.resolve({ items: [], current_page: 1, per_page: 20, total_pages: 1 })
    await pending
  })

  it('cancel stops a pending run from delivering', async () => {
    const pending = resolvable()
    const runner = new SearchRunner(deps({ searchConversations: async () => pending.promise }))
    const delivered: SearchResults[] = []
    const run = runner.run('lease', (r) => delivered.push(r))
    runner.cancel()
    pending.resolve({ items: [], current_page: 1, per_page: 20, total_pages: 1 })
    await run
    expect(delivered).toEqual([])
  })
})
