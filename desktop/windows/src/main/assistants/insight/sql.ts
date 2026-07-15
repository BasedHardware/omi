// The execute_sql / request_screenshot tool backends. The enforcement is Mac's
// shared ChatToolExecutor, distilled to what Insight actually exercises (read-only
// SELECT/WITH only): every layer here runs BEFORE the query reaches the DB.
//
// The impure edges (the DB query, the frame lookup, the JPEG read) are injected,
// so every safety layer — read-only rejection, single-statement, LIMIT 200 auto-
// append, 200-row cap, 500-char-per-cell truncation — is pure and hermetically
// testable with a fake runner.
//
// NEVER log a query, a result cell, or a window title from here — SQL results are
// raw OCR/screen text.
import type { RewindFrame } from '../../../shared/types'

/** Mac's auto-limit + belt-and-suspenders row cap ("Auto-limited to 200 rows"). */
export const MAX_ROWS = 200
/** Mac's per-cell truncation in the payload sent back to Gemini. */
export const CELL_CAP = 500

/** A read query executed against the local DB: column names + row arrays. */
export type QueryRunner = (sql: string) => { columns: string[]; rows: unknown[][] }

/** The ONLY tables execute_sql may read. A deliberate tightening of Mac's shared
 *  executor, which runs against the whole omi.db: Insight only ever needs rewind
 *  frames, and other tables (`local_conversation`, `ai_user_profiles`, the
 *  knowledge graph, …) hold content that must not flow to Gemini. `rewind_frames`
 *  is the frame timeline; `rewind_frames_fts` is its FTS5 mirror (see db.ts). */
const TABLE_ALLOWLIST = new Set(['rewind_frames', 'rewind_frames_fts'])

/** Keywords that end a table reference / its optional alias, so the table-list
 *  parser doesn't swallow a clause keyword as an alias and leaves JOINs for the
 *  outer walk. */
const CLAUSE_KW = new Set([
  'where',
  'group',
  'having',
  'order',
  'limit',
  'offset',
  'join',
  'inner',
  'left',
  'right',
  'full',
  'cross',
  'natural',
  'outer',
  'on',
  'using',
  'union',
  'except',
  'intersect',
  'window',
  'returning'
])

type SqlToken = { t: 'word' | 'ident' | 'str' | 'punct'; v: string }

/** Tokenize just far enough to find table references safely: comments dropped,
 *  single-quoted literals collapsed to an opaque `str`, quoted identifiers
 *  (double-quote, backtick, and `[bracket]`) preserved as `ident` with their
 *  unquoted name — so a forbidden table can't hide behind quoting — barewords as
 *  `word`, and everything else as single-char `punct`. */
function tokenizeSql(sql: string): SqlToken[] {
  const toks: SqlToken[] = []
  const n = sql.length
  for (let i = 0; i < n; ) {
    const c = sql[i]
    if (c === ' ' || c === '\t' || c === '\n' || c === '\r' || c === '\f' || c === '\v') {
      i++
    } else if (c === '-' && sql[i + 1] === '-') {
      i += 2
      while (i < n && sql[i] !== '\n') i++
    } else if (c === '/' && sql[i + 1] === '*') {
      i += 2
      while (i < n && !(sql[i] === '*' && sql[i + 1] === '/')) i++
      i += 2
    } else if (c === "'") {
      i++
      while (i < n) {
        if (sql[i] === "'") {
          if (sql[i + 1] === "'") {
            i += 2
            continue
          }
          i++
          break
        }
        i++
      }
      toks.push({ t: 'str', v: '' })
    } else if (c === '"' || c === '`') {
      const q = c
      i++
      let v = ''
      while (i < n) {
        if (sql[i] === q) {
          if (sql[i + 1] === q) {
            v += q
            i += 2
            continue
          }
          i++
          break
        }
        v += sql[i]
        i++
      }
      toks.push({ t: 'ident', v: v.toLowerCase() })
    } else if (c === '[') {
      i++
      let v = ''
      while (i < n && sql[i] !== ']') {
        v += sql[i]
        i++
      }
      i++
      toks.push({ t: 'ident', v: v.toLowerCase() })
    } else if (/[A-Za-z_]/.test(c)) {
      let v = ''
      while (i < n && /[A-Za-z0-9_$]/.test(sql[i])) {
        v += sql[i]
        i++
      }
      toks.push({ t: 'word', v: v.toLowerCase() })
    } else {
      toks.push({ t: 'punct', v: c })
      i++
    }
  }
  return toks
}

