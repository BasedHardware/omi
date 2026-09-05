// One query, four corpora, two very different sources.
//
// Memories, tasks and captured screen text are indexed on this machine and come
// back from main in a millisecond. Conversations live only in the cloud (the
// local cache holds the last 200), so they are searched through
// `POST /v1/conversations/search`, which covers the whole history.
//
// Three properties this module exists to hold:
//
// 1. THE TWO SOURCES ARE INDEPENDENT. A failed conversation request must still
//    show local results, and an unusable local index must still show
//    conversations. Each corpus reports its own `failed`, so the UI can say which
//    part is missing instead of showing a blank page or, worse, an empty result
//    list that reads as "you have nothing about that".
//
// 2. A SLOW ANSWER NEVER OVERWRITES A NEWER ONE. Typing "lease" fires a request
//    per keystroke; "l" can easily resolve after "lease". Every run carries a
//    monotonic sequence number and the caller drops anything that is not the
//    latest, so the results on screen always belong to the text in the box.
//
// 3. THE QUERY IS ECHOED BACK. The caller renders "no results for X" from the
//    query the results were computed FROM, never from the current input, so the
//    message can never name a different word than the one that was searched.

import { omiApi } from '../apiClient'
import type { Conversation, SearchConversationsResponse } from '../omiApi.generated'
import type { CorpusHit, CorpusSlice, DesktopSearchResult } from '../../../../shared/types'

export type SearchCorpus = 'conversations' | 'memories' | 'tasks' | 'screen'

export interface SearchSlice extends CorpusSlice {
  /** True when this corpus could not be searched at all. Distinct from an empty
   *  slice, which means "searched, found nothing". */
  failed: boolean
  /** True when `total` is a lower bound rather than an exact count. The
   *  conversation endpoint reports pages, not rows, so a multi-page result is
   *  only known to a page's granularity and must be shown as "41+", never "41". */
  atLeast: boolean
}

export interface SearchResults {
  /** The text these results were computed from. */
  query: string
  conversations: SearchSlice
  memories: SearchSlice
  tasks: SearchSlice
  screen: SearchSlice
}

/** Conversations requested per search. Matches the local per-corpus limit so no
 *  corpus visually dominates the page just by being fetched deeper. */
export const CONVERSATION_PAGE_SIZE = 20

/** Shortest query that is searched. One or two characters match a large fraction
 *  of everything and produce a result list that is noise, plus a request per
 *  keystroke that is never useful. */
export const MIN_QUERY_LENGTH = 2

const emptySlice = (): SearchSlice => ({ hits: [], total: 0, failed: false, atLeast: false })
const failedSlice = (): SearchSlice => ({ hits: [], total: 0, failed: true, atLeast: false })

export const emptyResults = (query = ''): SearchResults => ({
  query,
  conversations: emptySlice(),
  memories: emptySlice(),
  tasks: emptySlice(),
  screen: emptySlice()
})

/** True when a query is worth sending. Exported so the UI shows its prompt state
 *  from the same rule the search uses, instead of a second copy that can drift. */
export function isSearchable(query: string): boolean {
  return query.trim().length >= MIN_QUERY_LENGTH
}

/** A conversation's display title, falling back through the fields that are
 *  actually populated. An untitled conversation is common (it is titled after
 *  processing), so it must not render as a blank row. */
export function conversationTitle(c: Conversation): string {
  const title = c.structured?.title?.trim()
  if (title) return title
  const overview = c.structured?.overview?.trim()
  if (overview) return overview.length > 90 ? `${overview.slice(0, 89)}…` : overview
  return 'Untitled conversation'
}

/** Epoch ms for ordering. `started_at` is the capture time and is what every
 *  other conversation surface sorts by; `created_at` is the fallback for rows
 *  that never got one. */
export function conversationTimestamp(c: Conversation): number {
  const raw = c.started_at ?? c.created_at
  const ms = raw ? Date.parse(raw) : Number.NaN
  return Number.isFinite(ms) ? ms : 0
}

export function conversationToHit(c: Conversation): CorpusHit {
  return {
    kind: 'conversation',
    id: c.id,
    title: conversationTitle(c),
    detail: c.structured?.overview?.trim() ?? '',
    timestamp: conversationTimestamp(c)
  }
}

/** Maps a search response onto a slice. `total_pages` is what the endpoint
 *  reports, so the true total is only known to a page's granularity: a result
 *  set of 3 pages is "more than 40", not "60". The caller renders that as an
 *  at-least, never as an exact count. */
