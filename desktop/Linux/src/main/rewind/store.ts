import Database from 'better-sqlite3'
import { app } from 'electron'
import { join } from 'path'
import { mkdirSync, statSync, rmSync } from 'fs'
import type { RewindFrame } from '../../shared/types'

// SQLite layout mirrors RewindStorage.swift: frame metadata + OCR text with FTS5 search.

export function rewindRoot(): string {
  return join(app.getPath('userData'), 'rewind')
}

let db: Database.Database | null = null

function getDb(): Database.Database {
  if (db) return db
  mkdirSync(rewindRoot(), { recursive: true })
  db = new Database(join(rewindRoot(), 'rewind.db'))
  db.pragma('journal_mode = WAL')
  db.exec(`
    CREATE TABLE IF NOT EXISTS frames(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      day TEXT NOT NULL,
      path TEXT NOT NULL,
      bytes INTEGER NOT NULL DEFAULT 0,
      ocr TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_frames_day ON frames(day, ts);
    CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(ocr, content='frames', content_rowid='id');
  `)
  return db
}

/** Close the SQLite handle on quit so WAL is checkpointed cleanly. Idempotent. */
export function closeRewindDb(): void {
  if (db) {
    db.close()
    db = null
  }
}

export function insertFrame(ts: number, day: string, path: string, bytes: number): number {
  const res = getDb()
    .prepare('INSERT INTO frames(ts, day, path, bytes) VALUES (?, ?, ?, ?)')
    .run(ts, day, path, bytes)
  return Number(res.lastInsertRowid)
}

export function setFrameOcr(id: number, text: string): void {
  const d = getDb()
  // Async OCR can resolve after the frame was pruned; the UPDATE then affects 0
  // rows, so only index FTS when the frame still exists (avoids orphan FTS rows).
  const changed = d.prepare('UPDATE frames SET ocr = ? WHERE id = ?').run(text, id).changes
  if (changed > 0) d.prepare('INSERT INTO frames_fts(rowid, ocr) VALUES (?, ?)').run(id, text)
}

export function listFrames(day: string | null, limit: number, offset: number): RewindFrame[] {
  const d = getDb()
  if (day) {
    return d
      .prepare('SELECT id, ts, day, path, ocr FROM frames WHERE day = ? ORDER BY ts ASC LIMIT ? OFFSET ?')
      .all(day, limit, offset) as RewindFrame[]
  }
  return d
    .prepare('SELECT id, ts, day, path, ocr FROM frames ORDER BY ts DESC LIMIT ? OFFSET ?')
    .all(limit, offset) as RewindFrame[]
}

export function listDays(): { day: string; count: number }[] {
  return getDb()
    .prepare('SELECT day, COUNT(*) as count FROM frames GROUP BY day ORDER BY day DESC')
    .all() as { day: string; count: number }[]
}

export function searchFrames(query: string, limit: number): RewindFrame[] {
  const terms = query
    .split(/\s+/)
    .filter(Boolean)
    .map((t) => `"${t.replace(/"/g, '""')}"`)
    .join(' ')
  if (!terms) return []
  return getDb()
    .prepare(
      `SELECT f.id, f.ts, f.day, f.path, f.ocr,
              snippet(frames_fts, 0, '<<', '>>', '…', 12) AS snippet
       FROM frames_fts JOIN frames f ON f.id = frames_fts.rowid
       WHERE frames_fts MATCH ? ORDER BY f.ts DESC LIMIT ?`
    )
    .all(terms, limit) as RewindFrame[]
}

export function getFrame(id: number): RewindFrame | null {
  return (getDb().prepare('SELECT id, ts, day, path, ocr FROM frames WHERE id = ?').get(id) as RewindFrame) ?? null
}

/** Most recent OCR text, used as screen context for chat ("What do you see?" fallback). */
export function latestOcrText(maxAgeMs: number): string | null {
  const row = getDb()
    .prepare('SELECT ocr, ts FROM frames WHERE ocr IS NOT NULL ORDER BY ts DESC LIMIT 1')
    .get() as { ocr: string; ts: number } | undefined
  if (!row || Date.now() - row.ts > maxAgeMs) return null
  return row.ocr
}

/** Deduped OCR text from frames in the last `windowMs`, newest first, proactive context. */
export function recentOcrText(windowMs: number, maxChars = 8000): string | null {
  const cutoff = Date.now() - windowMs
  const rows = getDb()
    .prepare('SELECT ocr FROM frames WHERE ocr IS NOT NULL AND ts >= ? ORDER BY ts DESC LIMIT 40')
    .all(cutoff) as { ocr: string }[]
  if (rows.length === 0) return null
  const seen = new Set<string>()
  const parts: string[] = []
  let total = 0
  for (const r of rows) {
    const text = r.ocr.trim()
    const key = text.slice(0, 120)
    if (!text || seen.has(key)) continue
    seen.add(key)
    parts.push(text)
    total += text.length
    if (total >= maxChars) break
  }
  return parts.length ? parts.join('\n---\n') : null
}

export function stats(): { frames: number; days: number; bytes: number } {
  const row = getDb()
    .prepare('SELECT COUNT(*) AS frames, COUNT(DISTINCT day) AS days, COALESCE(SUM(bytes),0) AS bytes FROM frames')
    .get() as { frames: number; days: number; bytes: number }
  return row
}

export function pruneOlderThan(days: number): number {
  // Floor the retention so a renderer-set 0 or negative value cannot wipe all history.
  const cutoff = Date.now() - Math.max(1, days) * 24 * 3600 * 1000
  const d = getDb()
  const old = d.prepare('SELECT id, path, ocr FROM frames WHERE ts < ?').all(cutoff) as {
    id: number
    path: string
    ocr: string | null
  }[]
  const delFts = d.prepare(`INSERT INTO frames_fts(frames_fts, rowid, ocr) VALUES ('delete', ?, ?)`)
  const delRow = d.prepare('DELETE FROM frames WHERE id = ?')
  const tx = d.transaction(() => {
    for (const f of old) {
      if (f.ocr) delFts.run(f.id, f.ocr)
      delRow.run(f.id)
    }
  })
  tx()
  for (const f of old) {
    try {
      if (statSync(f.path).isFile()) rmSync(f.path)
    } catch {}
  }
  return old.length
}