/** Every table named in a FROM/JOIN position, plus the relation names bound by a
 *  CTE / derived table (`name AS ( … )`) which are NOT real tables (their bodies
 *  are subqueries scanned on their own). `ok` is false when a table slot held
 *  something this parser can't classify (e.g. a token where a table name was
 *  expected) — the caller then fails closed. */
function collectTables(toks: SqlToken[]): { tables: string[]; bound: Set<string>; ok: boolean } {
  const bound = new Set<string>()
  for (let i = 0; i + 2 < toks.length; i++) {
    const a = toks[i]
    if (
      (a.t === 'word' || a.t === 'ident') &&
      toks[i + 1].t === 'word' &&
      toks[i + 1].v === 'as' &&
      toks[i + 2].t === 'punct' &&
      toks[i + 2].v === '('
    ) {
      bound.add(a.v)
    }
  }

  const tables: string[] = []
  let ok = true
  for (let i = 0; i < toks.length; i++) {
    const kw = toks[i]
    if (kw.t !== 'word' || (kw.v !== 'from' && kw.v !== 'join')) continue
    let j = i + 1
    for (;;) {
      const nx = toks[j]
      if (!nx) break
      if (nx.t === 'punct' && nx.v === '(') break // subquery: its own FROM/JOIN is walked separately
      if (nx.t !== 'word' && nx.t !== 'ident') {
        ok = false // a table name was expected but something else is here — refuse to guess
        break
      }
      let name = nx.v
      const dot = toks[j + 1]
      const after = toks[j + 2]
      if (dot && dot.t === 'punct' && dot.v === '.' && after && (after.t === 'word' || after.t === 'ident')) {
        name = after.v // schema.table → the table part
        j += 2
      }
      tables.push(name)
      j++
      const asTok = toks[j]
      if (asTok && asTok.t === 'word' && asTok.v === 'as') j++
      const alias = toks[j]
      if (alias && (alias.t === 'word' || alias.t === 'ident') && !CLAUSE_KW.has(alias.v)) j++
      if (kw.v === 'join') break // a JOIN references exactly one table
      const comma = toks[j]
      if (comma && comma.t === 'punct' && comma.v === ',') {
        j++
        continue // FROM's comma-separated (implicit-join) table list
      }
      break
    }
  }
  return { tables, bound, ok }
}

/** True iff every table the query reads is in the allowlist. Fail-closed: any
 *  table slot the parser can't confidently classify rejects the whole query. Runs
 *  AFTER the read-only checks — it only narrows *which* tables a valid SELECT may
 *  touch, it never widens what counts as read-only. */
export function tablesAllowed(sql: string): boolean {
  const { tables, bound, ok } = collectTables(tokenizeSql(sql))
  if (!ok) return false
  return tables.every((name) => TABLE_ALLOWLIST.has(name) || bound.has(name))
}

/** Strip everything the keyword blocklist must NOT see so it scans SQL *structure*
 *  only: line/block comments, single-quoted string literals (`''` escapes an
 *  embedded quote), and double-quoted identifiers (`""` escapes one). Each is
 *  replaced by a space so word boundaries survive; the result is lowercased.
 *  Without this, a literal like `'%delete%'` or an identifier `"create"` — both
 *  extremely common in OCR text / window titles — would trip the blocklist and
 *  the query would be wrongly rejected. Mac's `sqlForKeywordScan` strips literals
 *  before scanning for the same reason. A single left-to-right pass (not chained
 *  regexes) so a `--` or `'` *inside* a string can't be mis-parsed as a comment. */
function stripForScan(sql: string): string {
  let out = ''
  const n = sql.length
  for (let i = 0; i < n; ) {
    const c = sql[i]
    if (c === '-' && sql[i + 1] === '-') {
      i += 2
      while (i < n && sql[i] !== '\n') i++
      out += ' '
    } else if (c === '/' && sql[i + 1] === '*') {
      i += 2
      while (i < n && !(sql[i] === '*' && sql[i + 1] === '/')) i++
      i += 2
      out += ' '
    } else if (c === "'") {
      i++
      while (i < n) {
        if (sql[i] === "'") {
          if (sql[i + 1] === "'") {
            i += 2
            continue
          }
          i++
          break
        }
        i++
      }
      out += ' '
    } else if (c === '"') {
      i++
      while (i < n) {
        if (sql[i] === '"') {
          if (sql[i + 1] === '"') {
            i += 2
            continue
          }
          i++
          break
        }
        i++
      }
      out += ' '
    } else {
      out += c
      i++
    }
  }
  return out.trim().toLowerCase()
}

