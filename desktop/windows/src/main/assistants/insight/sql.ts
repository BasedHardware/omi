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

function stripForScan(sql: string): string {
  return sql
    .replace(/--.*$/gm, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .trim()
    .toLowerCase()
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
