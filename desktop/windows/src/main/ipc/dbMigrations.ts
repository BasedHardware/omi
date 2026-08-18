/**
 * Minimal versioned-migration mechanism for omi.db.
 *
 * Before this module the schema evolved only via `CREATE TABLE IF NOT EXISTS` +
 * ad-hoc `ensureColumn` calls in db.ts (which stay as the idempotent baseline
 * bootstrap). Anything beyond "add a column if missing" needs ordering and
 * exactly-once semantics, so: `PRAGMA user_version` tracks the last applied
 * migration, MIGRATIONS is an ordered append-only list, and each pending
 * migration runs inside its own transaction (bumping user_version atomically
 * with its DDL, so a crash can't half-apply).
 *
 * Rules for adding a migration:
 *  - Append only; never renumber or edit a shipped migration.
 *  - Keep each `up` idempotent where cheap (guards against a user_version reset).
 *  - No electron imports here — this module is unit-tested against fixture
 *    databases in plain node (see dbMigrations.test.ts, which builds a db with
 *    the OLD schema via node:sqlite and migrates it).
 */

/** The subset of a SQLite driver the migrations need. Satisfied structurally by
 * both better-sqlite3 (production) and node:sqlite's DatabaseSync (tests).
 * (`never[]` rest params keep both drivers' differently-typed statement methods
 * assignable; migrations only ever call them with zero bind params.) */
export type MigrationDb = {
  exec(sql: string): unknown
  prepare(sql: string): {
    all: (...params: never[]) => unknown[]
    get: (...params: never[]) => unknown
  }
}

export type Migration = {
  /** 1-based, strictly increasing, contiguous. */
  version: number
  name: string
  up: (d: MigrationDb) => void
}

function columnExists(d: MigrationDb, table: string, col: string): boolean {
  const cols = d.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]
  return cols.some((c) => c.name === col)
}

/** Add a column only if it doesn't already exist. Exported for db.ts's legacy
 * additive-baseline bootstrap so the idiom isn't duplicated there. */
export function addColumnIfMissing(d: MigrationDb, table: string, col: string, decl: string): void {
  if (!columnExists(d, table, col)) d.exec(`ALTER TABLE ${table} ADD COLUMN ${col} ${decl}`)
}

export function getUserVersion(d: MigrationDb): number {
  const row = d.prepare('PRAGMA user_version').get() as { user_version: number }
  return row.user_version
}

export const MIGRATIONS: Migration[] = [
  {
    version: 1,
    name: 'local_conversation cloud-sync outbox columns',
    up: (d) => {
      // Outbox state machine + retained raw segments for retry/backfill. See
      // ConversationSyncState in shared/types.ts and lib/sync/outbox.ts.
      addColumnIfMissing(
        d,
        'local_conversation',
        'sync_state',
        "TEXT NOT NULL DEFAULT 'local_only'"
      )
      addColumnIfMissing(d, 'local_conversation', 'segments_json', 'TEXT')
      addColumnIfMissing(d, 'local_conversation', 'cloud_id', 'TEXT')
      addColumnIfMissing(d, 'local_conversation', 'sync_attempts', 'INTEGER NOT NULL DEFAULT 0')
      addColumnIfMissing(d, 'local_conversation', 'sync_error', 'TEXT')
    }
  },
  {
    version: 2,
    name: 'rewind_fts_backfill',
    up: (d) => {
      // One-time backfill of the external-content FTS index from existing
      // rewind_frames rows. The rewind_frames_fts table + its sync triggers are
      // created in db.ts's bootstrap block, which runs BEFORE runMigrations, so
      // the table exists here in production. 'rebuild' is the canonical
      // external-content re-sync (clears + repopulates from the content table),
      // so it stays correct even if the index was somehow already populated.
      // Guard on existence: a bare migration-only harness (e.g. dbMigrations.test)
      // seeds only local_conversation, so skip cleanly when the table is absent.
      const hasFts = d
        .prepare("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name='rewind_frames_fts'")
        .get() as { x: number } | undefined
      if (!hasFts) return
      d.exec("INSERT INTO rewind_frames_fts(rewind_frames_fts) VALUES('rebuild')")
    }
  },
  {
    version: 3,
    name: 'rewind_video_chunks',
    up: (d) => {
      // The abandoned-chunk table stands alone, so it is created either way.
      // The database half of abandoned-chunk recovery, ported from macOS'
      // `RewindAbandonedVideoChunkQuarantine`. A chunk found corrupt at read
      // time is tombstoned here so a later claim cannot point a frame back into
      // a file recovery has already given up on.
      d.exec(
        `CREATE TABLE IF NOT EXISTS rewind_abandoned_chunks (
           chunk_path TEXT PRIMARY KEY NOT NULL
         )`
      )
      // Guard on existence, for the same reason migration 2 does: db.ts's
      // bootstrap creates rewind_frames before migrations run in production,
      // but the migration-only harness (dbMigrations.test.ts) seeds only
      // local_conversation, and a migration that assumes a table it did not
      // create fails the whole chain there.
      const hasFrames = d
        .prepare("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name='rewind_frames'")
        .get() as { x: number } | undefined
      if (!hasFrames) return
      // Where a frame lives once it has been compacted into a video chunk:
      // `chunk_path` is the chunk's `<day>/<name>.omichunk` relative path and
      // `chunk_offset` is its position inside it. Both stay NULL for a frame
      // still stored as its own JPEG, which is every existing row — the column
      // being NULL is what `chunkSql.ts` filters compaction candidates on, so
      // the default is the migration's whole behaviour for existing data.
      addColumnIfMissing(d, 'rewind_frames', 'chunk_path', 'TEXT')
      addColumnIfMissing(d, 'rewind_frames', 'chunk_offset', 'INTEGER')
      // Partial index: only chunk-backed rows are in it, so it stays small on a
      // database that has never compacted anything, and the retention sweep's
      // DISTINCT over chunk_path does not scan the whole table.
      d.exec(
        'CREATE INDEX IF NOT EXISTS idx_rewind_frames_chunk ON rewind_frames(chunk_path) WHERE chunk_path IS NOT NULL'
      )
    }
  }
]

/**
 * Apply every migration newer than the db's user_version, in order. Each runs in
 * its own transaction; user_version is bumped inside it. Returns the number of
 * migrations applied.
 */
export function runMigrations(d: MigrationDb, migrations: Migration[] = MIGRATIONS): number {
  const sorted = [...migrations].sort((a, b) => a.version - b.version)
  sorted.forEach((m, i) => {
    if (m.version !== i + 1) {
      throw new Error(
        `migrations must be contiguous from 1; found version ${m.version} at index ${i}`
      )
    }
  })
  let applied = 0
  for (const m of sorted) {
    if (m.version <= getUserVersion(d)) continue
    d.exec('BEGIN')
    try {
      m.up(d)
      d.exec(`PRAGMA user_version = ${m.version}`)
      d.exec('COMMIT')
    } catch (e) {
      d.exec('ROLLBACK')
      throw new Error(`migration ${m.version} (${m.name}) failed: ${(e as Error).message}`)
    }
    applied++
  }
  return applied
}
