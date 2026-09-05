// Full-text search over the local `memories` table.
//
// Both the schema (MEMORY_SEARCH_SCHEMA) and the query live here so production
// (db.ts) and the tests run byte-identical SQL — a re-declared test copy drifts
// silently, which has happened twice in this program (see the header of
// taskStore.ts). db.ts execs the schema and re-exports a get()-bound wrapper;
// the tests import these same symbols.
//
// Shape follows `rewind_frames_fts` exactly: an external-content FTS5 index
// mirroring the base table's rowid, kept in sync by AFTER INSERT/DELETE/UPDATE
// triggers, so a search is a BM25-ranked index read rather than a LIKE scan over
// every memory ever extracted. Because the index is external-content and
// trigger-maintained, `memories_fts` is deliberately NOT in USER_DATA_TABLES:
// `DELETE FROM memories` on account switch empties it through the delete
// trigger, exactly as rewind_frames_fts / action_items_fts already do.
//
// Indexed columns are the CURATED ones only. `memories.window_title` is
// deliberately excluded: memory/persist.ts:26-31 keeps raw window titles local
// precisely because they are unfiltered PII ("Chase - Log in", "MyChart - Lab
// Results"), and the curated content/context_summary/source_app are what
// represent the memory everywhere else. Indexing the raw title would make that
// PII reachable by typing a fragment of it into a search box.

import { cachedStmt } from '../ipc/stmtCache'

/** Minimal DB surface — satisfied structurally by better-sqlite3 (production)
 *  and node:sqlite's DatabaseSync (tests). Positional `?` params only. */
export interface MemorySearchDb {
  exec(sql: string): void
  prepare(sql: string): {
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
    run: (...params: unknown[]) => unknown
  }
}

export const MEMORY_SEARCH_SCHEMA = `
  CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, context_summary, source_app,
    content='memories', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, context_summary, source_app)
    VALUES (new.id, new.content, new.context_summary, new.source_app);
  END;
  CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, context_summary, source_app)
    VALUES ('delete', old.id, old.content, old.context_summary, old.source_app);
  END;
  CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, context_summary, source_app)
    VALUES ('delete', old.id, old.content, old.context_summary, old.source_app);
    INSERT INTO memories_fts(rowid, content, context_summary, source_app)
    VALUES (new.id, new.content, new.context_summary, new.source_app);
  END;
`

export interface MemorySearchRow {
  id: number
  content: string
  category: string
  sourceApp: string
  contextSummary: string
  createdAt: number
}

/**
 * BM25-ranked memories for an FTS5 MATCH expression. `match` is already-built
 * FTS5 syntax (desktopSearch.ts builds it) — callers must never interpolate raw
 * user text, which would let a stray `"` or `*` throw a syntax error out of
 * SQLite on a keystroke.
 *
 * Ties break on recency, matching searchRewindFrames: two memories that mention
 * the query equally often are most usefully ordered newest-first.
 */
export function searchMemoriesFts(
  db: MemorySearchDb,
  match: string,
  limit = 50
): MemorySearchRow[] {
  if (match.length === 0) return []
  return cachedStmt(
    db,
    `SELECT memories.id AS id,
            memories.content AS content,
            memories.category AS category,
            memories.source_app AS sourceApp,
            memories.context_summary AS contextSummary,
            memories.created_at AS createdAt
       FROM memories
       JOIN memories_fts ON memories.id = memories_fts.rowid
      WHERE memories_fts MATCH ?
      ORDER BY bm25(memories_fts) ASC, memories.created_at DESC
      LIMIT ?`
  ).all(match, limit) as MemorySearchRow[]
}

/** Total memories matching `match`, before any limit. Separate from
 *  searchMemoriesFts so a caller can show how much it is not displaying without
 *  fetching every row to count it. */
export function countMemoriesFts(db: MemorySearchDb, match: string): number {
  if (match.length === 0) return 0
  const row = cachedStmt(
    db,
    `SELECT COUNT(*) AS n FROM memories_fts WHERE memories_fts MATCH ?`
  ).get(match) as { n: number } | undefined
  return row?.n ?? 0
}
