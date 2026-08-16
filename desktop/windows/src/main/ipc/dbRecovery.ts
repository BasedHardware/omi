/**
 * SQLite corruption detection + recovery for omi.db.
 *
 * Ported from macOS `RewindDatabase.swift`, with the deviations forced by the
 * platform written down below. Kept free of `electron` and `better-sqlite3`
 * imports so it is unit-testable under plain-node vitest against REAL corrupted
 * files via `node:sqlite` (the same driver-injection seam dbMigrations.ts and
 * agentKernel/store.ts use — better-sqlite3 is rebuilt for Electron's ABI and
 * cannot load there).
 *
 * DETECTION IS REACTIVE, NEVER A PROACTIVE SCAN. macOS deliberately does not run
 * `PRAGMA quick_check` at open ("scans the entire DB, 75s+ on 4GB databases") and
 * neither do we. We only classify errors that SQLite itself raises:
 *   - open fails, or
 *   - the post-open sanity query (`SELECT count(*) FROM sqlite_master`) throws.
 *
 * WHAT THAT DETECTOR CAN AND CANNOT SEE (measured against real corrupted files —
 * these numbers drive the design, see dbRecovery.test.ts which asserts them):
 *   - Corruption of the SCHEMA (page 1 / header / truncation / garbage file) is
 *     detected — but then `sqlite_master` is unreadable, so every table read
 *     throws and salvage recovers exactly ZERO rows. These recoveries are always
 *     a reset.
 *   - Corruption of a DATA page is NOT visible to open+sanity, but it is highly
 *     salvageable: the other tables read perfectly and even the damaged table
 *     gives up ~99% of its rows to a per-rowid scan. This is the case worth
 *     salvaging, and it is why `salvage()` is table-agnostic and row-resilient.
 *
 * Salvage runs at the SQL layer because Windows has no `sqlite3` CLI and
 * better-sqlite3 exposes no `.recover` (macOS shells out to `sqlite3 <db>
 * .recover`, which scrapes raw b-tree pages beneath the schema). We therefore
 * cannot beat a dead schema page — but unlike macOS, which salvages only the
 * `screenshots` table and silently discards everything else, we copy EVERY table
 * (conversations, chat, memories, tasks) with per-table and per-row isolation, so
 * one unreadable table or one bad page never costs more than itself.
 *
 * THE DESTRUCTIVE RULES, which every path here obeys:
 *   - The corrupt database is MOVED aside (archiveCorruptDb), never copied and then
 *     deleted. If it cannot be moved, the repair is abandoned with the original
 *     intact — we would rather ship a broken database than a missing one.
 *   - A swap only happens once the salvaged replacement is a PROVEN improvement on
 *     what the database serves today (salvageIsAnImprovement).
 *   - Every destructive path is gated on a POSITIVE corruption verdict from
 *     isCorruptionError. Busy / locked / read-only / disk-full is never corruption.
 *   - All of it runs at startup, from db.ts's single-threaded open, before the
 *     read-only handle or the KG worker's connection exist.
 */
import { copyFileSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from 'fs'
import { basename, dirname, join } from 'path'
import type { DbRecoveryStatus } from '../../shared/types'

// --- Driver seam -----------------------------------------------------------
// The minimal SQLite surface recovery needs, satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests).

export interface RecoveryStatement {
  all(...params: never[]): unknown[]
  get(...params: never[]): unknown
  run(...params: never[]): unknown
}

export interface RecoveryDb {
  exec(sql: string): unknown
  prepare(sql: string): RecoveryStatement
  close(): void
}

export interface RecoveryDriver {
  /** Open read-write, creating the file if absent. */
  open(file: string): RecoveryDb
  /** Open read-only; used to read the corrupt file during salvage. */
  openReadonly(file: string): RecoveryDb
}

// --- Error classification ---------------------------------------------------

// Primary result codes (err & 0xff). 11 = SQLITE_CORRUPT, 26 = SQLITE_NOTADB
// ("file is not a database" — what a garbage/overwritten header produces).
// SQLITE_IOERR_CORRUPTFS (extended 6922, primary 10 = SQLITE_IOERR) is corruption
// too, but its primary code is access-like, so it is matched by its exact extended
// code at the very top of isCorruptionError, ahead of the access gate.
const CORRUPT_PRIMARY_CODES = new Set([11, 26])

const CORRUPT_MESSAGE_PATTERNS = [
  'database disk image is malformed',
  'malformed database schema',
  'file is not a database',
  'file is encrypted or is not a database'
]

// Errors that mean "someone else holds it" or "we may not touch it" — NEVER
// corruption, and never a reason to delete a WAL or replace a file. Being wrong
// in this direction destroys a healthy database, so these are checked first and
// always rethrown untouched.
const ACCESS_ERROR_PATTERNS = [
  'database is locked',
  'database table is locked',
  'permission denied',
  'access is denied',
  'attempt to write a readonly database',
  'disk i/o error',
  'database or disk is full'
]
const ACCESS_CODE_PREFIXES = [
  'SQLITE_BUSY',
  'SQLITE_LOCKED',
  'SQLITE_PERM',
  'SQLITE_READONLY',
  'SQLITE_AUTH',
  'SQLITE_FULL',
  'SQLITE_CANTOPEN',
  'EBUSY',
  'EACCES',
  'EPERM',
  'EROFS',
  'ENOSPC',
  'EMFILE'
]
// Primary codes: 5 BUSY, 6 LOCKED, 3 PERM, 8 READONLY, 23 AUTH, 13 FULL, 14 CANTOPEN.
const ACCESS_PRIMARY_CODES = new Set([3, 5, 6, 8, 13, 14, 23])

function errorText(err: { errstr?: unknown; message?: unknown }): string {
  const parts = [err.errstr, err.message].filter((p): p is string => typeof p === 'string')
  return parts.join(' ').toLowerCase()
}

/** True for an error that means the DB is unreadable-because-damaged. Deliberately
 *  narrow: a false positive here would wipe a healthy database. */
export function isCorruptionError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const e = err as { code?: unknown; errcode?: unknown; errstr?: unknown; message?: unknown }
  // SQLITE_IOERR_CORRUPTFS is filesystem-level corruption the DB cannot recover
  // from in place — genuinely corrupt, not transient I/O. Its own message is the
  // generic "disk i/o error", which ALSO matches an access pattern, so it must be
  // recognised BEFORE the access gate or it would be misfiled as transient and the
  // file never repaired. Only this EXACT extended signal jumps the gate; a plain
  // SQLITE_IOERR (a transient read/write blip) stays access and is left untouched.
  const code = typeof e.code === 'string' ? e.code.toUpperCase() : ''
  if (code === 'SQLITE_IOERR_CORRUPTFS' || e.errcode === 6922) return true
  // Any other access/lock/disk error is never corruption, whatever else it looks like.
  if (isAccessError(err)) return false
  if (code.startsWith('SQLITE_CORRUPT') || code.startsWith('SQLITE_NOTADB')) return true
  if (typeof e.errcode === 'number') {
    // eslint-disable-next-line no-bitwise -- SQLite extended codes are primary | (sub << 8)
    if (CORRUPT_PRIMARY_CODES.has(e.errcode & 0xff)) return true
  }
  const text = errorText(e)
  return CORRUPT_MESSAGE_PATTERNS.some((p) => text.includes(p))
}

