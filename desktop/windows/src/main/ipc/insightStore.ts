// Proactive Insights — durable insight-history CRUD, kept driver-agnostic (no
// better-sqlite3 / electron import) so it is unit-testable under plain-node
// vitest with node:sqlite — db.ts's native better-sqlite3 dep is built for
// Electron's ABI and can't load there. Same pattern as taskStore.ts /
// voiceTurnOutbox.ts: the DDL lives here (exported as INSIGHTS_SCHEMA and exec'd
// by db.ts's bootstrap) so prod and the CRUD tests run the SAME SQL, and every
// query is an exported `*On(db, …)` function operating on whatever handle is
// passed in.
//
// Backs the Insights history page (Mac parity: InsightPage + InsightStorage).
// `dismissed` is the read/handled marker — Mac's "Mark All Read" maps to
// dismissAll; the schema has no separate unread flag.

import type { InsightPayload, InsightRecord } from '../../shared/types'

// Newest-first cap, matching Mac's InsightStorage history cap (100).
export const INSIGHT_HISTORY_CAP = 100

// Minimal DB surface these functions need — satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests). Bind params
// are positional `?` (no named-param dialect differences between the drivers).
export interface InsightStoreDb {
  exec(sql: string): unknown
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

// DDL for the insights table. Exec'd by db.ts's bootstrap (never here) so the
// schema can't drift from what the tests exercise.
export const INSIGHTS_SCHEMA = `
  CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    headline TEXT NOT NULL,
    advice TEXT NOT NULL,
    reasoning TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    source_app TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    dismissed INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_insights_ts ON insights(ts);
`

// Column list with camelCase aliases so a raw row maps straight onto the record.
const INSIGHT_COLUMNS =
  'id, ts, headline, advice, reasoning, category, source_app AS sourceApp, confidence, dismissed'

// Insert a new insight (most recent), then prune to the newest INSIGHT_HISTORY_CAP
// rows so history never grows unbounded — mirrors Mac's capped InsightStorage.
export function insertInsightOn(db: InsightStoreDb, p: InsightPayload, now = Date.now()): number {
  const info = db
    .prepare(
      `INSERT INTO insights (ts, headline, advice, reasoning, category, source_app, confidence)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .run(now, p.headline, p.advice, p.reasoning, p.category, p.sourceApp, p.confidence) as {
    lastInsertRowid: number | bigint
  }
  // Keep only the newest CAP rows (delete anything older than the CAP-th by ts).
  db.prepare(
    `DELETE FROM insights WHERE id NOT IN (
       SELECT id FROM insights ORDER BY ts DESC, id DESC LIMIT ?
     )`
  ).run(INSIGHT_HISTORY_CAP)
  return Number(info.lastInsertRowid)
}

export function recentInsightsOn(db: InsightStoreDb, limit = 30): InsightRecord[] {
  return db
    .prepare(`SELECT ${INSIGHT_COLUMNS} FROM insights ORDER BY ts DESC, id DESC LIMIT ?`)
    .all(limit) as InsightRecord[]
}

// Mark one insight as dismissed (read/handled). Returns true if a row changed.
export function dismissInsightOn(db: InsightStoreDb, id: number): boolean {
  const info = db.prepare(`UPDATE insights SET dismissed = 1 WHERE id = ?`).run(id) as {
    changes: number | bigint
  }
  return Number(info.changes) > 0
}

// Mark every insight as dismissed (Mac's "Mark All Read"). Returns the row count.
export function dismissAllInsightsOn(db: InsightStoreDb): number {
  const info = db.prepare(`UPDATE insights SET dismissed = 1 WHERE dismissed = 0`).run() as {
    changes: number | bigint
  }
  return Number(info.changes)
}

// Delete all insight history (Mac's "Clear All History"). Returns the row count.
export function clearInsightsOn(db: InsightStoreDb): number {
  const info = db.prepare(`DELETE FROM insights`).run() as { changes: number | bigint }
  return Number(info.changes)
}
