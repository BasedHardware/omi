// The execute_sql / request_screenshot tool backends. The enforcement is Mac's
// shared ChatToolExecutor, distilled to what Insight actually exercises (read-only
// SELECT/WITH only): every layer here runs BEFORE the query reaches the DB.
//
// The impure edges (the DB query, the frame lookup, the JPEG read) are injected,
// so every safety layer — read-only rejection, single-statement, table allowlist,
// the DoS shape guard, the unsuppressible outer-LIMIT wrap, the 200-row cap and
// 500-char-per-cell truncation — is pure and hermetically testable with a fake
// runner.
//
// DoS hardening (a prompt-injected query reaches this backend): the row cap is an
// OUTER `SELECT * FROM (<query>) LIMIT cap+1` wrap the model cannot suppress by
// smuggling the word "limit" into a string literal / alias / inner subquery, and a
// structural guard rejects the two shapes an outer LIMIT can't bound — an unbounded
// recursive CTE and a cartesian join — because better-sqlite3 runs synchronously on
// the Electron main thread with no interrupt/progress-handler API, so a recursive or
// N-way-cross-join query would freeze the whole app. See rejectDangerousShape.
//
// NEVER log a query, a result cell, or a window title from here — SQL results are
// raw OCR/screen text.
import type { RewindFrame } from '../../../shared/types'

/** Mac's auto-limit + belt-and-suspenders row cap ("Auto-limited to 200 rows"). */
export const MAX_ROWS = 200
/** Rows actually fetched: cap + 1, so an (cap+1)th row is proof the result was
 *  truncated (the model is told to narrow it) without materializing more. */