/** True for "busy / locked / no permission / disk full" — hands off the file. */
export function isAccessError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const e = err as { code?: unknown; errcode?: unknown; errstr?: unknown; message?: unknown }
  if (typeof e.code === 'string') {
    const code = e.code.toUpperCase()
    if (ACCESS_CODE_PREFIXES.some((p) => code.startsWith(p))) return true
  }
  // eslint-disable-next-line no-bitwise -- see above
  if (typeof e.errcode === 'number' && ACCESS_PRIMARY_CODES.has(e.errcode & 0xff)) return true
  const text = errorText(e)
  return ACCESS_ERROR_PATTERNS.some((p) => text.includes(p))
}

// --- Archiving the corrupt file ---------------------------------------------
//
// THE CORRUPT DATABASE IS *MOVED* ASIDE, NEVER COPIED-THEN-DELETED. A copy that
// fails halfway (disk full, a short write, a crash) followed by an unlink of the
// original loses everything the user had. A rename is atomic: after it, the bytes
// exist in exactly one place, and if it throws, they are still in the original
// place and NOTHING destructive has happened. Every destructive path in this file
// therefore goes through archiveCorruptDb(), and a failure to archive ABORTS the
// repair rather than proceeding without a backup.

/** macOS keeps the 5 newest `omi_corrupted_*.db` backups; so do we. */
export const BACKUP_RETENTION = 5
const BACKUP_PREFIX = 'omi_corrupted_'
const BACKUP_RE = /^omi_corrupted_.*\.db$/

function stamp(now: Date): string {
  const p = (n: number, w = 2): string => String(n).padStart(w, '0')
  return (
    `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}` +
    `_${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`
  )
}

/** Delete all but the `keep` newest backups. The timestamp format sorts
 *  lexicographically in chronological order, so a name sort is a time sort. */
export function pruneBackups(backupsDir: string, keep = BACKUP_RETENTION): string[] {
  if (!existsSync(backupsDir)) return []
  const names = readdirSync(backupsDir)
    .filter((n) => BACKUP_RE.test(n))
    .sort()
    .reverse() // newest first
  const doomed = names.slice(keep)
  for (const n of doomed) rmSync(join(backupsDir, n), { force: true })
  return doomed
}

/** rename(), tolerating the same transient Windows EBUSY that forceRemove() does. */
function forceRename(from: string, to: string, attempts = 10): void {
  for (let i = 0; ; i++) {
    try {
      renameSync(from, to)
      return
    } catch (err) {
      if (i >= attempts - 1) throw err
      sleep(50)
    }
  }
}

/**
 * MOVE the corrupt database to `<backupsDir>/omi_corrupted_<yyyyMMdd_HHmmss>.db`
 * and prune to the 5 newest. Returns the archive path.
 *
 * Throws if the file cannot be moved anywhere — and that is the point: the caller
 * must then abandon the repair with the original still intact. A rename needs the
 * same rights an unlink does, so a failure here means the destructive path could
 * not have completed safely either; refusing to continue costs the user a broken
 * database, while continuing would cost them the data inside it.
 */
export function archiveCorruptDb(dbFile: string, backupsDir: string, now = new Date()): string {
  const base = `${BACKUP_PREFIX}${stamp(now)}`
  const candidates: string[] = []
  try {
    mkdirSync(backupsDir, { recursive: true })
    // Two corruptions inside one second would otherwise overwrite the older archive.
    let dest = join(backupsDir, `${base}.db`)
    for (let i = 1; existsSync(dest); i++) dest = join(backupsDir, `${base}_${i}.db`)
    candidates.push(dest)
  } catch {
    // The backups directory is unusable; the sibling fallback below still works.
  }
  // Last resort: right next to omi.db, which is by definition a writable directory
  // on the same volume (the app has been writing the database there all along).
  candidates.push(`${dbFile}.corrupt-${stamp(now)}`)

  let lastErr: unknown
  for (const dest of candidates) {
    try {
      forceRename(dbFile, dest)
      try {
        pruneBackups(backupsDir)
      } catch {
        // Retention is housekeeping; never fail an archive over it.
      }
      return dest
    } catch (err) {
      lastErr = err
    }
  }
  throw lastErr instanceof Error
    ? lastErr
    : new Error(`could not move the corrupt database aside: ${String(lastErr)}`)
}

// --- Salvage ----------------------------------------------------------------

