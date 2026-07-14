// Corruption recovery, proven against REAL corrupted SQLite files on disk — not
// mocks. Recovery cannot be tested by assertion alone: the whole point is how
// SQLite behaves when its pages are damaged, so every test here builds a real DB,
// damages real bytes, and runs the real recovery.
//
// Driver: node:sqlite's DatabaseSync (the seam RecoveryDriver exists for).
// Production uses better-sqlite3, which cannot load under plain-node vitest
// (rebuilt for Electron's ABI) — the better-sqlite3 wiring is covered by the
// _electron smoke in e2e/db-recovery.spec.mjs instead.
import { DatabaseSync } from 'node:sqlite'
import { randomBytes } from 'node:crypto'
import {
  closeSync,
  existsSync,
  mkdtempSync,
  openSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  truncateSync,
  writeFileSync,
  writeSync
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  backupCorruptDb,
  clearCorruptionFlags,
  isAccessError,
  isCorruptionError,
  isCorruptionSuspected,
  markCorruptionSuspected,
  MAX_REPAIR_ATTEMPTS,
  openDatabaseWithRecovery,
  probeTables,
  pruneBackups,
  repairSuspectedCorruption,
  salvage,
  salvageIsAnImprovement,
  type RecoveryDb,
  type RecoveryDriver
} from './dbRecovery'

const driver: RecoveryDriver = {
  open: (f) => new DatabaseSync(f) as unknown as RecoveryDb,
  openReadonly: (f) => new DatabaseSync(f, { readOnly: true }) as unknown as RecoveryDb
}

let dir: string
let dbFile: string
let backupsDir: string

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'omi-dbrec-'))
  dbFile = join(dir, 'omi.db')
  backupsDir = join(dir, 'backups')
})

afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

// A miniature omi.db: several user tables (so we can prove salvage is
// table-agnostic), an FTS5 external-content index + its sync trigger (so we can
// prove the vtable/shadow-table handling), and enough rows to span many pages.
function buildDb(file: string): void {
  const d = new DatabaseSync(file)
  d.exec(`
    CREATE TABLE local_conversation (id TEXT PRIMARY KEY, transcript TEXT, created_at INTEGER);
    CREATE TABLE rewind_frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, ocr_text TEXT, image_path TEXT
    );
    CREATE INDEX idx_rewind_frames_ts ON rewind_frames(ts);
    CREATE TABLE insights (id INTEGER PRIMARY KEY AUTOINCREMENT, headline TEXT, advice TEXT);
    CREATE TABLE app_usage (exe_path TEXT PRIMARY KEY, total_seconds INTEGER);
    CREATE VIRTUAL TABLE rewind_frames_fts USING fts5(
      ocr_text, content='rewind_frames', content_rowid='id'
    );
    CREATE TRIGGER rewind_frames_ai AFTER INSERT ON rewind_frames BEGIN
      INSERT INTO rewind_frames_fts(rowid, ocr_text) VALUES (new.id, new.ocr_text);
    END;
  `)
  const pad = (s: string, n: number): string => (s + ' ').repeat(n)
  // One transaction for the whole seed — 1450 auto-committed inserts means 1450
  // fsyncs, which is slow enough to blow the test timeout on Windows.
  d.exec('BEGIN')
  const conv = d.prepare('INSERT INTO local_conversation VALUES (?, ?, ?)')
  for (let i = 0; i < 300; i++) conv.run(`conv-${i}`, pad(`transcript body ${i}`, 40), i)
  const frame = d.prepare('INSERT INTO rewind_frames (ts, ocr_text, image_path) VALUES (?, ?, ?)')
  for (let i = 0; i < 800; i++) frame.run(i, pad(`ocr text page ${i}`, 30), `C:/img/${i}.jpg`)
  const ins = d.prepare('INSERT INTO insights (headline, advice) VALUES (?, ?)')
  for (let i = 0; i < 200; i++) ins.run(`headline ${i}`, pad(`advice ${i}`, 20))
  const usage = d.prepare('INSERT INTO app_usage VALUES (?, ?)')
  for (let i = 0; i < 150; i++) usage.run(`C:/app${i}.exe`, i * 10)
  d.exec('COMMIT')
  d.exec('PRAGMA user_version = 2')
  d.close()
}

