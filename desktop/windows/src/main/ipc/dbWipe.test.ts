// Sign-out teardown (SQLite half): wipeUserDataOn must clear EVERY user-scoped
// table so a second account on the same machine can't see the prior user's data.
// The one exception is the owner's rewind index, which sign-out PARKS (under
// their uid, restored on their return) rather than deletes -- tested below.
// Proven against a real SQLite DB via node:sqlite (better-sqlite3 is built for
// Electron's ABI and won't load under plain-node vitest — same reason
// dbMigrations.test.ts uses node:sqlite).
import { readFileSync } from 'node:fs'
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import {
  REWIND_IMAGE_PATHS_SQL,
  USER_DATA_TABLES,
  pruneParkedRewindFramesOn,
  restoreRewindFramesOn,
  wipeUserDataOn
} from './dbWipe'

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

  it('wipes legacy user data when an additive JIT bootstrap left mirror tables absent', () => {
    const db = makeSeededDb()
    const optionalJitTables = USER_DATA_TABLES.filter((table) => table.startsWith('jit_'))
    for (const table of optionalJitTables) db.exec(`DROP TABLE ${table}`)

    wipeUserDataOn(db)

    for (const table of USER_DATA_TABLES) {
      if (optionalJitTables.includes(table)) continue
      expect(count(db, table)).toBe(0)
    }
  })

  it('does not clear install-scoped JIT cleanup authority during account wipe', () => {
    const db = makeSeededDb()
    db.exec('CREATE TABLE jit_keyframe_pin (v INTEGER)')
    db.exec('CREATE TABLE jit_keyframe_cleanup_outbox (v INTEGER)')
    db.prepare('INSERT INTO jit_keyframe_pin (v) VALUES (1)').run()
    db.prepare('INSERT INTO jit_keyframe_cleanup_outbox (v) VALUES (1)').run()

    wipeUserDataOn(db)

    // The caller drains these rows' physical image paths first. A failed unlink
    // must leave both records available to the launch retry worker.
    expect(count(db, 'jit_keyframe_pin')).toBe(1)
    expect(count(db, 'jit_keyframe_cleanup_outbox')).toBe(1)
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
  'app_meta',
  // JIT pins and their cleanup outbox are install-scoped unlink authority. The
  // account wipe queues/drains their physical image files first and retains
  // failed rows for a later retry; deleting these tables here would strand a
  // file or clear the only retry record.
  'jit_keyframe_pin',
  'jit_keyframe_cleanup_outbox',
  // Parked rewind frames are the outgoing account's screen history, deliberately
  // preserved across owner transitions (INV-AUTH-1: sign-out retargets the
  // rewind store for the next owner, it never destroys the prior owner's).
  // Wiping this table would re-create the silent-history-loss bug it exists to
  // prevent -- a sign-out would erase the account's entire local rewind, and
  // its unreferenced JPEGs would then be mass-deleted by the orphan sweep.
  'rewind_frames_parked',
  // The live rewind index is likewise owner-preserved: sign-out moves its rows
  // into rewind_frames_parked under the outgoing uid (still hidden from any
  // other account), and only a uid-less wipe falls back to deleting it.
  'rewind_frames'
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

// --- Sign-out must preserve the rewind index for its owner (INV-AUTH-1) -----
// Regression for the reported incident: signing out ran `DELETE FROM
// rewind_frames`, which destroyed the account's entire local screen history and
// left its JPEGs unreferenced, so the orphan sweep then unlinked them within
// minutes. Sign-out now PARKS the rows under the outgoing uid (rewind_frames is
// no longer in USER_DATA_TABLES) and a returning owner's rows are restored.
// These tables are full-shape (not the one-column stand-ins above) so the
// real INSERT..SELECT column lists are exercised.

const REWIND_FRAME_COLUMNS = `(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,
  app TEXT NOT NULL DEFAULT '', window_title TEXT NOT NULL DEFAULT '',
  process_name TEXT NOT NULL DEFAULT '', ocr_text TEXT NOT NULL DEFAULT '',
  ocr_lines_json TEXT,
  image_path TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0,
  height INTEGER NOT NULL DEFAULT 0, indexed INTEGER NOT NULL DEFAULT 0)`

const PARKED_FRAME_COLUMNS = `(owner_uid TEXT NOT NULL, ts INTEGER NOT NULL,
  app TEXT NOT NULL DEFAULT '', window_title TEXT NOT NULL DEFAULT '',
  process_name TEXT NOT NULL DEFAULT '', ocr_text TEXT NOT NULL DEFAULT '',
  ocr_lines_json TEXT,
  image_path TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0,
  height INTEGER NOT NULL DEFAULT 0, indexed INTEGER NOT NULL DEFAULT 0)`

function makeRewindDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  for (const table of USER_DATA_TABLES) {
    db.exec(`CREATE TABLE ${table} (v INTEGER)`)
    db.prepare(`INSERT INTO ${table} (v) VALUES (1)`).run()
  }
  // The two tables under test get their real column shape.
  db.exec(`DROP TABLE rewind_embeddings`)
  db.exec('CREATE TABLE rewind_embeddings (frame_id INTEGER, hash TEXT)')
  db.prepare('INSERT INTO rewind_embeddings (frame_id, hash) VALUES (1, ?)').run('seed')
  db.exec(`CREATE TABLE rewind_frames ${REWIND_FRAME_COLUMNS}`)
  db.exec(`CREATE TABLE rewind_frames_parked ${PARKED_FRAME_COLUMNS}`)
  // Production's unique (owner_uid, image_path) index (db.ts), so the park's
  // INSERT OR IGNORE is exercised against the same schema that ships -- without
  // it a duplicate-path park would insert a second row here and the prod
  // behavior (silently keep the first) would go untested.
  db.exec(
    'CREATE UNIQUE INDEX idx_rewind_frames_parked_owner_path ON rewind_frames_parked (owner_uid, image_path)'
  )
  return db
}

function insertFrame(
  db: DatabaseSync,
  ts: number,
  imagePath: string,
  ocrText: string,
  ocrLinesJson?: string
): void {
  db.prepare(
    `INSERT INTO rewind_frames (ts, app, window_title, process_name, ocr_text, ocr_lines_json, image_path, width, height, indexed)
     VALUES (?, 'App', 'Title', 'app.exe', ?, ?, ?, 100, 60, 1)`
  ).run(ts, ocrText, ocrLinesJson ?? null, imagePath)
}

function countRewind(db: DatabaseSync, table: string): number {
  return (db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n
}

describe('sign-out parks the rewind index for its owner (INV-AUTH-1 regression)', () => {
  it("parks the outgoing owner's frames instead of deleting them, and still wipes derived embeddings", () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'meeting notes')
    insertFrame(db, 2_000, '/rewind/2026-10-01/2000.jpg', 'code review')
    db.prepare('INSERT INTO rewind_embeddings (frame_id, hash) VALUES (1, ?)').run('hashA')
    db.prepare('INSERT INTO rewind_embedding_vectors (v) VALUES (1)').run()

    wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })

    // The violating pre-fix behavior was live rows = 0 with parked = 0: history
    // destroyed at the owner boundary.
    expect(countRewind(db, 'rewind_frames')).toBe(0)
    expect(countRewind(db, 'rewind_frames_parked')).toBe(2)
    const parked = db
      .prepare(`SELECT owner_uid, ts, ocr_text, image_path FROM rewind_frames_parked ORDER BY ts`)
      .all() as Array<{ owner_uid: string; ts: number; ocr_text: string; image_path: string }>
    expect(parked).toEqual([
      {
        owner_uid: 'uidA',
        ts: 1_000,
        ocr_text: 'meeting notes',
        image_path: '/rewind/2026-10-01/1000.jpg'
      },
      {
        owner_uid: 'uidA',
        ts: 2_000,
        ocr_text: 'code review',
        image_path: '/rewind/2026-10-01/2000.jpg'
      }
    ])
    // Derived embeddings stay a plain wipe (recomputable from restored rows).
    expect(countRewind(db, 'rewind_embeddings')).toBe(0)
    expect(countRewind(db, 'rewind_embedding_vectors')).toBe(0)
  })

  it('INSERT OR IGNORE keeps the existing parked row when the same image path is parked twice', () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 're-captured')
    // The parked slot already holds (uidA, same image_path) -- e.g. an earlier
    // park whose restore was interrupted. Production's UNIQUE (owner_uid,
    // image_path) index makes the park's INSERT OR IGNORE skip the duplicate
    // instead of throwing mid-wipe; this fixture carries that index, so this
    // test fails if the park ever stops being OR IGNORE.
    db.prepare(
      `INSERT INTO rewind_frames_parked (owner_uid, ts, image_path) VALUES ('uidA', 500, '/rewind/2026-10-01/1000.jpg')`
    ).run()

    expect(() => wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })).not.toThrow()

    expect(countRewind(db, 'rewind_frames')).toBe(0)
    expect(countRewind(db, 'rewind_frames_parked')).toBe(1)
    const parked = db.prepare('SELECT ts, image_path FROM rewind_frames_parked').get() as {
      ts: number
      image_path: string
    }
    expect(parked).toEqual({ ts: 500, image_path: '/rewind/2026-10-01/1000.jpg' })
  })

  it("restores a returning owner's parked rows into the live index", () => {
    const db = makeRewindDb()
    const linesJson = JSON.stringify([{ x: 1, y: 2, w: 3, h: 4, text: 'meeting' }])
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'meeting notes', linesJson)
    wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })
    expect(countRewind(db, 'rewind_frames')).toBe(0)

    expect(restoreRewindFramesOn(db, 'uidA')).toBe(1)

    expect(countRewind(db, 'rewind_frames')).toBe(1)
    expect(countRewind(db, 'rewind_frames_parked')).toBe(0)
    const row = db
      .prepare('SELECT ts, ocr_text, ocr_lines_json, image_path, indexed FROM rewind_frames')
      .get() as {
      ts: number
      ocr_text: string
      ocr_lines_json: string | null
      image_path: string
      indexed: number
    }
    // OCR text, per-line boxes, and metadata survive the round-trip (not a
    // lossy disk rebuild): the search-highlight overlay renders from
    // ocr_lines_json, so dropping it across a sign-out would degrade playback.
    expect(row).toEqual({
      ts: 1_000,
      ocr_text: 'meeting notes',
      ocr_lines_json: linesJson,
      image_path: '/rewind/2026-10-01/1000.jpg',
      indexed: 1
    })
  })

  it("never restores another owner's parked rows", () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'private')
    wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })

    expect(restoreRewindFramesOn(db, 'uidB')).toBe(0)

    // uidB must not see uidA's screen history; uidA's park is untouched.
    expect(countRewind(db, 'rewind_frames')).toBe(0)
    expect(countRewind(db, 'rewind_frames_parked')).toBe(1)
    expect(restoreRewindFramesOn(db, 'uidA')).toBe(1)
    expect(
      (db.prepare('SELECT ocr_text FROM rewind_frames').get() as { ocr_text: string }).ocr_text
    ).toBe('private')
  })

  it('restores nothing and does not throw when nothing is parked (every-sign-in safety)', () => {
    const db = makeRewindDb()
    expect(restoreRewindFramesOn(db, 'uidA')).toBe(0)
    expect(countRewind(db, 'rewind_frames')).toBe(0)
  })

  it('falls back to deleting rewind frames when no owner uid is supplied (fail-closed privacy)', () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'private')

    wipeUserDataOn(db)

    // Without an owner to park for, the rows must not survive into another
    // account's session -- the destructive wipe is the safer failure.
    expect(countRewind(db, 'rewind_frames')).toBe(0)
    expect(countRewind(db, 'rewind_frames_parked')).toBe(0)
  })

  it('deletes rewind frames when the parked table is absent despite an owner uid (documented fail-closed fallback)', () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'private')
    // A schema so old it predates rewind_frames_parked (unreachable in the
    // shipped app, which creates it at every db open before any wipe IPC).
    db.exec('DROP TABLE rewind_frames_parked')

    wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })

    // The fallback must match its comment: fail CLOSED toward privacy. Leaving
    // the rows live would hand the prior owner's screen history to the next
    // account on this machine.
    expect(countRewind(db, 'rewind_frames')).toBe(0)
  })

  it('rolls back the whole teardown if the park fails mid-transaction', () => {
    const db = makeRewindDb()
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'meeting notes')
    // Sabotage the park so it throws AFTER the user-table DELETEs: with
    // rewind_frames renamed away, the park's INSERT..SELECT has no source table.
    db.exec('ALTER TABLE rewind_frames RENAME TO rewind_frames_moved')

    expect(() => wipeUserDataOn(db, { rewindOwnerUid: 'uidA' })).toThrow()

    // All-or-nothing: the user tables wiped before the failure are restored.
    for (const t of USER_DATA_TABLES) expect(count(db, t)).toBe(1)
  })

  it('keep-set covers live AND parked rows (the identical statement db.ts runs)', () => {
    const db = makeRewindDb()
    // Live row + parked row for the same owner: after a sign-out both files must
    // stay in the sweep's keep-set or the sweep deletes the parked JPEGs.
    insertFrame(db, 1_000, '/rewind/2026-10-01/1000.jpg', 'live')
    db.prepare(
      `INSERT INTO rewind_frames_parked (owner_uid, ts, image_path) VALUES ('uidA', 2_000, '/rewind/2026-10-01/2000.jpg')`
    ).run()

    const paths = (
      db.prepare(REWIND_IMAGE_PATHS_SQL).all(0, 5_000, 0, 5_000) as { image_path: string }[]
    ).map((r) => r.image_path)

    expect(paths).toContain('/rewind/2026-10-01/1000.jpg')
    expect(paths).toContain('/rewind/2026-10-01/2000.jpg')
  })
})