export type SalvageResult = {
  /** Total rows copied across every table. */
  rows: number
  /** Rows copied, per table (only tables that yielded >= 1 row). */
  tables: Record<string, number>
  /** Tables present in the corrupt DB that produced nothing (unreadable), plus
   *  virtual/shadow tables we deliberately skip. */
  skipped: string[]
}

const EMPTY_SALVAGE: SalvageResult = { rows: 0, tables: {}, skipped: [] }

type MasterRow = { type: string; name: string; sql: string }

// FTS5 keeps its index in shadow tables (`<name>_data`, `_idx`, `_content`,
// `_docsize`, `_config`). Copying those raw would produce a corrupt index, so we
// skip the virtual table and its shadows entirely; db.ts recreates the vtable
// from its CREATE VIRTUAL TABLE IF NOT EXISTS and rebuilds the index from the
// recovered content rows (the `'rebuild'` command, same idiom as migration v2).
const FTS_SHADOW_SUFFIXES = ['data', 'idx', 'content', 'docsize', 'config']

function isVirtual(sql: string): boolean {
  return /^\s*create\s+virtual\s+table/i.test(sql)
}

function quote(id: string): string {
  return `"${id.replace(/"/g, '""')}"`
}

function readMaster(src: RecoveryDb): MasterRow[] {
  const rows = src
    .prepare(
      "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"
    )
    .all() as MasterRow[]
  return rows.filter((r) => typeof r.sql === 'string' && typeof r.name === 'string')
}

/** Column names of `table` as created in the destination DB. */
function columnsOf(db: RecoveryDb, table: string): string[] {
  const cols = db.prepare(`PRAGMA table_info(${quote(table)})`).all() as { name: string }[]
  return cols.map((c) => c.name)
}

// --- The resilient table scanner --------------------------------------------
//
// Every read of a possibly-damaged table — both the salvage copy and the probe
// that re-verifies corruption — goes through this. Two properties matter:
//
//   1. MEMORY IS BOUNDED. A plain `SELECT * FROM rewind_frames` materialises the
//      whole table; on a real omi.db that is gigabytes, and it would run at
//      startup, inside the repair path, on a machine that has just been through a
//      power loss. It reads in CHUNK-row windows instead and never holds more.
//   2. THERE IS NO ROW-COUNT CEILING. An earlier cut of this bailed out (returning
//      ZERO rows) once max(rowid) passed a cap — which on any real machine's
//      rewind_frames would have thrown away a table it could have salvaged almost
//      entirely, i.e. exactly the "silently discards the user's data" bug we came
//      here to avoid. Work is bounded by a single-row PROBE budget instead, which
//      only ever accrues around actual damage.
//
// A corrupt page kills the whole b-tree scan it sits on, so when a window throws,
// each rowid in that window is fetched individually: one bad page then costs only
// the rows that live on it. Measured on a real corrupted file: 793 of 800 rows
// recovered from a table whose full scan threw.
const CHUNK = 512
// Only spent walking past damage (a healthy table never fetches a single row on
// its own). Two million seeks is seconds of work and cannot hang startup.
const MAX_SINGLE_ROW_PROBES = 2_000_000

type Row = Record<string, unknown>
type ScanResult = {
  /** Rows the visitor accepted. */
  rows: number
  /** A read raised a corruption error somewhere in this table. */
  corrupt: boolean
}

/**
 * Walk every readable row of `table`, in bounded chunks, tolerating damaged pages.
 * `visit` returns how many of the rows it accepted (salvage counts inserts; the
 * probe counts rows). `colList` is the pre-quoted projection.
 */
function scanTable(
  src: RecoveryDb,
  table: string,
  colList: string,
  visit: (rows: Row[]) => number
): ScanResult {
  const t = quote(table)
  let chunk: RecoveryStatement
  let single: RecoveryStatement
  try {
    chunk = src.prepare(
      `SELECT rowid AS __rid, ${colList} FROM ${t} WHERE rowid > ? ORDER BY rowid LIMIT ${CHUNK}`
    )
    single = src.prepare(`SELECT rowid AS __rid, ${colList} FROM ${t} WHERE rowid = ?`)
  } catch (err) {
    // No usable rowid (a WITHOUT ROWID table, or a view). omi.db has none today,
    // but a future schema might: fall back to a plain read rather than skip it.
    return scanWholeTable(src, t, colList, visit, err)
  }

  let cursor = 0
  let rows = 0
  let corrupt = false
  let probes = 0
  for (;;) {
    let batch: Row[]
    try {
      batch = chunk.all(...([cursor] as never[])) as Row[]
    } catch (err) {
      if (!isCorruptionError(err)) return scanWholeTable(src, t, colList, visit, err)
      // A damaged page inside this window. Fetch its rowids one at a time — the
      // rows that are NOT on the bad page still come back — then step past it.
      corrupt = true
      const end = cursor + CHUNK
      for (let id = cursor + 1; id <= end; id++) {
        if (++probes > MAX_SINGLE_ROW_PROBES) return { rows, corrupt }
        try {
          const row = single.get(...([id] as never[])) as Row | undefined
          if (row) rows += visit([row])
        } catch {
          // This row lives on the corrupt page. Skip it, keep the rest.
        }
      }
      cursor = end
      continue
    }
    if (batch.length === 0) return { rows, corrupt }
    rows += visit(batch)
    const last = Number(batch[batch.length - 1].__rid)
    // Defensive: the cursor MUST advance, or this loops forever.
    if (!Number.isFinite(last) || last <= cursor) return { rows, corrupt }
    cursor = last
  }
}

/** Fallback for a table with no usable rowid: one unbounded read, all or nothing. */
function scanWholeTable(
  src: RecoveryDb,
  quotedTable: string,
  colList: string,
  visit: (rows: Row[]) => number,
  cause: unknown
): ScanResult {
  try {
    return {
      rows: visit(src.prepare(`SELECT ${colList} FROM ${quotedTable}`).all() as Row[]),
      corrupt: false
    }
  } catch (err) {
    return { rows: 0, corrupt: isCorruptionError(err) || isCorruptionError(cause) }
  }
}

