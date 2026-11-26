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


describe('legacy local data compatibility', () => {
  it('does not migrate or delete existing JIT and ledger tables', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_SCHEMA)
    runMigrations(db, MIGRATIONS.slice(0, 2))
    const legacy = ['jit_trigger_mirror', 'jit_snapshot_receipt', 'jit_wakeup_receipt',
      'jit_proactivity_reservation_receipt', 'jit_ambient_context_state', 'jit_feedback_outbox',
      'jit_installation_identity', 'jit_fact_mirror', 'jit_history_mirror', 'jit_playbook_mirror',
      'jit_alias_mirror', 'jit_ledger_mirror_receipt', 'jit_keyframe_pin',
      'jit_keyframe_cleanup_outbox', 'rewind_frames', 'focus_session', 'insight_history']
    for (const table of legacy) {
      db.exec(`CREATE TABLE ${table} (id TEXT PRIMARY KEY); INSERT INTO ${table} VALUES ('sentinel')`)
    }
    // Every later migration (v3+) runs over the sentinels and must leave them be.
    expect(runMigrations(db)).toBe(MIGRATIONS.length - 2)
    expect(runMigrations(db)).toBe(0)
    for (const table of legacy) {
      expect(db.prepare(`SELECT id FROM ${table}`).get()).toEqual({ id: 'sentinel' })
    }
    expect(db.prepare('PRAGMA foreign_key_check').all()).toEqual([])
    db.close()
  })
})

describe('migration v3 (reserved no-op)', () => {
  const tableExists = (db: DatabaseSync, name: string): boolean =>
    Boolean(db.prepare("SELECT 1 AS x FROM sqlite_master WHERE name = ?").get(name))

  it('keeps the old local AI-profile table: the profile service uploads, then drops it', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_SCHEMA)
    runMigrations(db as unknown as MigrationDb, MIGRATIONS.slice(0, 2))
    // The table + index exactly as db.ts's Track 3 block used to create them.
    db.exec(`
      CREATE TABLE ai_user_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_text TEXT NOT NULL,
        data_sources_used TEXT,
        generated_at INTEGER NOT NULL,
        backend_synced INTEGER NOT NULL DEFAULT 0
      );
      CREATE INDEX idx_ai_user_profiles_generated_at ON ai_user_profiles(generated_at);
      INSERT INTO ai_user_profiles (profile_text, generated_at) VALUES ('unsynced edit', 1);
    `)
    expect(runMigrations(db as unknown as MigrationDb)).toBe(MIGRATIONS.length - 2)
    expect(tableExists(db, 'ai_user_profiles')).toBe(true)
    expect(db.prepare('SELECT profile_text AS t FROM ai_user_profiles').get()).toEqual({
      t: 'unsynced edit'
    })
    expect(getUserVersion(db as unknown as MigrationDb)).toBeGreaterThanOrEqual(3)
    db.close()
  })

  it('a database that already ran the unreleased dropping v3 migrates on cleanly', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_SCHEMA)
    runMigrations(db as unknown as MigrationDb, MIGRATIONS.slice(0, 2))
    db.exec('PRAGMA user_version = 3')
    expect(runMigrations(db as unknown as MigrationDb)).toBe(MIGRATIONS.length - 3)
    expect(getUserVersion(db as unknown as MigrationDb)).toBe(MIGRATIONS.length)
    db.close()
  })

  it('is a no-op on an install that never had the table', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_SCHEMA)
    expect(runMigrations(db as unknown as MigrationDb)).toBe(MIGRATIONS.length)
    expect(tableExists(db, 'ai_user_profiles')).toBe(false)
    db.close()
  })
})