export function conversationSlice(res: SearchConversationsResponse): SearchSlice {
  const items = Array.isArray(res?.items) ? res.items : []
  const pages = Number.isFinite(res?.total_pages) ? Math.max(1, res.total_pages) : 1
  const perPage = Number.isFinite(res?.per_page) && res.per_page > 0 ? res.per_page : items.length
  return {
    hits: items.map(conversationToHit),
    // Everything before the last page is full; the last page holds at least one.
    total: pages > 1 ? (pages - 1) * perPage + 1 : items.length,
    failed: false,
    atLeast: pages > 1
  }
}

export interface SearchDeps {
  searchLocal: (query: string) => Promise<DesktopSearchResult>
  searchConversations: (query: string, signal: AbortSignal) => Promise<SearchConversationsResponse>
}

/** Production dependencies. Split out so tests drive the orchestration without
 *  Electron or the network. */
export const defaultDeps: SearchDeps = {
  searchLocal: async (query) => {
    const api = window.omi
    if (!api?.searchLocal) throw new Error('local search unavailable')
    return api.searchLocal(query)
  },
  searchConversations: async (query, signal) => {
    const res = await omiApi.post<SearchConversationsResponse>(
      '/v1/conversations/search',
      { query, page: 1, per_page: CONVERSATION_PAGE_SIZE },
      { signal }
    )
    return res.data
  }
}

/**
 * Runs one search. Never rejects: a corpus that fails comes back with
 * `failed: true` so the page can name what is missing.
 *
 * `signal` aborts the conversation request; the local search is synchronous on
 * the main side and completes either way, which costs nothing.
 */
export async function runSearch(
  query: string,
  signal: AbortSignal,
  deps: SearchDeps = defaultDeps
): Promise<SearchResults> {
  const text = query.trim()
  if (!isSearchable(text)) return emptyResults(text)

  const [local, conversations] = await Promise.all([
    deps
      .searchLocal(text)
      .then((r) => ({ ok: true as const, r }))
      .catch(() => ({ ok: false as const, r: null })),
    deps
      .searchConversations(text, signal)
      .then((r) => ({ ok: true as const, r }))
      .catch(() => ({ ok: false as const, r: null }))
  ])

  const localSlice = (pick: (r: DesktopSearchResult) => CorpusSlice): SearchSlice =>
    local.ok && local.r !== null
      ? { ...pick(local.r), failed: false, atLeast: false }
      : failedSlice()

  return {
    query: text,
    conversations:
      conversations.ok && conversations.r !== null
        ? conversationSlice(conversations.r)
        : failedSlice(),
    memories: localSlice((r) => r.memories),
    tasks: localSlice((r) => r.tasks),
    screen: localSlice((r) => r.screen)
  }
}

/**
 * Serialises searches so a slow answer can never replace a newer one.
 *
 * Every call bumps a sequence number and aborts the previous request. A result
 * is delivered only if its sequence is still the latest, so the list on screen
 * always belongs to the text that produced it.
 */
export class SearchRunner {
  private seq = 0
  private inFlight: AbortController | null = null

  constructor(private readonly deps: SearchDeps = defaultDeps) {}

  /** Cancels anything in flight. Delivered results stay on screen. */
  cancel(): void {
    this.inFlight?.abort()
    this.inFlight = null
    this.seq += 1
  }

  /**
   * Runs `query` and calls `onResults` only when this run is still the newest.
   * Returns the sequence number used, for tests and diagnostics.
   */
  async run(query: string, onResults: (results: SearchResults) => void): Promise<number> {
    this.inFlight?.abort()
    const controller = new AbortController()
    this.inFlight = controller
    this.seq += 1
    const mine = this.seq

    const results = await runSearch(query, controller.signal, this.deps)
    if (mine !== this.seq) return mine
    this.inFlight = null
    onResults(results)
    return mine
  }
}

/** Corpora in the order the page presents them. Conversations lead because they
 *  are what people search for most and the only corpus covering all of history. */
export const CORPUS_ORDER: SearchCorpus[] = ['conversations', 'memories', 'tasks', 'screen']

export const CORPUS_LABELS: Record<SearchCorpus, string> = {
  conversations: 'Conversations',
  memories: 'Memories',
  tasks: 'Tasks',
  screen: 'Screen'
}

export function sliceFor(results: SearchResults, corpus: SearchCorpus): SearchSlice {
  return results[corpus]
}