/** Copy every readable row of one table into the destination. */
function copyTable(src: RecoveryDb, dest: RecoveryDb, table: string): number {
  const cols = columnsOf(dest, table)
  if (cols.length === 0) return 0
  const colList = cols.map(quote).join(', ')
  const insert = dest.prepare(
    `INSERT OR IGNORE INTO ${quote(table)} (${colList}) VALUES (${cols.map(() => '?').join(', ')})`
  )
  const write = (rows: Row[]): number => {
    let n = 0
    for (const row of rows) {
      try {
        insert.run(...(cols.map((c) => row[c] ?? null) as never[]))
        n++
      } catch {
        // A single row that won't bind (bad blob, constraint) must not stop the rest.
      }
    }
    return n
  }
  return scanTable(src, table, colList, write).rows
}

/**
 * Best-effort copy of every readable table from a corrupt DB into a fresh one.
 * Order matters: tables → rows → indexes → triggers. Creating the triggers before
 * the rows would fire the FTS sync triggers on every insert, against a virtual
 * table we deliberately did not create — failing every single row.
 */
export function salvage(srcFile: string, destFile: string, driver: RecoveryDriver): SalvageResult {
  let src: RecoveryDb | null = null
  let dest: RecoveryDb | null = null
  try {
    src = driver.openReadonly(srcFile)
    let master: MasterRow[]
    try {
      master = readMaster(src)
    } catch {
      // The schema itself is on a dead page: nothing is readable. (Measured: a
      // per-rowid scan of sqlite_master recovers 0 rows here too, so there is no
      // cleverer fallback to attempt.)
      return EMPTY_SALVAGE
    }

    const skipped: string[] = []
    const virtualNames = master
      .filter((r) => r.type === 'table' && isVirtual(r.sql))
      .map((r) => r.name)
    const isShadow = (name: string): boolean =>
      virtualNames.some((v) => FTS_SHADOW_SUFFIXES.some((s) => name === `${v}_${s}`))

    const tables = master
      .filter((r) => r.type === 'table')
      .filter((r) => {
        if (isVirtual(r.sql) || isShadow(r.name)) {
          skipped.push(r.name)
          return false
        }
        return true
      })

    dest = driver.open(destFile)
    // The destination is a throwaway being built from an already-corrupt source:
    // if we crash mid-salvage the swap has not happened, the corrupt original is
    // still there, and the next launch simply redoes this. So durability during
    // the build buys nothing and costs an fsync per row — which on a real omi.db
    // is millions of them. Turn it off and commit per table instead.
    try {
      dest.exec('PRAGMA journal_mode = OFF')
      dest.exec('PRAGMA synchronous = OFF')
    } catch {
      // Not fatal — just slower.
    }
    const result: SalvageResult = { rows: 0, tables: {}, skipped }

    for (const t of tables) {
      try {
        dest.exec(t.sql)
      } catch {
        skipped.push(t.name) // unusable DDL — nothing we can do with this table
        continue
      }
      let n = 0
      try {
        dest.exec('BEGIN')
        n = copyTable(src, dest, t.name)
        dest.exec('COMMIT')
      } catch {
        // Per-table isolation: one unreadable table never aborts the others.
        try {
          dest.exec('ROLLBACK')
        } catch {
          // No transaction open.
        }
        n = 0
      }
      if (n > 0) {
        result.tables[t.name] = n
        result.rows += n
      } else if (!skipped.includes(t.name)) {
        skipped.push(t.name)
      }
    }

    // Indexes and triggers only after the rows are in (see the doc comment). Each
    // is optional — db.ts's bootstrap recreates all of them with IF NOT EXISTS.
    for (const r of master) {
      if (r.type !== 'index' && r.type !== 'trigger') continue
      try {
        dest.exec(r.sql)
      } catch {
        // References a table we could not salvage; bootstrap will recreate it.
      }
    }

    // Preserve the migration version so runMigrations does not replay migrations
    // whose DDL we just copied. db.ts rebuilds the FTS index explicitly after a
    // recovery instead of relying on migration v2 re-running.
    try {
      const row = src.prepare('PRAGMA user_version').get() as { user_version?: number } | null
      const v = row?.user_version
      if (typeof v === 'number' && Number.isInteger(v) && v >= 0) {
        dest.exec(`PRAGMA user_version = ${v}`)
      }
    } catch {
      // Leave the fresh DB at 0; migrations are idempotent and will replay.
    }

    return result
  } catch {
    return EMPTY_SALVAGE
  } finally {
    closeQuietly(src)
    closeQuietly(dest)
  }
}

// --- Suspected-corruption flag (the runtime trip) ---------------------------
//
// WHY THIS EXISTS. The open+sanity detector above only ever fires on SCHEMA-page
// damage — and that same damage makes sqlite_master unreadable, so salvage gets
// nothing and every such recovery is a wipe. The corruption that actually costs
// the user data is a damaged DATA page: open succeeds, the sanity query succeeds,
// most tables read perfectly, and only the damaged table throws SQLITE_CORRUPT at
// runtime, forever, silently. (Measured — see the module header and the tests.)
//
// So a corrupt error raised by ANY live query trips a persisted flag, and the
// repair runs at the NEXT startup, where it is safe: single-threaded, before the
// read-only handle and the KG worker's own connection exist. This is what makes
// the salvage engine reachable at all.
//
// macOS designed exactly this (RewindDatabase.reportQueryError counts consecutive
// corrupt/IOERR errors and closes the DB at maxQueryIOErrorsBeforeRecovery so the
// next initialize() recovers) — and then never called it from anywhere. This
// finishes that intent rather than inheriting the dead end.

const FLAG_SUSPECTED = 'db_corruption_suspected'
const FLAG_ATTEMPTS = 'db_repair_attempts'

/** Give up rebuilding after this many attempts and leave the database alone. A
 *  repair that keeps failing must not rebuild the DB on every launch forever. */
