// One search over everything this machine holds: memories, tasks, and captured
// screen text.
//
// Windows had no way to search any of it. Rewind had a frame-only search box and
// Settings had a settings-only one; a memory or a task could be found by
// scrolling and no other way. This module is the query half of that gap
// (conversations are searched server-side by the renderer, which is the only
// place the full history exists — see searchAllCorpora's doc comment).
//
// Two rules the shape of this file exists to enforce:
//
// 1. ONE matcher for the whole surface. `buildRewindFtsMatch` is already the
//    app's tuned user-facing FTS5 matcher (quoted phrase terms so punctuation can
//    never become query syntax, trailing `*` for prefix search, camelCase and
//    digit sub-parts expanded, tokens AND-joined so typing more narrows). Reusing
//    it means one query behaves the same way against every corpus, instead of the
//    three differently-tuned matchers the codebase already has for other jobs
//    (taskStore's sanitizeFtsQuery is exact-AND for agent tool calls;
//    toolBackends' buildFtsQuery is prefix-OR for dedup recall). It lives under
//    rewind/ for historical reasons; it is not rewind-specific.
//
// 2. NEVER interleave BM25 scores across corpora. A score from memories_fts and
//    one from rewind_frames_fts are computed over different document
//    populations, so comparing them is meaningless and would silently order
//    results by which index happens to have shorter documents. Results are
//    grouped per corpus and ranked inside it, and the caller decides presentation
//    order.

import { buildRewindFtsMatch } from '../rewind/rewindSearchQuery'
import { countMemoriesFts, searchMemoriesFts, type MemorySearchDb } from './memorySearchStore'
// The result shape crosses the IPC boundary, so shared/types.ts is its one
// definition and both sides import it from there.
import type { CorpusHit, CorpusSlice, DesktopSearchResult } from '../../shared/types'

/** Minimal DB surface — satisfied structurally by better-sqlite3 (production)
 *  and node:sqlite's DatabaseSync (tests). Positional `?` params only. */
