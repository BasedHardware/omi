import Database from 'better-sqlite3'
import { app } from 'electron'
import { join } from 'path'
import { mkdirSync } from 'fs'
import type { Insight } from '../../shared/types'

// Local store for proactive insights (the Mac app keeps these in GRDB
// `observations`). Memories and tasks the engine extracts go to the backend
// (/v3/memories, /v1/action-items); only the advisory insights live here.

let db: Database.Database | null = null

function getDb(): Database.Database {
  if (db) return db
  const dir = join(app.getPath('userData'), 'proactive')
  mkdirSync(dir, { recursive: true })
  db = new Database(join(dir, 'proactive.db'))
  db.pragma('journal_mode = WAL')
  db.exec(`
    CREATE TABLE IF NOT EXISTS insights(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'insight',
      source_app TEXT,
      read INTEGER NOT NULL DEFAULT 0,
      fingerprint TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_insights_ts ON insights(ts);
  `)
  return db
}

/** Close the SQLite handle on quit so WAL is checkpointed cleanly. Idempotent. */
export function closeProactiveDb(): void {
  if (db) {
    db.close()
    db = null
  }
}

function rowToInsight(r: Record<string, unknown>): Insight {
  return {
    id: r.id as number,
    ts: r.ts as number,
    title: r.title as string,
    body: r.body as string,
    category: r.category as string,
    sourceApp: (r.source_app as string) ?? null,
    read: r.read as number
  }
}

/** Insert an insight unless a same-fingerprint one was stored in the last 6h (dedup). */
export function addInsight(i: {
  ts: number
  title: string
  body: string
  category: string
  sourceApp?: string | null
  fingerprint: string
}): Insight | null {
  const d = getDb()
  const recent = d
    .prepare('SELECT id FROM insights WHERE fingerprint = ? AND ts >= ? LIMIT 1')
    .get(i.fingerprint, i.ts - 6 * 3600 * 1000)
  if (recent) return null
  const res = d
    .prepare(
      'INSERT INTO insights(ts, title, body, category, source_app, fingerprint) VALUES (?, ?, ?, ?, ?, ?)'
    )
    .run(i.ts, i.title, i.body, i.category, i.sourceApp ?? null, i.fingerprint)
  return rowToInsight({ ...i, id: Number(res.lastInsertRowid), source_app: i.sourceApp ?? null, read: 0 })
}

export function listInsights(limit = 100): Insight[] {
  return (getDb().prepare('SELECT * FROM insights ORDER BY ts DESC LIMIT ?').all(limit) as Record<string, unknown>[]).map(
    rowToInsight
  )
}

export function unreadCount(): number {
  return (getDb().prepare('SELECT COUNT(*) AS c FROM insights WHERE read = 0').get() as { c: number }).c
}

export function markRead(id: number): void {
  getDb().prepare('UPDATE insights SET read = 1 WHERE id = ?').run(id)
}

export function markAllRead(): void {
  getDb().prepare('UPDATE insights SET read = 1 WHERE read = 0').run()
}

export function deleteInsight(id: number): void {
  getDb().prepare('DELETE FROM insights WHERE id = ?').run(id)
}
