// Track 4 additive-schema contract, proven against a REAL SQLite database via
// node:sqlite. db.ts's better-sqlite3 is rebuilt for Electron's ABI and can't
// load under plain-node vitest (same constraint as dbMigrations.test.ts /
// dbWipe.test.ts), so the Track 4 DDL below is replicated verbatim from db.ts's
// bootstrap block, and the REAL column/migration helpers (addColumnIfMissing,
// runMigrations, MIGRATIONS) are imported and exercised. This asserts:
//   - every new table exists,
//   - the new additive columns exist,
//   - inserting/deleting a rewind_frames row propagates to rewind_frames_fts
//     (the sync triggers), and MATCH finds it,
//   - the dbMigrations v2 backfill populates the FTS from pre-existing rows,
//   - PRAGMA user_version reaches the current MIGRATIONS length (>= 2).
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import {
  addColumnIfMissing,
  getUserVersion,
  runMigrations,
  MIGRATIONS,
  type MigrationDb
} from './dbMigrations'
// PR8 LiveNotes DDL is imported (not re-declared) so this census can't drift from
// what db.ts actually execs — see liveNotesStore.ts.
import { LIVE_NOTES_SCHEMA } from './liveNotesStore'

// Base tables an existing install already has, verbatim from db.ts (the columns
// the FTS triggers read from rewind_frames, and the local_conversation baseline).
const BASE_SCHEMA = `
  CREATE TABLE IF NOT EXISTS rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    process_name TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
  );
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

// The Track 4 DDL block, verbatim from db.ts get(). Kept in sync manually (same
// replication discipline as dbMigrations.test.ts's OLD_SCHEMA).
const TRACK4_SCHEMA = `
  CREATE VIRTUAL TABLE IF NOT EXISTS rewind_frames_fts USING fts5(
    ocr_text, window_title, app,
    content='rewind_frames', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER IF NOT EXISTS rewind_frames_ai AFTER INSERT ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
    VALUES (new.id, new.ocr_text, new.window_title, new.app);
  END;
  CREATE TRIGGER IF NOT EXISTS rewind_frames_ad AFTER DELETE ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
  END;
  CREATE TRIGGER IF NOT EXISTS rewind_frames_au AFTER UPDATE ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
    INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
    VALUES (new.id, new.ocr_text, new.window_title, new.app);
  END;
  CREATE TABLE IF NOT EXISTS rewind_embeddings (
    frame_id INTEGER PRIMARY KEY,
    hash TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_rewind_embeddings_hash ON rewind_embeddings(hash);
  CREATE TABLE IF NOT EXISTS rewind_embedding_vectors (
    hash TEXT PRIMARY KEY,
    dim INTEGER,
    model TEXT,
    vec BLOB,
    created_at INTEGER
  );
  CREATE TABLE IF NOT EXISTS conversation_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT,
    icon TEXT,
    order_idx INTEGER NOT NULL DEFAULT 0,
    is_system INTEGER NOT NULL DEFAULT 0,
    conversation_count INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
  );
  CREATE TABLE IF NOT EXISTS conversation_speaker_names (
    conversation_id TEXT NOT NULL,
    speaker_id INTEGER NOT NULL,
    name TEXT,
    person_id TEXT,
    is_user INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conversation_id, speaker_id)
  );
  CREATE TABLE IF NOT EXISTS rescue_segments (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    segment_json TEXT NOT NULL,
    ts INTEGER NOT NULL,
    PRIMARY KEY (session_id, seq)
  );
  CREATE TABLE IF NOT EXISTS file_index_meta (
    key TEXT PRIMARY KEY,
    value TEXT
  );
  CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT
  );