export const MAX_REPAIR_ATTEMPTS = 3

function readMeta(db: RecoveryDb, key: string): string | null {
  try {
    const row = db
      .prepare('SELECT value FROM app_meta WHERE key = ?')
      .get(...([key] as never[])) as { value: string | null } | undefined
    return row?.value ?? null
  } catch {
    // app_meta may not exist yet (brand-new DB) or may be unreadable.
    return null
  }
}

function writeMeta(db: RecoveryDb, key: string, value: string): boolean {
  try {
    db.exec('CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)')
    db.prepare('INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)').run(
      ...([key, value] as never[])
    )
    return true
  } catch {
    // The DB is too damaged to even record the suspicion. Nothing more we can do
    // here — schema-level damage is caught by the startup detector anyway.
    return false
  }
}

/** Record that a live query raised a corrupt error, so the next launch repairs.
 *  Returns false if the suspicion could not be persisted. */
export function markCorruptionSuspected(db: RecoveryDb): boolean {
  return writeMeta(db, FLAG_SUSPECTED, '1')
}

export function isCorruptionSuspected(db: RecoveryDb): boolean {
  return readMeta(db, FLAG_SUSPECTED) === '1'
}

function clearSuspicion(db: RecoveryDb): void {
  try {
    db.prepare('DELETE FROM app_meta WHERE key IN (?, ?)').run(
      ...([FLAG_SUSPECTED, FLAG_ATTEMPTS] as never[])
    )
  } catch {
    // Best-effort.
  }
}

function repairAttempts(db: RecoveryDb): number {
  const n = Number(readMeta(db, FLAG_ATTEMPTS) ?? '0')
  return Number.isFinite(n) && n > 0 ? n : 0
}

// --- Re-verification (the flag is a suspicion, never a verdict) --------------

export type TableProbe = {
  /** Rows the app can actually READ from each table right now. A table whose full
   *  read throws serves nothing, so it counts as 0. */
  readable: Record<string, number>
  /** Tables whose full read raises a corrupt error. */
  damaged: string[]
}

/**
 * Read every table to find out what is ACTUALLY broken, right now. This is the
 * re-verification gate: the persisted flag says "a query threw once", which could
 * have been a transient or misclassified error. Nothing destructive happens until
 * this proves the corruption still reproduces.
 */
export function probeTables(db: RecoveryDb): TableProbe {
  const probe: TableProbe = { readable: {}, damaged: [] }
  let names: string[]
  try {
    const rows = db
      .prepare(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"
      )
      .all() as { name: string; sql: string | null }[]
    // Ignore exactly what salvage ignores: FTS virtual tables and their shadow
    // tables. They are a derived index, rebuilt from the recovered content — if we
    // counted their rows as "readable", the never-worse guard would see salvage
    // "losing" them and would veto every legitimate repair.
    const virtualNames = rows.filter((r) => r.sql && isVirtual(r.sql)).map((r) => r.name)
    const isDerived = (name: string): boolean =>
      virtualNames.includes(name) ||
      virtualNames.some((v) => FTS_SHADOW_SUFFIXES.some((s) => name === `${v}_${s}`))
    names = rows.filter((r) => !isDerived(r.name)).map((r) => r.name)
  } catch (err) {
    // Even the schema is unreadable — that is corruption of the worst kind.
    if (isCorruptionError(err)) probe.damaged.push('sqlite_master')
    return probe
  }
  for (const name of names) {
    // Same bounded scanner the salvage uses — a table too big to hold in memory
    // must not OOM the repair (see scanTable). `corrupt` is set by the classifier,
    // never by a missing table or a schema quirk.
    const { rows, corrupt } = scanTable(db, name, '*', (batch) => batch.length)
    if (corrupt) {
      probe.damaged.push(name)
      // The app's own queries are unbounded `SELECT`s, and a corrupt page kills the
      // whole scan — so from the app's point of view this table currently serves
      // NOTHING, whatever a page-skipping reader can still scrape out of it. That
      // zero is what the never-worse guard compares against.
      probe.readable[name] = 0
    } else {
      probe.readable[name] = rows
    }
  }
  return probe
}

/**
 * Never rebuild into a worse state. A swap is only allowed if salvage kept at
 * least as many rows as the app can currently read from every table that still
 * reads. Recovering 793/800 rows of a table that currently throws entirely is a
 * win; "recovering" 250 of the 300 rows of a table that reads fine is data loss.
 */
export function salvageIsAnImprovement(probe: TableProbe, salvaged: SalvageResult): boolean {
  if (salvaged.rows <= 0) return false
  for (const [table, currentlyReadable] of Object.entries(probe.readable)) {
    if (currentlyReadable <= 0) continue // nothing to lose on a table we cannot read
    if ((salvaged.tables[table] ?? 0) < currentlyReadable) return false
  }
  return true
}

export type RepairOutcome =
  /** The flag was a false alarm: nothing is damaged now. Flag cleared, DB untouched. */
  | { action: 'no_repair_needed' }
  /** Too many failed attempts — stop rebuilding, leave the DB alone, report. */
  | { action: 'abandoned'; attempts: number; damaged: string[] }
  /** Salvage would have lost rows a working table still serves. Original kept. */
  | { action: 'kept_original'; damaged: string[]; backupPath: string | null }
  /** Repaired: the salvaged database replaced the damaged one. */
  | { action: 'repaired'; status: RecoveryStatus; damaged: string[] }