export const ROW_FETCH_CAP = MAX_ROWS + 1
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
function collectTables(toks: SqlToken[]): {
  tables: string[]
  bound: Set<string>
  ok: boolean
  qualified: boolean
} {
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
  let qualified = false
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
      if (
        dot &&
        dot.t === 'punct' &&
        dot.v === '.' &&
        after &&
        (after.t === 'word' || after.t === 'ident')
      ) {
        name = after.v // schema.table → the table part
        qualified = true // a schema-qualified ref (e.g. main.rewind_frames)
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
  return { tables, bound, ok, qualified }
}

/** True iff every table the query reads is in `allowed` (the CTE-bound relation
 *  names are always permitted — their bodies are scanned on their own). Fail-
 *  closed: any table slot the parser can't confidently classify rejects the whole
 *  query. Runs AFTER the read-only checks — it only narrows *which* tables a valid
 *  SELECT may touch, it never widens what counts as read-only.
 *
 *  `rejectQualified` additionally refuses any schema-qualified table reference
 *  (e.g. `main.rewind_frames`). The denylist closure shadows the unqualified
 *  `rewind_frames` with a filtered CTE; a schema-qualified ref would bypass that
 *  CTE and hit the real table, so under a denylist qualified refs are rejected. */
export function tablesAllowed(
  sql: string,
  allowed: ReadonlySet<string> = TABLE_ALLOWLIST,
  rejectQualified = false
): boolean {
  const { tables, bound, ok, qualified } = collectTables(tokenizeSql(sql))
  if (!ok) return false
  if (rejectQualified && qualified) return false
  return tables.every((name) => allowed.has(name) || bound.has(name))
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

/** Wrap the (already validated) query as `SELECT * FROM (<query>) LIMIT cap` so the
 *  row cap ALWAYS applies. This replaces Mac's conditional `LIMIT 200` append, which
 *  was suppressible: the append skipped whenever the raw query contained the word
 *  "limit" anywhere — a `LIKE '%limit%'` literal, a `col AS limit_x` alias, or an
 *  inner subquery's own LIMIT — letting a prompt-injected query run unbounded. An
 *  outer LIMIT on a `SELECT *` over the subquery cannot be suppressed by any inner
 *  "limit" text. A `WITH … SELECT` is a valid parenthesized subquery in SQLite, so
 *  this wrap is valid for every read-only SELECT/WITH the gates above admit. The
 *  trailing `;` is stripped so the wrap stays a single statement. */
export function wrapWithRowCap(sql: string, cap: number = ROW_FETCH_CAP): string {
  const trimmed = sql.trim().replace(/;+\s*$/, '')
  return `SELECT * FROM (${trimmed}) LIMIT ${cap}`
}

/** Index of the `)` that matches the `(` at `openIdx` (which must be a `(` punct
 *  token), or -1 if unbalanced. */
function matchParen(toks: SqlToken[], openIdx: number): number {
  let depth = 0
  for (let k = openIdx; k < toks.length; k++) {
    const t = toks[k]
    if (t.t === 'punct' && t.v === '(') depth++
    else if (t.t === 'punct' && t.v === ')') {
      depth--
      if (depth === 0) return k
    }
  }
  return -1
}

/** True iff a leading `WITH RECURSIVE` defines a CTE that references its own name in
 *  its body but has no `LIMIT` inside that body to bound generation. SQLite only
 *  permits a CTE to reference itself under `RECURSIVE`, so a non-recursive WITH can
 *  never infinite-loop; a recursive CTE whose body carries its own LIMIT terminates.
 *  An unbounded one (e.g. `WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1
 *  FROM r) SELECT max(x) FROM r`) runs forever — and because the aggregate over it
 *  must fully evaluate the recursion, the outer-LIMIT wrap can't stop it. Rejected. */
function hasUnboundedRecursiveCte(toks: SqlToken[]): boolean {
  let i = 0
  if (!(toks[i]?.t === 'word' && toks[i].v === 'with')) return false
  i++
  if (toks[i]?.t === 'word' && toks[i].v === 'recursive') i++
  else return false
  for (;;) {
    const nameTok = toks[i]
    if (!nameTok || (nameTok.t !== 'word' && nameTok.t !== 'ident')) return false
    const name = nameTok.v
    i++
    if (toks[i]?.t === 'punct' && toks[i].v === '(') {
      const close = matchParen(toks, i) // optional column list
      if (close < 0) return false
      i = close + 1
    }
    if (!(toks[i]?.t === 'word' && toks[i].v === 'as')) return false
    i++
    if (!(toks[i]?.t === 'punct' && toks[i].v === '(')) return false
    const bodyClose = matchParen(toks, i)
    if (bodyClose < 0) return false
    const body = toks.slice(i + 1, bodyClose)
    const selfRef = body.some((t) => (t.t === 'word' || t.t === 'ident') && t.v === name)
    const bodyHasLimit = body.some((t) => t.t === 'word' && t.v === 'limit')
    if (selfRef && !bodyHasLimit) return true
    i = bodyClose + 1
    if (toks[i]?.t === 'punct' && toks[i].v === ',') {
      i++
      continue
    }
    return false
  }
}

/** Keywords that end a JOIN's search for an ON/USING predicate. Hitting any of these
 *  (or the end / an enclosing `)`) before a predicate means the JOIN is a cartesian
 *  product. */
const JOIN_BOUNDARY_KW = new Set([
  'where',
  'group',
  'order',
  'limit',
  'having',
  'window',
  'union',
  'except',
  'intersect',
  'returning',
  'join',
  'cross',
  'inner',
  'left',
  'right',
  'full',
  'natural'
])

/** Walk one FROM clause (its keyword at `fromIdx`) and report whether it lists two
 *  real tables separated by a top-level comma (`FROM a, b`) — an implicit cartesian
 *  join. A subquery after the comma (`FROM t, (SELECT …)`) is NOT flagged: it is the
 *  common 1-row scalar-cross idiom and its cardinality is unknowable here. */
function fromHasCommaJoin(toks: SqlToken[], fromIdx: number): boolean {
  let j = fromIdx + 1
  for (;;) {
    const nx = toks[j]
    if (!nx) return false
    if (nx.t === 'punct' && nx.v === '(') {
      const close = matchParen(toks, j) // subquery item
      if (close < 0) return false
      j = close + 1
    } else if (nx.t === 'word' || nx.t === 'ident') {
      j++
      if (
        toks[j]?.t === 'punct' &&
        toks[j].v === '.' &&
        (toks[j + 1]?.t === 'word' || toks[j + 1]?.t === 'ident')
      ) {
        j += 2 // schema.table
      }
    } else {
      return false
    }
    if (toks[j]?.t === 'word' && toks[j].v === 'as') j++
    const alias = toks[j]
    if (alias && (alias.t === 'word' || alias.t === 'ident') && !CLAUSE_KW.has(alias.v)) j++
    const comma = toks[j]
    if (comma && comma.t === 'punct' && comma.v === ',') {
      const after = toks[j + 1]
      if (after && (after.t === 'word' || after.t === 'ident')) return true
      j++ // subquery after comma → keep walking, don't flag
      continue
    }
    return false
  }
}

/** True iff the JOIN keyword at `joinIdx` has no ON/USING predicate before the next
 *  clause boundary — a cartesian product. Depth-tracked so predicates/keywords
 *  inside a joined subquery don't confuse the scan. */
function joinLacksPredicate(toks: SqlToken[], joinIdx: number): boolean {
  let depth = 0
  for (let k = joinIdx + 1; k < toks.length; k++) {
    const t = toks[k]
    if (t.t === 'punct') {
      if (t.v === '(') depth++
      else if (t.v === ')') {
        if (depth === 0) return true
        depth--
      }
      continue
    }
    if (depth !== 0) continue
    if (t.t === 'word') {
      if (t.v === 'on' || t.v === 'using') return false
      if (JOIN_BOUNDARY_KW.has(t.v)) return true
    }
  }
  return true
}

/** True iff the query contains a cartesian product: an implicit comma-join of two
 *  real tables, a CROSS JOIN, or a JOIN with no ON/USING (and not NATURAL). Over
 *  large tables a cartesian is an N² / N³ scan that — combined with an aggregate,
 *  ORDER BY, GROUP BY or DISTINCT the outer LIMIT can't push down — freezes the
 *  synchronous DB call. These joins are never needed on the tool surface (rewind
 *  frames / app usage / tasks / conversations / memories), so they are rejected. */
function hasCartesianJoin(toks: SqlToken[]): boolean {
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i]
    if (t.t !== 'word') continue
    if (t.v === 'cross' && toks[i + 1]?.t === 'word' && toks[i + 1].v === 'join') return true
    if (t.v === 'from' && fromHasCommaJoin(toks, i)) return true
    if (t.v === 'join') {
      const prev = toks[i - 1]
      if (prev?.t === 'word' && (prev.v === 'cross' || prev.v === 'natural')) continue
      if (joinLacksPredicate(toks, i)) return true
    }
  }
  return false
}