export interface SearchDb {
  prepare(sql: string): {
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

/** Hits returned per corpus. Deliberately small: the surface shows a few strong
 *  results per corpus and reports the true total next to them. */
export const PER_CORPUS_LIMIT = 20

const EMPTY: DesktopSearchResult = {
  memories: { hits: [], total: 0 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 }
}

/**
 * Searches every local corpus for `query`.
 *
 * Returns empty slices (never throws) when the query has no indexable content,
 * so a search box can call this on every keystroke without guarding.
 *
 * Conversations are absent on purpose. Only the last 200 are cached locally, so
 * a local conversation search would quietly cover a fraction of someone's
 * history and present it as a search of all of it. The renderer searches them
 * through `POST /v1/conversations/search`, which covers the full history.
 */
export function searchAllCorpora(
  db: SearchDb,
  query: string,
  limit = PER_CORPUS_LIMIT
): DesktopSearchResult {
  const match = buildRewindFtsMatch(query)
  if (match === null) return EMPTY
  return {
    memories: searchMemorySlice(db, match, limit),
    tasks: searchTaskSlice(db, match, limit),
    screen: searchScreenSlice(db, match, limit)
  }
}

function countMatches(db: SearchDb, sql: string, match: string): number {
  const row = db.prepare(sql).get(match) as { n: number } | undefined
  return row?.n ?? 0
}

function searchMemorySlice(db: SearchDb, match: string, limit: number): CorpusSlice {
  // The memories SQL lives in memorySearchStore.ts next to the schema it reads,
  // so the index definition and its query can never drift apart.
  const store = db as unknown as MemorySearchDb
  return {
    hits: searchMemoriesFts(store, match, limit).map((r) => ({
      kind: 'memory' as const,
      id: String(r.id),
      title: r.content,
      detail: r.contextSummary ?? '',
      timestamp: r.createdAt
    })),
    total: countMemoriesFts(store, match)
  }
}

/**
 * Tasks span two tables: `action_items` (accepted) and `staged_tasks` (proposed
 * but not yet accepted). Both are things the user would call a task, so both are
 * searched and the results are merged.
 *
 * The merge orders by recency rather than by score: the two tables are separate
 * FTS indexes, so interleaving their BM25 scores would be the cross-corpus
 * comparison this module refuses to make everywhere else.
 *
 * Deleted rows are excluded from both, and completed action items are kept:
 * "what did I decide about the lease" is usually a question about finished work.
 */
function searchTaskSlice(db: SearchDb, match: string, limit: number): CorpusSlice {
  const actions = db
    .prepare(
      `SELECT a.id AS id, a.description AS description, a.completed AS completed,
              a.created_at AS ts
         FROM action_items a JOIN action_items_fts ON a.id = action_items_fts.rowid
        WHERE action_items_fts MATCH ? AND a.deleted = 0
        ORDER BY bm25(action_items_fts) ASC
        LIMIT ?`
    )
    .all(match, limit) as { id: number; description: string; completed: number; ts: number }[]
  const staged = db
    .prepare(
      `SELECT s.id AS id, s.description AS description, s.created_at AS ts
         FROM staged_tasks s JOIN staged_tasks_fts ON s.id = staged_tasks_fts.rowid
        WHERE staged_tasks_fts MATCH ? AND s.completed = 0 AND s.deleted = 0
        ORDER BY bm25(staged_tasks_fts) ASC
        LIMIT ?`
    )
    .all(match, limit) as { id: number; description: string; ts: number }[]

  const hits: CorpusHit[] = [
    ...actions.map((r) => ({
      kind: 'task' as const,
      id: `action:${r.id}`,
      title: r.description,
      detail: r.completed ? 'Done' : '',
      timestamp: r.ts
    })),
    ...staged.map((r) => ({
      kind: 'task' as const,
      id: `staged:${r.id}`,
      title: r.description,
      detail: 'Suggested',
      timestamp: r.ts
    }))
  ]
  hits.sort((a, b) => b.timestamp - a.timestamp)

  const total =
    countMatches(
      db,
      `SELECT COUNT(*) AS n FROM action_items a JOIN action_items_fts ON a.id = action_items_fts.rowid
        WHERE action_items_fts MATCH ? AND a.deleted = 0`,
      match
    ) +
    countMatches(
      db,
      `SELECT COUNT(*) AS n FROM staged_tasks s JOIN staged_tasks_fts ON s.id = staged_tasks_fts.rowid
        WHERE staged_tasks_fts MATCH ? AND s.completed = 0 AND s.deleted = 0`,
      match
    )
  return { hits: hits.slice(0, limit), total }
}

function searchScreenSlice(db: SearchDb, match: string, limit: number): CorpusSlice {
  const rows = db
    .prepare(
      `SELECT f.id AS id, f.window_title AS windowTitle, f.app AS app, f.ts AS ts
         FROM rewind_frames f JOIN rewind_frames_fts ON f.id = rewind_frames_fts.rowid
        WHERE rewind_frames_fts MATCH ?
        ORDER BY bm25(rewind_frames_fts) ASC, f.ts DESC
        LIMIT ?`
    )
    .all(match, limit) as { id: number; windowTitle: string; app: string; ts: number }[]
  return {
    hits: rows.map((r) => ({
      kind: 'screen' as const,
      id: String(r.id),
      // The window title is what a person recognizes a moment by; the app name
      // alone ("Chrome") identifies nothing.
      title: r.windowTitle || r.app || 'Screen',
      detail: r.windowTitle ? r.app : '',
      timestamp: r.ts
    })),
    total: countMatches(
      db,
      `SELECT COUNT(*) AS n FROM rewind_frames_fts WHERE rewind_frames_fts MATCH ?`,
      match
    )
  }
}
