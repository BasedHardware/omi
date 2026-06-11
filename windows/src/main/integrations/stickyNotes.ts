import Database from 'better-sqlite3'
import { app } from 'electron'
import { copyFileSync, existsSync, readdirSync, rmSync, statSync } from 'fs'
import { join } from 'path'
import { resolveStickyNotesDb } from './stickyNotesPath'
import { toStickyNotes, type RawNoteRow } from './stickyNotesText'
import type { StickyNotesReadResult } from '../../shared/types'

// List subdirectories of `packages` newest-mtime first, so resolveStickyNotesDb
// picks the most recently used Sticky Notes install when several exist.
function listPackageDirsNewestFirst(packages: string): string[] {
  try {
    return readdirSync(packages, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => {
        let mtime = 0
        try {
          mtime = statSync(join(packages, e.name)).mtimeMs
        } catch {
          /* ignore */
        }
        return { name: e.name, mtime }
      })
      .sort((a, b) => b.mtime - a.mtime)
      .map((e) => e.name)
  } catch {
    return []
  }
}

// .NET DateTime ticks at the Unix epoch (100ns intervals since 0001-01-01).
const DOTNET_TICKS_AT_UNIX_EPOCH = 621355968000000000
// Anything past this many ms epoch is well beyond any real note date (year
// ~5138), so a larger number must be .NET ticks rather than ms.
const MS_EPOCH_SANITY_MAX = 1e14

// Coerce a Sticky Notes timestamp to ms epoch. Newer Sticky Notes stores
// CreatedAt/UpdatedAt as .NET DateTime ticks (e.g. 638986500693000925); older
// data / other columns may be ISO strings or already-ms numbers.
function coerceMs(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v)) {
    if (v > MS_EPOCH_SANITY_MAX) return Math.round((v - DOTNET_TICKS_AT_UNIX_EPOCH) / 10000)
    return v
  }
  if (typeof v === 'string') {
    const t = Date.parse(v)
    if (!Number.isNaN(t)) return t
  }
  return 0
}

// Quote a SQLite identifier for safe interpolation (column names come from
// PRAGMA table_info, not user input, but we quote defensively).
function quoteIdent(id: string): string {
  return '"' + id.replace(/"/g, '""') + '"'
}

// Read the Note table from an already-openable db file. Introspects columns so
// it tolerates Sticky Notes schema drift across versions.
function readNoteRows(dbPath: string): RawNoteRow[] {
  const db = new Database(dbPath, { readonly: true, fileMustExist: true })
  try {
    const hasNote = db
      .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='Note'")
      .get()
    if (!hasNote) return []

    const cols = db.prepare('PRAGMA table_info(Note)').all() as { name: string }[]
    const names = cols.map((c) => c.name)
    const textCol = names.find((c) => c === 'Text') ?? names.find((c) => /text/i.test(c))
    if (!textCol) return []
    const idCol = names.find((c) => c === 'Id') ?? names.find((c) => /^id$/i.test(c))
    const updatedCol =
      names.find((c) => c === 'UpdatedAt') ?? names.find((c) => /updat/i.test(c))
    const deletedCol =
      names.find((c) => /^(IsDeleted|DeletedAt)$/i.test(c)) ?? names.find((c) => /delet/i.test(c))

    const select = [
      `${idCol ? quoteIdent(idCol) : 'rowid'} AS id`,
      `${quoteIdent(textCol)} AS text`,
      `${updatedCol ? quoteIdent(updatedCol) : '0'} AS updatedAt`,
      `${deletedCol ? quoteIdent(deletedCol) : 'NULL'} AS deleted`
    ].join(', ')

    const rows = db.prepare(`SELECT ${select} FROM Note`).all() as {
      id: unknown
      text: unknown
      updatedAt: unknown
      deleted: unknown
    }[]

    return rows.map((r) => ({
      id: String(r.id),
      text: typeof r.text === 'string' ? r.text : '',
      updatedAt: coerceMs(r.updatedAt),
      // truthy IsDeleted (1) or a non-null DeletedAt both mean deleted
      deleted: r.deleted != null && r.deleted !== 0 && r.deleted !== ''
    }))
  } finally {
    db.close()
  }
}

// Sticky Notes may hold a write lock on plum.sqlite. On a locked open, copy the
// db (and its -wal/-shm sidecars) to a temp dir, read the copy, then clean up.
function readViaTempCopy(dbPath: string): RawNoteRow[] {
  const tmpBase = join(app.getPath('temp'), `omi-sticky-${Date.now()}`)
  const tmpDb = `${tmpBase}.sqlite`
  const copies: string[] = []
  try {
    copyFileSync(dbPath, tmpDb)
    copies.push(tmpDb)
    for (const ext of ['-wal', '-shm']) {
      const side = dbPath + ext
      if (existsSync(side)) {
        const tside = tmpDb + ext
        copyFileSync(side, tside)
        copies.push(tside)
      }
    }
    return readNoteRows(tmpDb)
  } finally {
    for (const f of copies) {
      try {
        rmSync(f, { force: true })
      } catch {
        /* best-effort cleanup */
      }
    }
  }
}

// Locate + read Windows Sticky Notes, returning cleaned notes. Never throws:
// missing install → { available: false }, read failure → { available: true, error }.
export function readStickyNotes(): StickyNotesReadResult {
  const dbPath = resolveStickyNotesDb(
    { LOCALAPPDATA: process.env.LOCALAPPDATA },
    listPackageDirsNewestFirst,
    existsSync
  )
  if (!dbPath) return { available: false, notes: [] }
  try {
    let rows: RawNoteRow[]
    try {
      rows = readNoteRows(dbPath)
    } catch {
      // Likely SQLITE_BUSY / locked — fall back to a temp copy.
      rows = readViaTempCopy(dbPath)
    }
    return { available: true, notes: toStickyNotes(rows) }
  } catch (e) {
    return { available: true, notes: [], error: (e as Error).message }
  }
}