/** Mac's read-only gate: a SELECT/WITH prefix (comments stripped) AND no write or
 *  DDL keyword anywhere as a whole word. A blocklist, not parameterization —
 *  faithful to Mac, which splices the raw query into the statement. */
export function isReadOnlySql(sql: string): boolean {
  const s = stripForScan(sql)
  if (!s) return false
  if (!/^(select|with)\b/.test(s)) return false
  return !/\b(insert|update|delete|replace|drop|alter|create|pragma|attach|detach|vacuum|reindex|truncate)\b/.test(
    s
  )
}

/** Append `LIMIT 200` when the query has no LIMIT of its own (case-insensitive,
 *  after stripping a trailing `;`). Mac's executeSelectQuery behavior. */
export function appendLimit(sql: string, cap: number = MAX_ROWS): string {
  const trimmed = sql.trim().replace(/;+\s*$/, '')
  if (/\blimit\b/i.test(trimmed)) return trimmed
  return `${trimmed} LIMIT ${cap}`
}

function cellToString(v: unknown): string {
  const s = v == null ? '' : String(v)
  return s.length > CELL_CAP ? `${s.slice(0, CELL_CAP)}...` : s
}

/** Mac's pipe-table rendering: header, divider, one line per (capped) row, a
 *  trailing `N row(s)`. Empty set → the literal `No results`. */
export function formatRows(columns: string[], rows: unknown[][]): string {
  if (rows.length === 0) return 'No results'
  const capped = rows.slice(0, MAX_ROWS)
  const divider = '-'.repeat(Math.min(columns.length * 20, 120))
  const lines = [columns.join(' | '), divider]
  for (const row of capped) lines.push(row.map(cellToString).join(' | '))
  lines.push(`${capped.length} row(s)`)
  return lines.join('\n')
}

/**
 * Run one execute_sql tool call. Returns the string that becomes the
 * functionResponse `result` sent back to Gemini — an error string (never a
 * throw) on any rejection, so the tool loop continues rather than aborting.
 */
export function executeSql(rawQuery: unknown, runQuery: QueryRunner): string {
  const query = typeof rawQuery === 'string' ? rawQuery.trim() : ''
  if (!query) return 'Error: empty query'

  // Single statement only (Mac splits on ';' and rejects >1 non-empty).
  const statements = query
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
  if (statements.length > 1) return 'Error: only a single statement is allowed'
  const single = statements[0] ?? query

  if (!isReadOnlySql(single)) return 'Error: only read-only SELECT/WITH queries are allowed'

  // Even a valid read-only SELECT may only touch the rewind frame tables — other
  // tables' contents would flow to Gemini (a deliberate deviation from Mac).
  if (!tablesAllowed(single)) return 'Error: only the rewind_frames table is queryable'

  const limited = appendLimit(single, MAX_ROWS)
  let result: { columns: string[]; rows: unknown[][] }
  try {
    result = runQuery(limited)
  } catch (e) {
    // Message only — a better-sqlite3 error message names columns/syntax, never
    // row contents. Safe to surface to the model; do not log it here.
    return `Error: ${e instanceof Error ? e.message : 'query failed'}`
  }
  return formatRows(result.columns, result.rows)
}

/** request_screenshot backend: resolve a frame id to its JPEG bytes, base64. null
 *  when the id isn't in the DB or its image was swept off disk — Phase 2 aborts.
 *  Windows stores per-frame JPEGs (no Mac video-chunk "still being written" guard
 *  is possible or needed). Deps injected for testability. */
export async function loadScreenshotBase64(
  id: number,
  deps: {
    getFramesByIds: (ids: number[]) => RewindFrame[]
    readImageBase64: (frame: Pick<RewindFrame, 'imagePath'>) => Promise<string | null>
  }
): Promise<string | null> {
  const frames = deps.getFramesByIds([id])
  const frame = frames.find((f) => f.id === id) ?? frames[0]
  if (!frame) return null
  return deps.readImageBase64(frame)
}