`

const NEW_TABLES = [
  'rewind_frames_fts',
  'rewind_embeddings',
  'rewind_embedding_vectors',
  'conversation_folders',
  'conversation_speaker_names',
  'transcription_sessions',
  'live_notes',
  'rescue_segments',
  'file_index_meta',
  'app_meta'
]

function tableExists(db: DatabaseSync, name: string): boolean {
  return !!db.prepare('SELECT 1 FROM sqlite_master WHERE name = ?').get(name)
}

function columns(db: DatabaseSync, table: string): string[] {
  return (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map((c) => c.name)
}

function insertFrame(
  db: DatabaseSync,
  ts: number,
  app: string,
  title: string,
  ocr: string
): number {
  const r = db
    .prepare(
      'INSERT INTO rewind_frames (ts, app, window_title, process_name, ocr_text, image_path) VALUES (?, ?, ?, ?, ?, ?)'
    )
    .run(ts, app, title, '', ocr, `/tmp/${ts}.jpg`)
  return Number(r.lastInsertRowid)
}

function ftsMatchRowids(db: DatabaseSync, query: string): number[] {
  return (
    db
      .prepare('SELECT rowid FROM rewind_frames_fts WHERE rewind_frames_fts MATCH ?')
      .all(query) as {
      rowid: number
    }[]
  ).map((r) => Number(r.rowid))
}

// Build a DB that mirrors an existing install: base tables + one pre-existing
// rewind_frames row, THEN the Track 4 bootstrap (FTS/triggers/tables), THEN the
// additive columns, THEN the real versioned migrations (v2 backfills the FTS).
function makeMigratedDb(): { db: DatabaseSync; preexistingRowId: number } {
  const db = new DatabaseSync(':memory:')
  db.exec(BASE_SCHEMA)
  // A row that existed BEFORE the FTS index — only migration v2's backfill can
  // make it searchable (the AFTER-INSERT trigger doesn't fire retroactively).
  const preexistingRowId = insertFrame(db, 1000, 'Chrome', 'Docs', 'pelican reservoir schematic')
  db.exec(TRACK4_SCHEMA)
  db.exec(LIVE_NOTES_SCHEMA)
  addColumnIfMissing(db as unknown as MigrationDb, 'rewind_frames', 'ocr_lines_json', 'TEXT')
  addColumnIfMissing(
    db as unknown as MigrationDb,
    'local_conversation',
    'starred',
    'INTEGER NOT NULL DEFAULT 0'
  )
  addColumnIfMissing(db as unknown as MigrationDb, 'local_conversation', 'folder_id', 'TEXT')
  runMigrations(db as unknown as MigrationDb)
  return { db, preexistingRowId }
}

describe('Track 4 additive schema', () => {
  it('creates every new table', () => {
    const { db } = makeMigratedDb()
    for (const t of NEW_TABLES) expect(tableExists(db, t), `table ${t}`).toBe(true)
  })

  it('adds the new additive columns to existing tables', () => {
    const { db } = makeMigratedDb()
    expect(columns(db, 'rewind_frames')).toContain('ocr_lines_json')
    const conv = columns(db, 'local_conversation')
    expect(conv).toContain('starred')
    expect(conv).toContain('folder_id')
  })

  it('reaches the current migration version (>= 2)', () => {
    const { db } = makeMigratedDb()
    expect(getUserVersion(db as unknown as MigrationDb)).toBe(MIGRATIONS.length)
    expect(MIGRATIONS.length).toBeGreaterThanOrEqual(2)
  })

  it('backfills the FTS index from pre-existing rows (migration v2)', () => {
    const { db, preexistingRowId } = makeMigratedDb()
    expect(ftsMatchRowids(db, 'reservoir')).toContain(preexistingRowId)
    // Matches across the other indexed columns too (window_title, app).
    expect(ftsMatchRowids(db, 'Docs')).toContain(preexistingRowId)
  })

  it('propagates new inserts into the FTS via the AFTER INSERT trigger', () => {
    const { db } = makeMigratedDb()
    const id = insertFrame(db, 2000, 'Slack', 'general', 'quarterly axolotl roadmap')
    expect(ftsMatchRowids(db, 'axolotl')).toEqual([id])
  })

  it('removes rows from the FTS via the AFTER DELETE trigger (wipe consistency)', () => {
    const { db } = makeMigratedDb()
    const id = insertFrame(db, 3000, 'Notes', 'scratch', 'ephemeral narwhal note')
    expect(ftsMatchRowids(db, 'narwhal')).toEqual([id])
    db.prepare('DELETE FROM rewind_frames WHERE id = ?').run(id)
    expect(ftsMatchRowids(db, 'narwhal')).toEqual([])
  })

  it('reflects updates in the FTS via the AFTER UPDATE trigger', () => {
    const { db } = makeMigratedDb()
    const id = insertFrame(db, 4000, 'Editor', 'main.ts', 'before token')
    expect(ftsMatchRowids(db, 'before')).toEqual([id])
    db.prepare('UPDATE rewind_frames SET ocr_text = ? WHERE id = ?').run('after token', id)
    expect(ftsMatchRowids(db, 'before')).toEqual([])
    expect(ftsMatchRowids(db, 'after')).toEqual([id])
  })
})