// --- Parked rows age out through the same retention cutoff as live frames ---
// Regression for the review gap: the keep-set above makes every parked JPEG
// look referenced, so if parked rows were never pruned, a parked owner who
// never signs back in would keep their rows (and their files) forever. The
// prune runs per-frame age, regardless of owner presence, and retires rows
// BEFORE their files so a failed unlink leaves a no-row file past the cutoff,
// which the orphan sweep already treats as deletable-on-sight.
describe('parked rewind retention (pruneParkedRewindFramesOn)', () => {
  const insertParked = (db: DatabaseSync, uid: string, ts: number, imagePath: string): void => {
    db.prepare('INSERT INTO rewind_frames_parked (owner_uid, ts, image_path) VALUES (?, ?, ?)').run(
      uid,
      ts,
      imagePath
    )
  }

  it('prunes parked rows past the cutoff and returns them for file unlink, including owners who never sign back in', () => {
    const db = makeRewindDb()
    insertParked(db, 'uidGone', 1_000, '/rewind/2026-10-01/1000.jpg') // ancient; owner never returns
    insertParked(db, 'uidA', 6_000, '/rewind/2026-10-01/6000.jpg') // still inside retention

    const doomed = pruneParkedRewindFramesOn(db, 5_000)

    expect(doomed).toEqual([{ ts: 1_000, imagePath: '/rewind/2026-10-01/1000.jpg' }])
    expect(doomed).not.toContainEqual({ ts: 6_000, imagePath: '/rewind/2026-10-01/6000.jpg' })
    expect(countRewind(db, 'rewind_frames_parked')).toBe(1)
    const kept = db.prepare('SELECT owner_uid FROM rewind_frames_parked').get() as {
      owner_uid: string
    }
    expect(kept.owner_uid).toBe('uidA')
  })

  it('keeps a parked row exactly AT the cutoff (strict <, same boundary as live retention)', () => {
    const db = makeRewindDb()
    insertParked(db, 'uidA', 5_000, '/rewind/2026-10-01/5000.jpg')

    expect(pruneParkedRewindFramesOn(db, 5_000)).toEqual([])

    expect(countRewind(db, 'rewind_frames_parked')).toBe(1)
  })

  it('is a no-op on a schema that predates the parked table', () => {
    const db = makeRewindDb()
    db.exec('DROP TABLE rewind_frames_parked')

    expect(pruneParkedRewindFramesOn(db, 5_000)).toEqual([])
  })
})
