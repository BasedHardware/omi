// Server-side conversation search — mobile/macOS parity for the Conversations
// page. Mac reference: ConversationsPage.swift (submitSearch/performSearch) +
// LiveConversationRemoteDataSource.search — a 250ms debounce, then
// POST /v1/conversations/search (page 1, per_page 50, discarded excluded).
//
// Why a remote call at all: the list fetch is a single page of the newest
// conversations, and the old client-side `matchesQuery` could only see the title
// and the overview snippet of THAT page. The backend search is Typesense over
// every conversation the account owns and (since transcript-chunk indexing) over
// the spoken words too — so a term said in a meeting three months ago is
// findable, exactly like the phone app.
//
// The search endpoint accepts text + a date window only; folder/starred/type
// refinements are applied to the returned rows by the same pure predicates the
// list uses (ConversationSearchResultFilter on Mac), so search and list share
// identical AND semantics without a second backend endpoint. Local-only rows
// (recordings still syncing, saved chats) are not in Typesense; the page keeps
// matching those by title/preview on the client and appends them.

import { omiApi } from '../apiClient'
import type { ConversationRow } from '../pageCache'
import type {
  ConversationSearchItem,
  SearchConversationsResponse,
  SearchRequest
} from '../omiApi.generated'
import { applyFilters, matchesQuery, type ConversationFilters, type DateRange } from './filtering'

/** Mac's DebouncedSearchCoordinator.standardDelayNanoseconds (250ms). */
export const SEARCH_DEBOUNCE_MS = 250

/** Mac fetches one page of 50; the backend clamps anything larger. */
export const SEARCH_PAGE_SIZE = 50

/** Safety cap so a very broad query cannot fan out unbounded parallel pages. */
export const SEARCH_MAX_PAGES = 20

/** Longest preview we lift from a spoken-word snippet or the overview. Matches
 *  the list's 200-char preview truncation. */
const PREVIEW_CHARS = 200

/** A search is "active" once the trimmed query is non-empty — the same rule the
 *  Mac coordinator uses (`DebouncedSearchCoordinator.isActive`). Whitespace-only
 *  input never hits the network. */
export function isSearchActive(query: string): boolean {
  return normalizeSearchQuery(query) !== ''
}

export function normalizeSearchQuery(query: string): string {
  return query.trim()
}

/** Request body for one search page. Dates travel as ISO strings because the
 *  backend parses them with datetime.fromisoformat. */
export function buildSearchRequest(
  query: string,
  dateRange: DateRange,
  page = 1,
  perPage = SEARCH_PAGE_SIZE
): SearchRequest {
  const body: SearchRequest = {
    query: normalizeSearchQuery(query),
    page,
    per_page: perPage,
    include_discarded: false
  }
  if (dateRange.start != null) body.start_date = new Date(dateRange.start).toISOString()
  if (dateRange.end != null) body.end_date = new Date(dateRange.end).toISOString()
  return body
}

function truncate(text: string): string {
  return text.length > PREVIEW_CHARS ? text.slice(0, PREVIEW_CHARS) + '…' : text
}

/** Map one search hit onto the list's row shape. The preview prefers the
 *  backend's spoken-word match snippet (so the row shows WHY it matched, like the
 *  phone app's search result header) and falls back to the overview. */
export function searchItemToRow(item: ConversationSearchItem): ConversationRow {
  const created = item.created_at ? new Date(item.created_at).getTime() : 0
  const snippet = item.match_snippets?.find((s) => s.text?.trim())?.text?.trim()
  const overview = item.structured?.overview?.trim()
  return {
    id: item.id,
    title: item.structured?.title || 'Untitled conversation',
    emoji: item.structured?.emoji || undefined,
    subtitle: item.created_at ? new Date(item.created_at).toLocaleString() : '',
    preview: snippet ? truncate(`“${snippet}”`) : overview ? truncate(overview) : '(no transcript)',
    source: 'cloud',
    starred: item.starred ?? undefined,
    folderId: item.folder_id ?? null,
    sortAt: created
  }
}

/** One page of remote hits as list rows, newest first. Throws on transport/5xx
 *  so the page can show the "couldn't search" state (a 503 is what the backend
 *  returns when Typesense is unavailable). */
function rowsFromSearchItems(items: unknown[]): ConversationRow[] {
  return items
    .filter((item): item is ConversationSearchItem => {
      const hit = item as ConversationSearchItem
      return !!item && typeof hit.id === 'string' && !hit.is_locked
    })
    .map(searchItemToRow)
}

export async function searchConversations(
  query: string,
  dateRange: DateRange
): Promise<ConversationRow[]> {
  const r = await omiApi.post<SearchConversationsResponse>(
    '/v1/conversations/search',
    buildSearchRequest(query, dateRange)
  )
  const data = r.data
  let items = Array.isArray(data?.items) ? data.items : []
  const totalPages = Math.min(
    typeof data?.total_pages === 'number' && data.total_pages > 0 ? data.total_pages : 1,
    SEARCH_MAX_PAGES
  )
  if (totalPages > 1) {
    const extraPages = await Promise.all(
      Array.from({ length: totalPages - 1 }, (_, i) =>
        omiApi.post<SearchConversationsResponse>(
          '/v1/conversations/search',
          buildSearchRequest(query, dateRange, i + 2)
        )
      )
    )
    for (const page of extraPages) {
      const pageItems = Array.isArray(page.data?.items) ? page.data.items : []
      items = items.concat(pageItems)
    }
  }
  const seen = new Set<string>()
  const rows = rowsFromSearchItems(items).filter((row) => {
    if (seen.has(row.id)) return false
    seen.add(row.id)
    return true
  })
  return rows.sort((a, b) => b.sortAt - a.sortAt)
}

/** Compose the rows shown while a search is active.
 *
 *  - Remote hits pass through folder/type/date but NOT the text predicate — a hit
 *    may match on spoken words that appear in neither the title nor the preview,
 *    and re-applying `matchesQuery` would silently drop exactly the results the
 *    server search exists to find.
 *  - Local rows (not indexed server-side) still match by title/preview on the
 *    client, then pass through the same folder/type/date predicates.
 *  - A local row whose cloud twin is already among the hits is dropped (the cloud
 *    row is the real one — same rule as hideSyncedLocals on the list).
 */
export function composeSearchRows(
  remote: ConversationRow[],
  localRows: ConversationRow[],
  filters: ConversationFilters
): ConversationRow[] {
  const remoteFiltered = applyFilters(remote, { ...filters, query: '' })
  const remoteIds = new Set(remoteFiltered.map((r) => r.id))
  const locals = localRows.filter(
    (r) => r.source === 'local' && !remoteIds.has(r.id) && matchesQuery(r, filters.query)
  )
  const localFiltered = applyFilters(locals, { ...filters, query: '' })
  return [...remoteFiltered, ...localFiltered].sort((a, b) => b.sortAt - a.sortAt)
}