/** Overwrite `len` bytes at `offset` with random noise — real page corruption. */
function clobber(file: string, offset: number, len: number): void {
  const fd = openSync(file, 'r+')
  writeSync(fd, randomBytes(len), 0, len, offset)
  closeSync(fd)
}

function countRows(file: string, table: string): number {
  const d = new DatabaseSync(file, { readOnly: true })
  try {
    return (d.prepare(`SELECT count(*) AS n FROM ${table}`).get() as { n: number }).n
  } finally {
    d.close()
  }
}

function backupNames(): string[] {
  return existsSync(backupsDir) ? readdirSync(backupsDir).sort() : []
}

describe('isCorruptionError', () => {
  it('matches SQLITE_CORRUPT, NOTADB, IOERR_CORRUPTFS and malformed messages', () => {
    expect(isCorruptionError({ code: 'SQLITE_CORRUPT' })).toBe(true)
    expect(isCorruptionError({ code: 'SQLITE_CORRUPT_VTAB' })).toBe(true)
    expect(isCorruptionError({ code: 'SQLITE_NOTADB' })).toBe(true)
    expect(isCorruptionError({ code: 'SQLITE_IOERR_CORRUPTFS' })).toBe(true)
    expect(isCorruptionError({ errcode: 11 })).toBe(true) // SQLITE_CORRUPT
    expect(isCorruptionError({ errcode: 26 })).toBe(true) // SQLITE_NOTADB
    expect(isCorruptionError({ errcode: 267 })).toBe(true) // SQLITE_CORRUPT_VTAB
    expect(isCorruptionError({ errcode: 6922 })).toBe(true) // SQLITE_IOERR_CORRUPTFS
    expect(isCorruptionError(new Error('database disk image is malformed'))).toBe(true)
    expect(isCorruptionError(new Error('file is not a database'))).toBe(true)
    expect(isCorruptionError(new Error('file is encrypted or is not a database'))).toBe(true)
  })

  // The false-positive guard: a wrong "corrupt" verdict destroys a healthy DB.
  it('does NOT match unrelated errors', () => {
    expect(isCorruptionError({ code: 'SQLITE_BUSY', message: 'database is locked' })).toBe(false)
    expect(isCorruptionError({ errcode: 5 })).toBe(false) // BUSY
    expect(isCorruptionError({ errcode: 6 })).toBe(false) // LOCKED
    expect(isCorruptionError({ errcode: 14 })).toBe(false) // CANTOPEN
    expect(isCorruptionError(new Error('no such column: foo'))).toBe(false)
    expect(isCorruptionError(new Error('table x has no column named y'))).toBe(false)
    expect(isCorruptionError(new Error('UNIQUE constraint failed'))).toBe(false)
    expect(isCorruptionError({ code: 'EACCES' })).toBe(false)
    expect(isCorruptionError({ code: 'ENOSPC', message: 'database or disk is full' })).toBe(false)
    expect(isCorruptionError(null)).toBe(false)
    expect(isCorruptionError(undefined)).toBe(false)
  })

  it('classifies access errors separately so they are never recovered from', () => {
    expect(isAccessError({ code: 'SQLITE_BUSY' })).toBe(true)
    expect(isAccessError({ code: 'EACCES' })).toBe(true)
    expect(isAccessError({ errcode: 8 })).toBe(true) // READONLY
    expect(isAccessError(new Error('permission denied'))).toBe(true)
    expect(isAccessError({ code: 'SQLITE_CORRUPT' })).toBe(false)
  })
})

