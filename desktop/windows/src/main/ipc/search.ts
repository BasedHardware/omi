// Renderer-facing surface for local search.
//
// Reads only, so it is not gated to the main window: every UI window is allowed
// to search the corpora the signed-in user already sees, and there is nothing
// here to mutate. The write-side surfaces (starring, completing a task) keep
// their own existing channels and guards.

import { ipcMain } from 'electron'
import { searchDesktopCorpora } from './db'
import { PER_CORPUS_LIMIT } from '../search/desktopSearch'
import type { DesktopSearchResult } from '../../shared/types'

const EMPTY: DesktopSearchResult = {
  memories: { hits: [], total: 0 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 }
}

/** Longest query text accepted. A search box can be pasted into; an unbounded
 *  string becomes an unbounded FTS expression and a slow query on every
 *  keystroke. Long queries are truncated rather than refused, because refusing
 *  would make the box look broken. */
export const MAX_QUERY_CHARS = 200

export function searchLocalCorpora(query: unknown, limit?: unknown): DesktopSearchResult {
  if (typeof query !== 'string') return EMPTY
  const text = query.slice(0, MAX_QUERY_CHARS)
  const bounded =
    typeof limit === 'number' && Number.isFinite(limit)
      ? Math.max(1, Math.min(Math.floor(limit), PER_CORPUS_LIMIT))
      : PER_CORPUS_LIMIT
  try {
    return searchDesktopCorpora(text, bounded)
  } catch (e) {
    // A search box must never take the window down. An unusable index (mid
    // recovery, mid migration) degrades to "no local results" while the
    // server-side conversation search the renderer runs in parallel still works.
    console.error('[search] local search failed', e)
    return EMPTY
  }
}

export function registerSearchHandlers(): void {
  ipcMain.handle('omi-search:local', (_e, query: unknown, limit?: unknown) =>
    searchLocalCorpora(query, limit)
  )
}
