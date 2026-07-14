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
 */
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, renameSync } from 'fs'
import { dirname, join } from 'path'

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
const CORRUPT_PRIMARY_CODES = new Set([11, 26])
// Extended codes whose primary code is NOT itself corruption. 6922 =
// SQLITE_IOERR_CORRUPTFS (primary 10 = SQLITE_IOERR), which macOS matches by name.
const CORRUPT_EXTENDED_CODES = new Set([6922])

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
  // An access/lock/disk error is never corruption, whatever else it looks like.
  if (isAccessError(err)) return false
  if (typeof e.code === 'string') {
    const code = e.code.toUpperCase()
    if (code.startsWith('SQLITE_CORRUPT') || code.startsWith('SQLITE_NOTADB')) return true
    if (code === 'SQLITE_IOERR_CORRUPTFS') return true
  }
  if (typeof e.errcode === 'number') {
    if (CORRUPT_EXTENDED_CODES.has(e.errcode)) return true
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

// --- Backups ----------------------------------------------------------------

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

/** Copy the corrupt file to `<backupsDir>/omi_corrupted_<yyyyMMdd_HHmmss>.db`,
 *  then prune to the 5 newest. Returns the backup path. */
export function backupCorruptDb(dbFile: string, backupsDir: string, now = new Date()): string {
  mkdirSync(backupsDir, { recursive: true })
  const base = `${BACKUP_PREFIX}${stamp(now)}`
  // Two corruptions inside one second would otherwise overwrite the older backup.
  let dest = join(backupsDir, `${base}.db`)
  for (let i = 1; existsSync(dest); i++) dest = join(backupsDir, `${base}_${i}.db`)
  copyFileSync(dbFile, dest)
  pruneBackups(backupsDir)
  return dest
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
    .prepare("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\'")
    .all() as MasterRow[]
  return rows.filter((r) => typeof r.sql === 'string' && typeof r.name === 'string')
}

/** Column names of `table` as created in the destination DB. */
function columnsOf(db: RecoveryDb, table: string): string[] {
  const cols = db.prepare(`PRAGMA table_info(${quote(table)})`).all() as { name: string }[]
  return cols.map((c) => c.name)
}

// A per-row scan of a damaged table walks the rowid space, so cap the work: a
// pathological max(rowid) must not hang startup. 250k probes is far more than any
// real omi.db table and completes in seconds.
const MAX_ROW_PROBES = 250_000
const ROW_WINDOW = 256

/**
 * Copy every readable row of one table. Fast path is a single `SELECT`; if that
 * throws (a corrupt page anywhere in the table kills the whole scan) we fall back
 * to a rowid-windowed scan and then to single-row reads, so one bad page costs
 * only the rows on it. Measured on a real corrupted file: 793 of 800 rows
 * recovered from a table whose full scan threw.
 */
function copyTable(src: RecoveryDb, dest: RecoveryDb, table: string): number {
  const cols = columnsOf(dest, table)
  if (cols.length === 0) return 0
  const colList = cols.map(quote).join(', ')
  const insert = dest.prepare(
    `INSERT OR IGNORE INTO ${quote(table)} (${colList}) VALUES (${cols.map(() => '?').join(', ')})`
  )
  const toParams = (row: Record<string, unknown>): unknown[] => cols.map((c) => row[c] ?? null)

  const write = (rows: Record<string, unknown>[]): number => {
    let n = 0
    for (const row of rows) {
      try {
        insert.run(...(toParams(row) as never[]))
        n++
      } catch {
        // A single row that won't bind (bad blob, constraint) must not stop the rest.
      }
    }
    return n
  }

  // Fast path — whole table in one read.
  try {
    const rows = src.prepare(`SELECT ${colList} FROM ${quote(table)}`).all() as Record<
      string,
      unknown
    >[]
    return write(rows)
  } catch {
    // Damaged page somewhere in this table — fall through to the resilient scan.
  }

  let max = 0
  try {
    const row = src.prepare(`SELECT MAX(rowid) AS m FROM ${quote(table)}`).get() as {
      m: number | null
    } | null
    max = row?.m ?? 0
  } catch {
    // Can't even read the rowid range — the table is a total loss.
    return 0
  }
  if (max <= 0 || max > MAX_ROW_PROBES) return 0

  const windowed = src.prepare(
    `SELECT ${colList} FROM ${quote(table)} WHERE rowid > ? AND rowid <= ?`
  )
  const single = src.prepare(`SELECT ${colList} FROM ${quote(table)} WHERE rowid = ?`)
  let copied = 0
  for (let lo = 0; lo < max; lo += ROW_WINDOW) {
    const hi = Math.min(lo + ROW_WINDOW, max)
    try {
      copied += write(windowed.all(...([lo, hi] as never[])) as Record<string, unknown>[])
    } catch {
      // This window straddles the bad page — recover it row by row.
      for (let id = lo + 1; id <= hi; id++) {
        try {
          const row = single.get(...([id] as never[])) as Record<string, unknown> | undefined
          if (row) copied += write([row])
        } catch {
          // This row lives on the corrupt page. Skip it, keep the rest.
        }
      }
    }
  }
  return copied
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

    const tables = master.filter((r) => r.type === 'table').filter((r) => {
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

// --- Open with recovery -----------------------------------------------------

export type RecoveryStatus = {
  /** Corruption was detected and handled on this launch. */
  recovered: boolean
  /** Nothing was salvageable — the database was reset to an empty schema. */
  reset: boolean
  rowsRecovered: number
  tablesRecovered: Record<string, number>
  backupPath: string | null
}

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

function removeSidecars(file: string): void {
  for (const suffix of ['-wal', '-shm', '-journal']) rmSync(`${file}${suffix}`, { force: true })
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

  let firstErr: unknown
  try {
    return { db: openChecked(file, driver), status: NO_RECOVERY }
  } catch (err) {
    if (isAccessError(err)) throw err
    firstErr = err
  }

  // macOS's first move: a bad/orphaned WAL is the common cause of an unopenable
  // database, so drop the sidecars and try once more before concluding anything.
  log(`db: open failed (${(firstErr as Error)?.message}); removing WAL and retrying once`)
  removeSidecars(file)
  try {
    const db = openChecked(file, driver)
    log('db: recovered by removing a stale WAL — no corruption')
    return { db, status: NO_RECOVERY }
  } catch (secondErr) {
    if (isAccessError(secondErr)) throw secondErr
    if (!isCorruptionError(secondErr) && !isCorruptionError(firstErr)) throw secondErr

    const phase: 'open' | 'sanity' = 'open'
    hooks.onCorruption?.(secondErr, phase)
    return recover(file, driver, backupsDir, log, opts.now?.() ?? new Date())
  }
}

/** Backup → salvage → swap. Only ever called with a positive corruption verdict. */
function recover(
  file: string,
  driver: RecoveryDriver,
  backupsDir: string,
  log: (m: string) => void,
  now: Date
): { db: RecoveryDb; status: RecoveryStatus } {
  let backupPath: string | null = null
  try {
    backupPath = backupCorruptDb(file, backupsDir, now)
    log(`db: corrupt database backed up to ${backupPath}`)
  } catch (e) {
    // Losing the backup (disk full, permissions) must not strand the user with an
    // app that cannot start — the file is unusable either way. Log loudly, go on.
    log(`db: WARNING could not back up the corrupt database: ${(e as Error)?.message}`)
  }

  const tmp = `${file}.salvage-${now.getTime()}`
  rmSync(tmp, { force: true })
  const salvaged = salvage(file, tmp, driver)
  log(
    `db: salvaged ${salvaged.rows} row(s) from ${Object.keys(salvaged.tables).length} table(s)` +
      (salvaged.skipped.length ? `; skipped ${salvaged.skipped.join(', ')}` : '')
  )

  removeSidecars(file)
  rmSync(file, { force: true })

  const useSalvaged = salvaged.rows > 0
  if (useSalvaged) {
    renameSync(tmp, file)
  } else {
    rmSync(tmp, { force: true })
  }
  removeSidecars(file)

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
    // The salvaged copy is itself unusable — fall back to a clean reset rather
    // than leaving the user with an app that cannot start.
    log(`db: salvaged database failed to open (${(err as Error)?.message}); resetting instead`)
    removeSidecars(file)
    rmSync(file, { force: true })
    return {
      db: openChecked(file, driver),
      status: { ...status, reset: true, rowsRecovered: 0, tablesRecovered: {} }
    }
  }
}