describe('backup retention', () => {
  it('keeps only the 5 newest backups', () => {
    buildDb(dbFile)
    const made: string[] = []
    for (let i = 0; i < 8; i++) {
      // Distinct timestamps: one per minute, oldest first.
      made.push(backupCorruptDb(dbFile, backupsDir, new Date(2026, 0, 1, 12, i, 0)))
    }
    const kept = backupNames()
    expect(kept).toHaveLength(5)
    // The 5 newest (minutes 3..7) survive; 0..2 are gone.
    expect(kept).toEqual([
      'omi_corrupted_20260101_120300.db',
      'omi_corrupted_20260101_120400.db',
      'omi_corrupted_20260101_120500.db',
      'omi_corrupted_20260101_120600.db',
      'omi_corrupted_20260101_120700.db'
    ])
    expect(existsSync(made[0])).toBe(false)
    expect(existsSync(made[7])).toBe(true)
  })

  it('backs up the real bytes of the corrupt file', () => {
    buildDb(dbFile)
    clobber(dbFile, 100, 8)
    const path = backupCorruptDb(dbFile, backupsDir)
    expect(readFileSync(path).equals(readFileSync(dbFile))).toBe(true)
  })

  it('prunes nothing when the directory does not exist', () => {
    expect(pruneBackups(join(dir, 'nope'))).toEqual([])
  })
})

describe('openDatabaseWithRecovery — healthy databases are never touched', () => {
  // The single most important test in this file. A false corruption verdict
  // would destroy good data, so prove the happy path is inert.
  it('leaves a healthy database completely untouched', () => {
    buildDb(dbFile)
    const before = readFileSync(dbFile)
    const { db, status } = openDatabaseWithRecovery(dbFile, driver, { backupsDir })
    db.close()

    expect(status.recovered).toBe(false)
    expect(status.reset).toBe(false)
    expect(status.backupPath).toBeNull()
    expect(backupNames()).toEqual([]) // no backup taken
    expect(readFileSync(dbFile).equals(before)).toBe(true) // byte-identical
    expect(countRows(dbFile, 'local_conversation')).toBe(300)
    expect(countRows(dbFile, 'rewind_frames')).toBe(800)
  })

  it('creates a fresh database when the file does not exist (not a corruption)', () => {
    const { db, status } = openDatabaseWithRecovery(dbFile, driver, { backupsDir })
    db.close()
    expect(status.recovered).toBe(false)
    expect(existsSync(dbFile)).toBe(true)
    expect(backupNames()).toEqual([])
  })
})

describe('openDatabaseWithRecovery — corruption is detected and handled', () => {
  // Schema-page corruption: SQLite can see it (the sanity query throws), but
  // sqlite_master is unreadable so nothing can be salvaged → backup + reset.
  it.each([
    ['zeroed header magic', (f: string) => clobber(f, 0, 16)],
    ['damaged page-1 b-tree header', (f: string) => clobber(f, 100, 8)],
    ['garbage inside the schema page', (f: string) => clobber(f, 3000, 500)],
    ['truncated file', (f: string) => truncateSync(f, Math.floor(statSync(f).size * 0.6))]
  ])('detects %s, backs it up, and resets to a working database', (_label, damage) => {
    buildDb(dbFile)
    damage(dbFile)

    const { db, status } = openDatabaseWithRecovery(dbFile, driver, { backupsDir })

    expect(status.recovered).toBe(true)
    expect(status.reset).toBe(true) // schema is dead — nothing salvageable
    expect(status.rowsRecovered).toBe(0)
    expect(status.backupPath).not.toBeNull()
    expect(backupNames()).toHaveLength(1)

    // The app ends up with a working database it can build a schema on.
    db.exec('CREATE TABLE IF NOT EXISTS smoke (id INTEGER PRIMARY KEY)')
    db.prepare('INSERT INTO smoke (id) VALUES (1)').run()
    expect((db.prepare('SELECT count(*) AS n FROM smoke').get() as { n: number }).n).toBe(1)
    db.close()
  })

  it('detects a total-garbage file, backs it up, and resets', () => {
    writeFileSync(dbFile, randomBytes(5000))
    const { db, status } = openDatabaseWithRecovery(dbFile, driver, { backupsDir })
    expect(status.recovered).toBe(true)
    expect(status.reset).toBe(true)
    expect(backupNames()).toHaveLength(1)
    db.exec('CREATE TABLE IF NOT EXISTS smoke (id INTEGER PRIMARY KEY)') // usable
    db.close()
  })
})