/**
 * The next-launch repair for a database flagged by the runtime trip. Called with
 * an already-open handle at startup, before any other connection exists.
 *
 * The ORDER is the whole safety argument:
 *   1. Boot-loop guard — give up after MAX_REPAIR_ATTEMPTS rather than rebuild forever.
 *   2. Burn an attempt FIRST, before reading a single damaged page. Everything
 *      below can crash the process (a corrupt page can take the native driver down,
 *      and a huge table can exhaust memory); if the counter were written later, such
 *      a crash would cost nothing and the repair would re-run on every launch, for
 *      ever. It is written to the ORIGINAL database, which is still the live file.
 *   3. Re-verify — the flag is only a suspicion. Prove the damage still reproduces.
 *   4. Salvage from a STAGING COPY, and decide whether the result is actually better
 *      than what the database serves today. Nothing has been touched yet, so
 *      "no, it isn't" costs a temp file and nothing else.
 *   5. Only then, ONE destructive step: MOVE the original into the backups directory
 *      (atomic — never copy-then-delete) and rename the salvaged file into its place.
 *
 * The caller closes `db` on every path except no_repair_needed / abandoned.
 */
export function repairSuspectedCorruption(
  db: RecoveryDb,
  file: string,
  driver: RecoveryDriver,
  opts: { backupsDir: string; hooks?: RecoveryHooks; now?: () => Date }
): RepairOutcome {
  const log = opts.hooks?.log ?? ((): void => {})
  const now = opts.now?.() ?? new Date()

  const attempts = repairAttempts(db)
  if (attempts >= MAX_REPAIR_ATTEMPTS) {
    log(`db: repair abandoned after ${attempts} attempts — leaving the database alone`)
    return { action: 'abandoned', attempts, damaged: probeTables(db).damaged }
  }
  // (2) Burn the attempt before we read anything damaged. See the doc comment.
  writeMeta(db, FLAG_ATTEMPTS, String(attempts + 1))

  const probe = probeTables(db)
  if (probe.damaged.length === 0) {
    // Transient or misclassified: everything reads clean now. Do NOT rebuild.
    log('db: corruption suspicion did not reproduce — clearing the flag, no repair')
    clearSuspicion(db) // also drops the attempt counter we just wrote
    return { action: 'no_repair_needed' }
  }
  log(`db: corruption re-verified in: ${probe.damaged.join(', ')}`)
  opts.hooks?.onCorruption?.(
    new Error(`database corruption confirmed in: ${probe.damaged.join(', ')}`),
    'sanity'
  )
  db.close()

  const tmp = `${file}${SALVAGE_TMP_INFIX}${now.getTime()}`
  const staging = `${file}.recover-src-${now.getTime()}`
  const cleanup = (): void => {
    forceRemove(tmp)
    forceRemove(staging)
    for (const s of SIDECARS) forceRemove(`${staging}${s}`)
  }

  try {
    // (4) Salvage reads a STAGING COPY, never the live file: opening the original
    // read-only re-creates its -wal/-shm, and Windows then refuses to unlink those
    // during the swap (EBUSY), failing the whole repair. The copy carries the
    // sidecars with it so any content still living in an un-checkpointed WAL is
    // salvaged too. A copy is safe HERE precisely because it is not a backup —
    // nothing is deleted on the strength of it.
    cleanup()
    if (!stageCopy(file, staging)) {
      log('db: could not stage a copy of the database — keeping the original untouched')
      cleanup()
      return { action: 'kept_original', damaged: probe.damaged, backupPath: null }
    }
    const salvaged = salvage(staging, tmp, driver)
    log(
      `db: salvage recovered ${salvaged.rows} row(s) from ${Object.keys(salvaged.tables).length} table(s)`
    )

    if (!salvageIsAnImprovement(probe, salvaged)) {
      // Rebuilding would cost the user rows a working table still serves. Keep the
      // original untouched; the damaged table stays broken, but nothing else is lost.
      log('db: salvage would not improve on the current database — keeping the original')
      cleanup()
      return { action: 'kept_original', damaged: probe.damaged, backupPath: null }
    }

    // (5) The single destructive step, and it is a MOVE. If it throws, the original
    // is still exactly where it was and we have changed nothing.
    let backupPath: string
    try {
      backupPath = archiveCorruptDb(file, opts.backupsDir, now)
    } catch (e) {
      log(
        `db: could not move the corrupt database aside (${(e as Error)?.message}) — ` +
          'keeping the original untouched'
      )
      cleanup()
      return { action: 'kept_original', damaged: probe.damaged, backupPath: null }
    }
    log(`db: corrupt database archived to ${backupPath}`)
    archiveSidecars(file, backupPath)
    forceRename(tmp, file)

    return {
      action: 'repaired',
      damaged: probe.damaged,
      status: {
        recovered: true,
        reset: false,
        rowsRecovered: salvaged.rows,
        tablesRecovered: salvaged.tables,
        backupPath
      }
    }
  } finally {
    forceRemove(staging)
    for (const s of SIDECARS) forceRemove(`${staging}${s}`)
  }
}

/** Copy `file` (and any live sidecars) to `staging`, and prove the copy is whole.
 *  A short copy would under-salvage, so a size mismatch fails it outright. */
function stageCopy(file: string, staging: string): boolean {
  try {
    copyFileSync(file, staging)
    if (statSync(staging).size !== statSync(file).size) return false
    for (const s of SIDECARS) {
      const from = `${file}${s}`
      if (existsSync(from)) copyFileSync(from, `${staging}${s}`)
    }
    return true
  } catch {
    return false
  }
}

/** Clear the suspicion + attempt counter on the freshly repaired database (the
 *  salvage copied app_meta across, flag and all). */
export function clearCorruptionFlags(db: RecoveryDb): void {
  clearSuspicion(db)
}

// --- Open with recovery -----------------------------------------------------

/** One shape, shared with the renderer's recovery notice (shared/types.ts). */
export type RecoveryStatus = DbRecoveryStatus

export const NO_RECOVERY: RecoveryStatus = {
  recovered: false,
  reset: false,
  rowsRecovered: 0,
  tablesRecovered: {},
  backupPath: null
}

export type RecoveryHooks = {
  /** Called once when corruption is confirmed, before anything destructive. */
  onCorruption?: (err: unknown, phase: 'open' | 'sanity') => void
  log?: (message: string) => void
}

function closeQuietly(db: RecoveryDb | null): void {
  try {
    db?.close()
  } catch {
    // Already closed / never opened.
  }
}

