// Migration mechanism contract, proven against a REAL SQLite database file
// created with the OLD (pre-outbox) schema — exactly what an existing install's
// omi.db looks like. better-sqlite3 in this repo is rebuilt for Electron's ABI
// (unloadable from plain node), so the fixture db uses node's built-in
// node:sqlite driver; dbMigrations.ts is written against the structural
// MigrationDb interface both drivers satisfy.
import { DatabaseSync } from 'node:sqlite'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { MIGRATIONS, getUserVersion, runMigrations, type Migration, type MigrationDb } from './dbMigrations'

// The local_conversation schema as it shipped BEFORE the sync outbox (verbatim
// from db.ts as of feat/windows-capture — kind/messages/title already present).
const OLD_SCHEMA = `
  CREATE TABLE IF NOT EXISTS local_conversation (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER NOT NULL,
    transcript TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'recording',
    messages TEXT,
    title TEXT
  );
`

const tempFiles: string[] = []

function makeOldDbFile(): { file: string; db: DatabaseSync } {
  const file = path.join(os.tmpdir(), `omi-mig-test-${Date.now()}-${Math.random().toString(36).slice(2)}.db`)
  tempFiles.push(file)
  const db = new DatabaseSync(file)
  db.exec(OLD_SCHEMA)
  db.prepare(
    'INSERT INTO local_conversation (id, started_at, ended_at, transcript, created_at, kind, messages, title) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
  ).run('conv-1', 1000, 2000, 'You: hello', 2000, 'recording', null, 'My recording')
  return { file, db }
}

function columns(db: DatabaseSync, table: string): string[] {
  return (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map((c) => c.name)
}

afterEach(() => {
  for (const f of tempFiles.splice(0)) {
    try {
      fs.rmSync(f)
    } catch {
      /* still open on Windows — temp dir cleans up */
    }
  }
})

describe('runMigrations', () => {
  it('migrates an old-schema database: adds sync columns, preserves rows, bumps user_version', () => {
    const { db } = makeOldDbFile()
    expect(getUserVersion(db as unknown as MigrationDb)).toBe(0)

    const applied = runMigrations(db as unknown as MigrationDb)

    expect(applied).toBe(MIGRATIONS.length)
    expect(getUserVersion(db as unknown as MigrationDb)).toBe(MIGRATIONS.length)
    const cols = columns(db, 'local_conversation')
    for (const c of ['sync_state', 'segments_json', 'cloud_id', 'sync_attempts', 'sync_error']) {
      expect(cols, `column ${c}`).toContain(c)
    }
    // Pre-existing data survives and gets the defaults.
    const row = db
      .prepare('SELECT id, transcript, title, sync_state, sync_attempts, cloud_id FROM local_conversation')
      .get() as Record<string, unknown>
    expect(row.id).toBe('conv-1')
    expect(row.transcript).toBe('You: hello')
    expect(row.title).toBe('My recording')
    expect(row.sync_state).toBe('local_only')
    expect(row.sync_attempts).toBe(0)
    expect(row.cloud_id).toBeNull()
  })

  it('is a no-op on the second run (exactly-once per migration)', () => {
    const { db } = makeOldDbFile()
    const d = db as unknown as MigrationDb
    expect(runMigrations(d)).toBe(MIGRATIONS.length)
    expect(runMigrations(d)).toBe(0)
    expect(getUserVersion(d)).toBe(MIGRATIONS.length)
  })

  it('a failing migration rolls back atomically (user_version and DDL together)', () => {
    const { db } = makeOldDbFile()
    const d = db as unknown as MigrationDb
    const bad: Migration[] = [
      {
        version: 1,
        name: 'adds a column then explodes',
        up: (x) => {
          x.exec('ALTER TABLE local_conversation ADD COLUMN doomed TEXT')
          throw new Error('boom')
        }
      }
    ]
    expect(() => runMigrations(d, bad)).toThrow(/migration 1 .*boom/)
    expect(getUserVersion(d)).toBe(0)
    expect(columns(db, 'local_conversation')).not.toContain('doomed')
  })

  it('rejects a non-contiguous migration list (append-only discipline)', () => {
    const { db } = makeOldDbFile()
    const gappy: Migration[] = [
      { version: 1, name: 'one', up: () => {} },
      { version: 3, name: 'skipped two', up: () => {} }
    ]
    expect(() => runMigrations(db as unknown as MigrationDb, gappy)).toThrow(/contiguous/)
  })

  it('a fresh database (new-schema baseline, user_version 0) migrates cleanly too', () => {
    // A brand-new install runs the CREATE block (old columns only — migrations own
    // the new ones) and then runMigrations; both paths converge on one schema.
    const file = path.join(os.tmpdir(), `omi-mig-fresh-${Date.now()}.db`)
    tempFiles.push(file)
    const db = new DatabaseSync(file)
    db.exec(OLD_SCHEMA)
    expect(runMigrations(db as unknown as MigrationDb)).toBe(MIGRATIONS.length)
    expect(columns(db, 'local_conversation')).toContain('sync_state')
  })
})