describe('salvage — table-agnostic, per-table and per-row resilient', () => {
  // The case that actually matters for user data: a damaged DATA page. Other
  // tables are perfectly readable, and even the damaged table gives up almost
  // all of its rows. macOS would salvage only `screenshots` and throw the rest
  // away; we must keep conversations, insights and usage too.
  it('salvages EVERY table when one table sits on a corrupt page', () => {
    buildDb(dbFile)
    const size = statSync(dbFile).size
    // Clobber a whole page in the middle of the file (lands in rewind_frames).
    clobber(dbFile, Math.floor(size / 2) & ~4095, 4096)

    const out = join(dir, 'salvaged.db')
    const result = salvage(dbFile, out, driver)

    // Untouched tables come across whole — this is the macOS deviation that
    // stops a rewind-page corruption from destroying the user's conversations.
    expect(result.tables['local_conversation']).toBe(300)
    expect(result.tables['insights']).toBe(200)
    expect(result.tables['app_usage']).toBe(150)

    // The damaged table loses only the rows on the bad page, not the whole table.
    const frames = result.tables['rewind_frames'] ?? 0
    expect(frames).toBeGreaterThan(700)
    expect(frames).toBeLessThan(800)

    expect(result.rows).toBe(300 + 200 + 150 + frames)

    // The salvaged DB is real and queryable.
    expect(countRows(out, 'local_conversation')).toBe(300)
    expect(countRows(out, 'rewind_frames')).toBe(frames)

    // FTS virtual table + its shadow tables are skipped, never copied raw.
    expect(result.skipped).toContain('rewind_frames_fts')
    expect(Object.keys(result.tables)).not.toContain('rewind_frames_fts')
    expect(Object.keys(result.tables).some((t) => t.startsWith('rewind_frames_fts_'))).toBe(false)

    // Schema extras survive so the recovered DB behaves like the original.
    const d = new DatabaseSync(out, { readOnly: true })
    const version = (d.prepare('PRAGMA user_version').get() as { user_version: number })
      .user_version
    const idx = d
      .prepare("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rewind_frames_ts'")
      .get()
    d.close()
    expect(version).toBe(2) // migration version preserved
    expect(idx).toBeTruthy() // index recreated
  })

  it('copies a healthy database in full', () => {
    buildDb(dbFile)
    const out = join(dir, 'copy.db')
    const result = salvage(dbFile, out, driver)
    expect(result.tables).toEqual({
      local_conversation: 300,
      rewind_frames: 800,
      insights: 200,
      app_usage: 150
    })
    expect(result.rows).toBe(1450)
  })

  it('returns nothing when the schema itself is unreadable', () => {
    buildDb(dbFile)
    clobber(dbFile, 100, 8) // page-1 b-tree header
    const result = salvage(dbFile, join(dir, 'out.db'), driver)
    expect(result.rows).toBe(0)
    expect(result.tables).toEqual({})
  })

  it('returns nothing for a file that is not a database', () => {
    writeFileSync(dbFile, randomBytes(5000))
    expect(salvage(dbFile, join(dir, 'out.db'), driver).rows).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// The runtime trip (option B) — the whole reason the salvage engine is reachable.
//
// A damaged DATA page is invisible to open+sanity: the app starts, the schema
// reads, and only the damaged table throws — forever, silently. These tests pin
// that entire path: not detected at startup -> a live query trips the classifier
// -> the flag persists -> the next launch re-verifies, salvages, and swaps.
// ---------------------------------------------------------------------------

/** Damage a data page in the middle of the file. Lands in rewind_frames and
 *  leaves the schema page and every other table perfectly readable. */
function corruptDataPage(file: string): void {
  const size = statSync(file).size
  clobber(file, Math.floor(size / 2) & ~4095, 4096)
}

function openDb(file: string): RecoveryDb {
  return new DatabaseSync(file) as unknown as RecoveryDb
}

describe('runtime corruption trip (option B)', () => {
  it('a damaged data page is NOT detected at startup — this is why the trip exists', () => {
    buildDb(dbFile)
    corruptDataPage(dbFile)

    const { db, status } = openDatabaseWithRecovery(dbFile, driver, { backupsDir })
    // Open succeeds and the sanity query passes: macOS's detector is blind here.
    expect(status.recovered).toBe(false)
    expect(backupNames()).toEqual([])

    // But a real query against the damaged table throws a corrupt error...
    let thrown: unknown
    try {
      db.prepare('SELECT * FROM rewind_frames').all()
    } catch (e) {
      thrown = e
    }
    expect(thrown, 'the damaged table must actually throw').toBeDefined()
    // ...and the classifier recognizes it. That is the trip.
    expect(isCorruptionError(thrown)).toBe(true)

    // Sibling tables are untouched — a wipe here would be catastrophic.
    expect(
      (db.prepare('SELECT count(*) AS n FROM local_conversation').get() as { n: number }).n
    ).toBe(300)
    db.close()
  })

  it('persists the suspicion so the next launch can repair', () => {
    buildDb(dbFile)
    const db = openDb(dbFile)
    expect(isCorruptionSuspected(db)).toBe(false)
    expect(markCorruptionSuspected(db)).toBe(true)
    db.close()

    // Survives a restart (it is on disk, not in memory).
    const next = openDb(dbFile)
    expect(isCorruptionSuspected(next)).toBe(true)
    clearCorruptionFlags(next)
    expect(isCorruptionSuspected(next)).toBe(false)
    next.close()
  })

  // THE test for option B: the end-to-end case the orchestrator required.
  it('repairs on the next launch: every other table intact, most of the damaged table recovered', () => {
    buildDb(dbFile)
    corruptDataPage(dbFile)

    // --- session 1: a live query trips the flag ---
    const s1 = openDb(dbFile)
    expect(() => s1.prepare('SELECT * FROM rewind_frames').all()).toThrow()
    markCorruptionSuspected(s1)
    s1.close()

    // --- session 2 (next launch): re-verify, salvage, swap ---
    const s2 = openDb(dbFile)
    expect(isCorruptionSuspected(s2)).toBe(true)
    const outcome = repairSuspectedCorruption(s2, dbFile, driver, { backupsDir })

    expect(outcome.action).toBe('repaired')
    if (outcome.action !== 'repaired') throw new Error('unreachable')
    expect(outcome.damaged).toContain('rewind_frames')
    expect(outcome.status.recovered).toBe(true)
    expect(outcome.status.reset).toBe(false)
    expect(outcome.status.backupPath).not.toBeNull()
    expect(backupNames()).toHaveLength(1)

    // The user's OTHER data — conversations, insights, usage — survives whole.
    // macOS's recovery salvages only `screenshots` and would have destroyed all of this.
    expect(countRows(dbFile, 'local_conversation')).toBe(300)
    expect(countRows(dbFile, 'insights')).toBe(200)
    expect(countRows(dbFile, 'app_usage')).toBe(150)

    // The damaged table loses only the rows on the bad page — not the whole table.
    const frames = countRows(dbFile, 'rewind_frames')
    expect(frames).toBeGreaterThan(700)
    expect(frames).toBeLessThan(800)
    // Per-table, so the total can't hide a shortfall. (app_meta rides along too —
    // it carries the flag + attempt counter, which is exactly how the boot-loop
    // budget survives a rebuild.)
    expect(outcome.status.tablesRecovered).toMatchObject({
      local_conversation: 300,
      insights: 200,
      app_usage: 150,
      rewind_frames: frames
    })

    // And the repaired database is genuinely healthy now: the read that used to
    // throw works.
    const after = openDb(dbFile)
    expect(() => after.prepare('SELECT * FROM rewind_frames').all()).not.toThrow()
    expect(probeTables(after).damaged).toEqual([])
    clearCorruptionFlags(after)
    after.close()
  })

  // FALSE-POSITIVE SAFETY: the flag is a suspicion, never a verdict.
  it('does NOT rebuild when the damage does not reproduce (transient/misclassified)', () => {
    buildDb(dbFile)

    // Flag set, but the database is perfectly healthy — e.g. a one-off error, or a
    // misclassification. Rebuilding here would be destroying good data.
    const db = openDb(dbFile)
    markCorruptionSuspected(db)
    const outcome = repairSuspectedCorruption(db, dbFile, driver, { backupsDir })

    expect(outcome.action).toBe('no_repair_needed')
    expect(backupNames()).toEqual([]) // nothing backed up
    expect(isCorruptionSuspected(db)).toBe(false) // flag cleared
    db.close()

    // Every row still there, and no rebuild ever happened: the file was never
    // swapped (no salvage temp left behind) and the schema version is untouched.
    // (The file's byte length legitimately changes — writing then deleting the flag
    // touches app_meta — so the meaningful assertions are the data ones.)
    expect(countRows(dbFile, 'local_conversation')).toBe(300)
    expect(countRows(dbFile, 'rewind_frames')).toBe(800)
    expect(countRows(dbFile, 'insights')).toBe(200)
    expect(readdirSync(dir).filter((f) => f.includes('.salvage-'))).toEqual([])
    const d = new DatabaseSync(dbFile, { readOnly: true })
    const version = (d.prepare('PRAGMA user_version').get() as { user_version: number })
      .user_version
    d.close()
    expect(version).toBe(2)
  })

  // NO BOOT LOOP: a repair that keeps failing must not rebuild on every launch.
  it('gives up after MAX_REPAIR_ATTEMPTS and leaves the database alone', () => {
    buildDb(dbFile)
    corruptDataPage(dbFile)

    const db = openDb(dbFile)
    markCorruptionSuspected(db)
    // Simulate MAX_REPAIR_ATTEMPTS already-burned attempts (each prior launch tried
    // and crashed before clearing the flag).
    db.prepare('INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)').run(
      ...(['db_repair_attempts', String(MAX_REPAIR_ATTEMPTS)] as never[])
    )

    const outcome = repairSuspectedCorruption(db, dbFile, driver, { backupsDir })
    expect(outcome.action).toBe('abandoned')
    if (outcome.action !== 'abandoned') throw new Error('unreachable')
    expect(outcome.attempts).toBe(MAX_REPAIR_ATTEMPTS)

    // Nothing destructive happened: no backup, no swap, data as it was.
    expect(backupNames()).toEqual([])
    db.close()
    expect(countRows(dbFile, 'local_conversation')).toBe(300)
  })

  it('counts the attempt BEFORE repairing, so a crash mid-repair still burns budget', () => {
    buildDb(dbFile)
    corruptDataPage(dbFile)
    const db = openDb(dbFile)
    markCorruptionSuspected(db)
    repairSuspectedCorruption(db, dbFile, driver, { backupsDir })

    // The repaired DB carries the incremented counter across (app_meta is salvaged).
    const after = openDb(dbFile)
    const row = after
      .prepare('SELECT value FROM app_meta WHERE key = ?')
      .get(...(['db_repair_attempts'] as never[])) as { value: string } | undefined
    after.close()
    expect(row?.value).toBe('1')
  })
})

describe('never rebuild into a worse state', () => {
  it('refuses a swap that would lose rows a working table still serves', () => {
    // A table that currently reads 300 rows must never come back with fewer.
    const probe = {
      readable: { local_conversation: 300, rewind_frames: 0 },
      damaged: ['rewind_frames']
    }
    expect(
      salvageIsAnImprovement(probe, {
        rows: 1050,
        tables: { local_conversation: 250, rewind_frames: 800 }, // lost 50 good rows!
        skipped: []
      })
    ).toBe(false)
  })

  it('allows a swap that rescues a table which currently throws entirely', () => {
    // The 793/800 case: rewind_frames serves NOTHING today, so 793 is pure gain.
    const probe = {
      readable: { local_conversation: 300, rewind_frames: 0 },
      damaged: ['rewind_frames']
    }
    expect(
      salvageIsAnImprovement(probe, {
        rows: 1093,
        tables: { local_conversation: 300, rewind_frames: 793 },
        skipped: []
      })
    ).toBe(true)
  })

  it('refuses a swap that salvaged nothing at all', () => {
    const probe = { readable: { local_conversation: 300 }, damaged: ['rewind_frames'] }
    expect(salvageIsAnImprovement(probe, { rows: 0, tables: {}, skipped: [] })).toBe(false)
  })
})
