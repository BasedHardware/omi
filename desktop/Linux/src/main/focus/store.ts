import Database from 'better-sqlite3'
import { app } from 'electron'
import { join } from 'path'
import { mkdirSync } from 'fs'
import type { FocusSession } from '../../shared/types'

// Focus session history (StoredFocusSession in FocusStorage.swift).

let db: Database.Database | null = null

function getDb(): Database.Database {
  if (db) return db
  const dir = join(app.getPath('userData'), 'focus')
  mkdirSync(dir, { recursive: true })
  db = new Database(join(dir, 'focus.db'))
  db.pragma('journal_mode = WAL')
  db.exec(`
    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      status TEXT NOT NULL,
      app_or_site TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      message TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_focus_ts ON sessions(ts);
  `)
  return db
}

/** Close the SQLite handle on quit so WAL is checkpointed cleanly. Idempotent. */
export function closeFocusDb(): void {
  if (db) {
    db.close()
    db = null
  }
}

export function addSession(s: {
  ts: number
  status: 'focused' | 'distracted'
  appOrSite: string
  description: string
  message: string | null
}): number {
  return Number(
    getDb()
      .prepare('INSERT INTO sessions(ts, status, app_or_site, description, message) VALUES (?, ?, ?, ?, ?)')
      .run(s.ts, s.status, s.appOrSite, s.description, s.message).lastInsertRowid
  )
}

export function listSessions(limit = 200): FocusSession[] {
  const rows = getDb()
    .prepare('SELECT * FROM sessions ORDER BY ts DESC LIMIT ?')
    .all(limit) as Record<string, unknown>[]
  return mapSessionRows(rows)
}

function listSessionsSince(since: number): FocusSession[] {
  const rows = getDb()
    .prepare('SELECT * FROM sessions WHERE ts >= ? ORDER BY ts DESC')
    .all(since) as Record<string, unknown>[]
  return mapSessionRows(rows)
}

function mapSessionRows(rows: Record<string, unknown>[]): FocusSession[] {
  // durationSeconds = time until the next (newer) session, computed on the fly.
  return rows.map((r, i) => {
    const ts = r.ts as number
    const nextTs = i > 0 ? (rows[i - 1].ts as number) : Date.now()
    return {
      id: r.id as number,
      ts,
      status: r.status as 'focused' | 'distracted',
      appOrSite: r.app_or_site as string,
      description: r.description as string,
      message: (r.message as string) ?? null,
      durationSeconds: Math.max(0, Math.round((nextTs - ts) / 1000))
    }
  })
}

export interface FocusSummary {
  focusedMinutes: number
  distractedMinutes: number
  focusRate: number
  sessions: number
  topDistractions: { app: string; minutes: number }[]
}

export function todaySummary(): FocusSummary {
  const startOfDay = new Date()
  startOfDay.setHours(0, 0, 0, 0)
  const sessions = listSessionsSince(startOfDay.getTime())
  let focusedSec = 0
  let distractedSec = 0
  const byApp = new Map<string, number>()
  for (const s of sessions) {
    if (s.status === 'focused') focusedSec += s.durationSeconds
    else {
      distractedSec += s.durationSeconds
      byApp.set(s.appOrSite, (byApp.get(s.appOrSite) ?? 0) + s.durationSeconds)
    }
  }
  const total = focusedSec + distractedSec
  return {
    focusedMinutes: Math.round(focusedSec / 60),
    distractedMinutes: Math.round(distractedSec / 60),
    focusRate: total > 0 ? Math.round((focusedSec / total) * 100) : 0,
    sessions: sessions.length,
    topDistractions: [...byApp.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([appName, sec]) => ({ app: appName, minutes: Math.max(1, Math.round(sec / 60)) }))
  }
}

export function clearSessions(): void {
  getDb().prepare('DELETE FROM sessions').run()
}
