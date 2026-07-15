// Sign-out teardown (SQLite half): wipeUserDataOn must clear EVERY user-scoped
// table so a second account on the same machine can't see the prior user's data.
// Proven against a real SQLite DB via node:sqlite (better-sqlite3 is built for
// Electron's ABI and won't load under plain-node vitest — same reason
// dbMigrations.test.ts uses node:sqlite).
import { readFileSync } from 'node:fs'
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { USER_DATA_TABLES, wipeUserDataOn } from './dbWipe'

// Minimal one-column stand-ins for each user table — enough to insert + count.
function makeSeededDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  for (const table of USER_DATA_TABLES) {
    db.exec(`CREATE TABLE ${table} (v INTEGER)`)
    db.prepare(`INSERT INTO ${table} (v) VALUES (1)`).run()
  }
  return db
}

function count(db: DatabaseSync, table: string): number {
  return (db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n
}

describe('wipeUserDataOn (sign-out teardown)', () => {
  it('clears every user-scoped table', () => {
    const db = makeSeededDb()
    for (const t of USER_DATA_TABLES) expect(count(db, t)).toBe(1)

    wipeUserDataOn(db)

    for (const t of USER_DATA_TABLES) expect(count(db, t)).toBe(0)
  })

  it('rolls back and leaves data intact if a delete fails mid-wipe', () => {
    const db = makeSeededDb()
    // Drop one table so its DELETE throws partway through the transaction.
    db.exec('DROP TABLE insights')

    expect(() => wipeUserDataOn(db)).toThrow()

    // The tables deleted before the failure must be restored by the ROLLBACK —
    // an all-or-nothing wipe, never a partial one.
    for (const t of USER_DATA_TABLES) {
      if (t === 'insights') continue
      expect(count(db, t)).toBe(1)
    }
  })
})

// Drift guard: every table in the REAL schema must be wiped on sign-out (or be
// explicitly exempted below). Fails the moment ANY track adds a table to db.ts
// (or a migration) without adding it to USER_DATA_TABLES — the exact gap that
// would leak one account's data to the next account on the same machine.

// Tables that are legitimately NOT user-data belong here, each with a reason.
const WIPE_EXEMPT = new Set<string>([
  // app_meta holds app-level flags (clean-exit, launch-at-login migrated) that must
  // survive an account switch — not user content. Owned by Track 4 (see dbWipe.ts).
  'app_meta'
])

// Pull table names straight from source so the guard tracks db.ts / dbMigrations.ts
// without importing them (both load better-sqlite3/electron, which won't run under
// plain-node vitest). The `\s*\(` after the name keeps prose comments that merely
// mention "CREATE TABLE" from matching — only real DDL is followed by a column list.
function tablesDeclaredInSource(): string[] {
  // liveNotesStore.ts holds the PR8 LiveNotes DDL (transcription_sessions +
  // live_notes) that db.ts execs via LIVE_NOTES_SCHEMA — scan it too so those
  // tables are still required in USER_DATA_TABLES by the drift guard. taskStore.ts
  // holds the Track 3 task DDL (action_items + staged_tasks) execed via
  // TASK_TABLES_SCHEMA — same reason.
  const src = ['./db.ts', './dbMigrations.ts', './liveNotesStore.ts', './taskStore.ts']
    .map((f) => readFileSync(new URL(f, import.meta.url), 'utf8'))
    .join('\n')
  const names = new Set<string>()
  const re = /CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\(/gi
  let m: RegExpExecArray | null
  while ((m = re.exec(src)) !== null) names.add(m[1])
  return [...names]
}

// Materialize the real schema in a real SQLite db, then read it back via
// sqlite_master (excluding sqlite_* internals and, implicitly, indexes) — the
// same node:sqlite path the suites above use.
function realSchemaTables(): string[] {
  const db = new DatabaseSync(':memory:')
  for (const t of tablesDeclaredInSource()) db.exec(`CREATE TABLE ${t} (v INTEGER)`)
  return (
    db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
      .all() as { name: string }[]
  ).map((r) => r.name)
}

describe('USER_DATA_TABLES covers the whole schema (sign-out leak guard)', () => {
  const wiped = new Set<string>(USER_DATA_TABLES)

  it('finds the known core tables (extractor sanity — never passes vacuously)', () => {
    const tables = realSchemaTables()
    for (const t of [
      'local_conversation',
      'ai_user_profiles',
      'focus_sessions',
      'task_embeddings',
      'action_items',
      'staged_tasks'
    ]) {
      expect(tables, `schema should contain ${t}`).toContain(t)
    }
  })

  it('wipes (or explicitly exempts) every table in the real schema', () => {
    const unwiped = realSchemaTables().filter((t) => !wiped.has(t) && !WIPE_EXEMPT.has(t))
    expect(unwiped, `tables missing from USER_DATA_TABLES: ${unwiped.join(', ')}`).toEqual([])
  })
})