/** The DoS shape guard: reject the two unbounded-computation shapes the outer-LIMIT
 *  wrap cannot bound. Runs AFTER the read-only + allowlist gates (so it only ever
 *  fires on an otherwise-valid, allowlisted query — the real DoS vector), and BEFORE
 *  the wrap. Returns an `Error: …` string to reject, or null to allow. */
export function rejectDangerousShape(sql: string): string | null {
  const toks = tokenizeSql(sql)
  if (hasUnboundedRecursiveCte(toks)) {
    return 'Error: recursive queries must bound their recursion with a LIMIT inside the recursive CTE.'
  }
  if (hasCartesianJoin(toks)) {
    return 'Error: cartesian joins are not allowed — add an ON/USING join condition, or query one table at a time.'
  }
  return null
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

/** Render a result set for the model, flagging truncation. The query is fetched with
 *  `LIMIT MAX_ROWS + 1` (ROW_FETCH_CAP), so an (MAX_ROWS+1)th row is proof more rows
 *  exist; formatRows still renders only the first MAX_ROWS, and the note tells the
 *  model to narrow the query rather than silently dropping the tail. */
function renderResult(result: { columns: string[]; rows: unknown[][] }): string {
  const body = formatRows(result.columns, result.rows)
  if (result.rows.length > MAX_ROWS) {
    return `${body}\n(Auto-limited to ${MAX_ROWS} rows — add a LIMIT or a narrower WHERE to see the rest.)`
  }
  return body
}

/** When the user has a non-empty Insight denylist, execute_sql is closed to the
 *  FTS mirror as well: `rewind_frames_fts` is external-content over
 *  `rewind_frames` and exposes `ocr_text`/`window_title`/`app` DIRECTLY (and MATCH
 *  can't be run against a CTE), so it cannot be shadow-filtered like the base
 *  table. Dropping it leaves the base table (now filtered) as the only readable
 *  relation — the model falls back to a LIKE scan, correct if slower. */
const DENYLIST_ALLOWLIST: ReadonlySet<string> = new Set(['rewind_frames'])

/** sql.ts's own copy of the LIKE-metachar escaper (db.ts keeps a sibling copy;
 *  neither layer imports the other). */
function escapeLikeTerm(term: string): string {
  return term.replace(/[\\%_]/g, (c) => `\\${c}`)
}

/** A SQL single-quoted string literal for `raw` (embedded quotes doubled). */
function sqlStringLiteral(raw: string): string {
  return `'${raw.replace(/'/g, "''")}'`
}

/** The WHERE body that keeps only NON-denied frames: for each term, the
 *  concatenated identity columns must NOT contain it (case-insensitive substring,
 *  the SAME predicate as the per-frame gate isUserDeniedApp). Terms are inlined as
 *  escaped literals because the query runner takes only a SQL string (no bound
 *  params). Empty when there are no usable terms (the caller then skips shadowing). */
export function buildDenyFilter(terms: string[]): string {
  const usable = terms.map((t) => t.trim()).filter((t) => t.length > 0)
  if (usable.length === 0) return ''
  return usable
    .map((t) => {
      const literal = sqlStringLiteral(`%${escapeLikeTerm(t)}%`)
      return `(app || ' ' || window_title || ' ' || process_name) NOT LIKE ${literal} ESCAPE '\\'`
    })
    .join(' AND ')
}

/** Skip leading whitespace + comments and report whether the statement begins
 *  with `WITH` (optionally `WITH RECURSIVE`), plus the char offset right after
 *  that keyword (where a new leading CTE is spliced in). */
function scanLeadingWith(sql: string): { isWith: boolean; insertAt: number } {
  const n = sql.length
  let i = 0
  const skip = (): void => {
    for (;;) {
      while (i < n && /\s/.test(sql[i])) i++
      if (sql[i] === '-' && sql[i + 1] === '-') {
        i += 2
        while (i < n && sql[i] !== '\n') i++
        continue
      }
      if (sql[i] === '/' && sql[i + 1] === '*') {
        i += 2
        while (i < n && !(sql[i] === '*' && sql[i + 1] === '/')) i++
        i += 2
        continue
      }
      break
    }
  }
  const word = (): string => {
    let v = ''
    while (i < n && /[A-Za-z_]/.test(sql[i])) {
      v += sql[i]
      i++
    }
    return v
  }
  skip()
  if (word().toLowerCase() !== 'with') return { isWith: false, insertAt: -1 }
  let insertAt = i // right after WITH
  skip()
  const save = i
  if (word().toLowerCase() === 'recursive') insertAt = i
  else i = save
  return { isWith: true, insertAt }
}

/** Shadow the real `rewind_frames` table with a same-named CTE that filters out
 *  denied frames, so every unqualified `rewind_frames` reference in the query —
 *  including `WHERE app='Signal'` — resolves to the filtered relation and can
 *  physically never return a denied row. The CTE body reads the real table via a
 *  SCHEMA-QUALIFIED name (`main.rewind_frames`) so it isn't self-recursive; the
 *  caller has already rejected any user-supplied schema-qualified ref that would
 *  otherwise bypass this CTE. Merges ahead of an existing WITH / WITH RECURSIVE.
 *  A no-op when there are no usable terms. */
export function applyDenylistShadow(sql: string, terms: string[]): string {
  const filter = buildDenyFilter(terms)
  if (!filter) return sql
  const cte = `rewind_frames AS (SELECT * FROM main.rewind_frames WHERE ${filter})`
  const { isWith, insertAt } = scanLeadingWith(sql)
  if (isWith) return `${sql.slice(0, insertAt)} ${cte},${sql.slice(insertAt)}`
  return `WITH ${cte} ${sql}`
}

/**
 * Run one execute_sql tool call. Returns the string that becomes the
 * functionResponse `result` sent back to Gemini — an error string (never a
 * throw) on any rejection, so the tool loop continues rather than aborting.
 *
 * `denylist` (the user's Insight denylist): when non-empty, execute_sql is closed
 * so a denylisted app's rows can NEVER be retrieved — the FTS mirror is dropped
 * from the allowlist, schema-qualified refs are rejected, and every unqualified
 * `rewind_frames` reference is shadowed by a filtered CTE. Empty denylist → the
 * path is byte-for-byte unchanged.
 */
export function executeSql(
  rawQuery: unknown,
  runQuery: QueryRunner,
  denylist: string[] = []
): string {
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

  const denyTerms = denylist.map((t) => t.trim()).filter((t) => t.length > 0)
  const denyActive = denyTerms.length > 0

  // Even a valid read-only SELECT may only touch the rewind frame tables — other
  // tables' contents would flow to Gemini (a deliberate deviation from Mac). Under
  // an active denylist the allowlist tightens to the base table only and schema-
  // qualified refs are rejected (see tablesAllowed / applyDenylistShadow).
  if (!tablesAllowed(single, denyActive ? DENYLIST_ALLOWLIST : TABLE_ALLOWLIST, denyActive))
    return 'Error: only the rewind_frames table is queryable'

  // Reject the unbounded-computation shapes the outer-LIMIT wrap can't bound
  // (recursive-CTE bomb, cartesian join) before any query reaches the DB.
  const dangerous = rejectDangerousShape(single)
  if (dangerous) return dangerous

  // Shadow first (rewrites the user's query), then wrap the whole thing in the
  // unsuppressible outer LIMIT.
  const shaped = denyActive ? applyDenylistShadow(single, denyTerms) : single
  const finalSql = wrapWithRowCap(shaped)
  let result: { columns: string[]; rows: unknown[][] }
  try {
    result = runQuery(finalSql)
  } catch (e) {
    // Message only — a better-sqlite3 error message names columns/syntax, never
    // row contents. Safe to surface to the model; do not log it here.
    return `Error: ${e instanceof Error ? e.message : 'query failed'}`
  }
  return renderResult(result)
}

/**
 * The agent-kernel execute_sql backend: the SAME read-only safety stack Insight
 * uses (single-statement, read-only SELECT/WITH gate, LIMIT 200 auto-append,
 * 200-row / 500-char caps) but over a CALLER-SUPPLIED table allowlist instead of
 * Insight's rewind-frames-only one. The agent tool needs a wider surface (app
 * usage, tasks, conversations, memories, aggregations — see
 * productToolExecutors.ts's AGENT_SQL_TABLE_ALLOWLIST), so the allowlist is a
 * parameter; it is still a CLOSED allowlist (anything not listed is refused), so
 * meta/kv/embedding/credential-shaped tables stay unreachable.
 *
 * No denylist-shadow path here (that is an Insight-privacy feature): the agent
 * scope has no per-app denylist. Returns the string that becomes the tool_result —
 * an `Error: …` string (never a throw) on any rejection so the tool loop continues.
 *
 * Write support is deliberately NOT ported: v1 is read-only on Windows (Mac's
 * ask-mode write rules become moot), so INSERT/UPDATE/DELETE/DDL/PRAGMA/ATTACH are
 * all rejected by isReadOnlySql before a query ever reaches the DB.
 */
export function executeReadOnlySql(
  rawQuery: unknown,
  runQuery: QueryRunner,
  allowlist: ReadonlySet<string>
): string {
  const query = typeof rawQuery === 'string' ? rawQuery.trim() : ''
  if (!query) return 'Error: query is required'

  // Single statement only (Mac splits on ';' and rejects >1 non-empty).
  const statements = query
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
  if (statements.length > 1) {
    return 'Error: multi-statement queries are not allowed. Send one statement at a time.'
  }
  const single = statements[0] ?? query

  // Read-only gate: SELECT/WITH prefix AND no write/DDL keyword anywhere. This is
  // what rejects INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/PRAGMA/ATTACH/DETACH/
  // VACUUM/REINDEX/TRUNCATE/REPLACE (isReadOnlySql's blocklist).
  if (!isReadOnlySql(single)) {
    return 'Error: this SQL surface is read-only. Use SELECT or read-only WITH queries.'
  }

  // Even a valid read-only SELECT may only touch allowlisted tables — a closed
  // allowlist so meta/embedding/credential-shaped tables can never be read.
  if (!tablesAllowed(single, allowlist)) {
    return (
      'Error: that query references a table that is not queryable. Allowed tables: ' +
      [...allowlist].sort().join(', ')
    )
  }

  // Reject the unbounded-computation shapes the outer-LIMIT wrap can't bound
  // (recursive-CTE bomb, cartesian join) before any query reaches the DB.
  const dangerous = rejectDangerousShape(single)
  if (dangerous) return dangerous

  const finalSql = wrapWithRowCap(single)
  let result: { columns: string[]; rows: unknown[][] }
  try {
    result = runQuery(finalSql)
  } catch (e) {
    // Message only — a better-sqlite3 error names columns/syntax, never row
    // contents. Safe to surface to the model; do not log it here.
    return `Error: ${e instanceof Error ? e.message : 'query failed'}`
  }
  return renderResult(result)
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
