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

function addColumnIfMissing(d: MigrationDb, table: string, col: string, decl: string): void {
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
      addColumnIfMissing(d, 'local_conversation', 'sync_state', "TEXT NOT NULL DEFAULT 'local_only'")
      addColumnIfMissing(d, 'local_conversation', 'segments_json', 'TEXT')
      addColumnIfMissing(d, 'local_conversation', 'cloud_id', 'TEXT')
      addColumnIfMissing(d, 'local_conversation', 'sync_attempts', 'INTEGER NOT NULL DEFAULT 0')
      addColumnIfMissing(d, 'local_conversation', 'sync_error', 'TEXT')
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
      throw new Error(`migrations must be contiguous from 1; found version ${m.version} at index ${i}`)
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