/** Synchronous backoff. This runs at startup, before any window exists, on a path
 *  that fires once in a database's lifetime. */
function sleep(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

/**
 * Delete a file, tolerating Windows's EBUSY.
 *
 * On Windows a file cannot be unlinked while any handle is open, and SQLite's
 * close is not always instantaneous about releasing the -wal/-shm (a failed
 * checkpoint on a corrupt DB can leave them held for a moment). A bare rmSync
 * therefore throws EBUSY and takes the whole repair down with it — which is
 * exactly what the e2e caught: the swap failed, get() threw, and the repair
 * re-ran on every call. Retry briefly, then give up loudly.
 *
 * Only ever called on files WE created (staging copies, salvage temporaries) or on
 * sidecars whose database has already been archived. The user's database itself is
 * never deleted — it is moved (archiveCorruptDb).
 */
function forceRemove(file: string, attempts = 10): void {
  for (let i = 0; ; i++) {
    try {
      rmSync(file, { force: true })
      return
    } catch (err) {
      if (i >= attempts - 1) throw err
      sleep(50)
    }
  }
}

const SIDECARS = ['-wal', '-shm', '-journal'] as const

/**
 * Move the live database's sidecars out of the way, keeping the bytes.
 *
 * A stale `-journal` next to a fresh database is not inert — SQLite treats a hot
 * journal as something to roll back INTO the database — so the sidecars cannot
 * simply be left behind. But they can hold committed pages that never made it into
 * the main file, so they are not thrown away either: they are renamed to a
 * stash, and the caller decides what becomes of them.
 */
function stashSidecars(file: string, tag: string): string[] {
  const stashed: string[] = []
  for (const suffix of SIDECARS) {
    const from = `${file}${suffix}`
    if (!existsSync(from)) continue
    const to = `${from}.stash-${tag}`
    try {
      forceRemove(to)
      forceRename(from, to)
      stashed.push(to)
    } catch {
      // Could not move it. Removing it is the only way the database opens at all.
      try {
        forceRemove(from)
      } catch {
        // Nothing else to try; the open below will fail and report.
      }
    }
  }
  return stashed
}

/** Park stashed sidecars next to the archived database, for forensics.
 *
 *  Deliberately NOT named `<archive>-wal`: the archive is a corrupt database and
 *  the salvage opens it read-only, so a file SQLite would auto-attach as its WAL
 *  would be replayed into the very read we are trying to get data out of. The
 *  `.orphaned` suffix keeps the bytes without making them live. */
function parkStash(stashed: string[], archivePath: string): void {
  for (const from of stashed) {
    const suffix = SIDECARS.find((s) => from.includes(`${s}.stash-`)) ?? '-sidecar'
    try {
      forceRename(from, `${archivePath}${suffix}.orphaned`)
    } catch {
      // Best-effort forensics; never fail a recovery over it.
    }
  }
}

/** Move the live sidecars of `file` next to its archive. Used after the database
 *  itself has been archived, so `<archive>-wal` IS the archive's real WAL here and
 *  keeping the name makes the archived pair openable. */
function archiveSidecars(file: string, archivePath: string): void {
  for (const suffix of SIDECARS) {
    const from = `${file}${suffix}`
    if (!existsSync(from)) continue
    try {
      forceRename(from, `${archivePath}${suffix}`)
    } catch {
      try {
        forceRemove(from)
      } catch {
        // A sidecar we can neither move nor delete would be applied to the
        // replacement database. Nothing left to try; surface it.
        throw new Error(`could not clear ${from} — the replacement database is not safe to install`)
      }
    }
  }
}

function discardStash(stashed: string[]): void {
  for (const f of stashed) {
    try {
      forceRemove(f)
    } catch {
      // Leftover junk in userData; harmless (SQLite never looks at `.stash-*`).
    }
  }
}

const SALVAGE_TMP_INFIX = '.salvage-'

/**
 * Recover from a repair that was interrupted mid-swap.
 *
 * The Windows swap is unavoidably two steps — archive the original away (a MOVE, so
 * the original is already safe in backups/), then rename the salvaged temp into its
 * place — because Windows cannot atomically replace an open database file. If the
 * process dies BETWEEN them (power loss is this feature's whole threat model), the
 * database path is empty and the salvaged data is stranded at `omi.db.salvage-<ts>`.
 * Left alone, the next open would create a fresh empty database and silently orphan
 * every recovered row.
 *
 * So: if the database is missing (or a zero-byte stub) and a salvage temp is sitting
 * right there, complete the interrupted swap by moving it into place. Picks the
 * newest by name (the timestamp suffix sorts chronologically). If the adopted file
 * turns out to be a partial write, the normal open+recovery path below handles it —
 * and the true original is still in backups/ regardless.
 */
function adoptInterruptedSalvage(file: string, log: (m: string) => void): void {
  try {
    if (existsSync(file) && statSync(file).size > 0) return // a real database is present
    const dir = dirname(file)
    const prefix = `${basename(file)}${SALVAGE_TMP_INFIX}`
    if (!existsSync(dir)) return
    const temps = readdirSync(dir)
      .filter((n) => n.startsWith(prefix))
      .sort() // timestamp suffix → chronological
    const newest = temps[temps.length - 1]
    if (!newest) return
    // Any older salvage temps are leftovers from a superseded attempt — discard them.
    for (const stale of temps.slice(0, -1)) forceRemove(join(dir, stale))
    if (existsSync(file)) forceRemove(file) // clear the zero-byte stub, if any
    forceRename(join(dir, newest), file)
    log(`db: completed an interrupted repair — adopted salvaged ${newest}`)
  } catch (e) {
    // Best-effort: a failure here just falls through to the normal open path, and
    // the real original is safe in backups/. Never let it break startup.
    log(`db: could not adopt an interrupted salvage (${(e as Error)?.message})`)
  }
}

/** Open + prove the connection can actually read the schema. macOS's real sanity
 *  query — cheap (schema is already in memory) unlike `quick_check`. */
function openChecked(file: string, driver: RecoveryDriver): RecoveryDb {
  const db = driver.open(file)
  try {
    db.prepare('SELECT count(*) AS n FROM sqlite_master').get()
    return db
  } catch (err) {
    closeQuietly(db)
    throw err
  }
}

/**
 * Open `file`, recovering it if — and only if — SQLite says it is corrupt.
 *
 * Safety contract (the reason this function is shaped the way it is):
 *   - An access error (locked / busy / no permission / disk full) is rethrown
 *     untouched. We never delete a WAL or replace a file we merely failed to open.
 *   - An unclassified error is rethrown after at most a WAL-removal retry. The
 *     destructive path (backup → salvage → replace) requires a POSITIVE
 *     corruption verdict, because a false positive would destroy a healthy DB.
 *   - A missing file is not corruption: SQLite creates it and the sanity query
 *     passes on the empty schema.
 */
export function openDatabaseWithRecovery(
  file: string,
  driver: RecoveryDriver,
  opts: { backupsDir?: string; hooks?: RecoveryHooks; now?: () => Date } = {}
): { db: RecoveryDb; status: RecoveryStatus } {
  const hooks = opts.hooks ?? {}
  const backupsDir = opts.backupsDir ?? join(dirname(file), 'backups')
  const log = hooks.log ?? ((): void => {})

  const now = opts.now?.() ?? new Date()

  // Crash-recovery for the repair's own non-atomic swap. Windows cannot atomically
  // replace an open database, so repairSuspectedCorruption archives the original
  // (a MOVE — original now safe in backups/) and THEN renames the salvaged temp
  // into place. A process death in that microsecond gap leaves `file` missing and
  // the salvaged data stranded at `omi.db.salvage-*`. Without this, the next launch
  // would create a fresh EMPTY database and silently orphan the recovered rows.
  // Adopt the stranded salvage instead — the repair's result is not lost to a crash.
  adoptInterruptedSalvage(file, log)

  let firstErr: unknown
  try {
    return { db: openChecked(file, driver), status: NO_RECOVERY }
  } catch (err) {
    if (isAccessError(err)) throw err
    firstErr = err
  }

  // macOS's first move: a bad/orphaned WAL is the common cause of an unopenable
  // database, so take the sidecars out of the picture and try once more before
  // concluding anything. They are STASHED, not deleted — if this turns out to be
  // corruption, they are parked alongside the archived database rather than lost.
  log(`db: open failed (${(firstErr as Error)?.message}); setting the WAL aside and retrying once`)
  const stashed = stashSidecars(file, String(now.getTime()))
  try {
    const db = openChecked(file, driver)
    log('db: recovered by removing a stale WAL — no corruption')
    // The database opened clean without them: SQLite itself rejected those bytes.
    discardStash(stashed)
    return { db, status: NO_RECOVERY }
  } catch (secondErr) {
    if (isAccessError(secondErr)) {
      discardStash(stashed)
      throw secondErr
    }
    if (!isCorruptionError(secondErr) && !isCorruptionError(firstErr)) {
      discardStash(stashed)
      throw secondErr
    }

    const phase: 'open' | 'sanity' = 'open'
    hooks.onCorruption?.(secondErr, phase)
    return recover(file, driver, backupsDir, log, now, stashed)
  }
}

/**
 * Archive → salvage → install. Only ever called with a positive corruption verdict,
 * on a database that cannot be opened at all: its schema page is unreadable, so the
 * app can currently read ZERO rows from it and any outcome is an improvement.
 *
 * The corrupt file is MOVED into the backups directory, not copied-then-deleted. If
 * it cannot be moved, the corruption error is rethrown and nothing is destroyed —
 * the app then boots without a database (initDatabase's throw is non-fatal) rather
 * than boot with an empty one over the user's shredded data.
 */
function recover(
  file: string,
  driver: RecoveryDriver,
  backupsDir: string,
  log: (m: string) => void,
  now: Date,
  stashed: string[]
): { db: RecoveryDb; status: RecoveryStatus } {
  const backupPath = archiveCorruptDb(file, backupsDir, now)
  log(`db: corrupt database archived to ${backupPath}`)
  parkStash(stashed, backupPath)

  const tmp = `${file}${SALVAGE_TMP_INFIX}${now.getTime()}`
  forceRemove(tmp)
  const salvaged = salvage(backupPath, tmp, driver)
  log(
    `db: salvaged ${salvaged.rows} row(s) from ${Object.keys(salvaged.tables).length} table(s)` +
      (salvaged.skipped.length ? `; skipped ${salvaged.skipped.join(', ')}` : '')
  )

  const useSalvaged = salvaged.rows > 0
  if (useSalvaged) {
    forceRename(tmp, file) // `file` no longer exists — it was moved to the archive
  } else {
    forceRemove(tmp) // nothing salvageable; openChecked creates a fresh database
  }

  const status: RecoveryStatus = {
    recovered: true,
    reset: !useSalvaged,
    rowsRecovered: salvaged.rows,
    tablesRecovered: salvaged.tables,
    backupPath
  }

  try {
    // The salvaged file (or a fresh empty one) must open cleanly. db.ts's
    // bootstrap recreates anything salvage skipped.
    return { db: openChecked(file, driver), status }
  } catch (err) {
    if (!useSalvaged) throw err // a brand-new empty DB that won't open: unrecoverable
    // The salvaged copy is itself unusable. Deleting it is safe — it is OUR file,
    // and the user's original is already archived — so fall back to a clean reset
    // rather than leave the user with an app that cannot start.
    log(`db: salvaged database failed to open (${(err as Error)?.message}); resetting instead`)
    forceRemove(file)
    for (const s of SIDECARS) forceRemove(`${file}${s}`)
    return {
      db: openChecked(file, driver),
      status: { ...status, reset: true, rowsRecovered: 0, tablesRecovered: {} }
    }
  }
}
