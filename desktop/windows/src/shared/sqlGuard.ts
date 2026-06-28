// Read-only SQL guard for the chat agent's execute_sql tool. The agent LLM
// writes SQL against the local DB; this validates it is a single, read-only
// SELECT/WITH statement and enforces a row cap. It is the first line of defense;
// the second is opening the DB connection in readonly mode (see db.ts), so even
// a validator miss cannot mutate data. Pure — no I/O.

const MAX_LIMIT = 200
const FORBIDDEN =
  /\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|TRIGGER|GRANT|TRUNCATE|LOAD_EXTENSION|WRITEFILE|READFILE|FSDIR|EDIT)\b/i

// A trailing LIMIT clause in any of SQLite's forms:
//   LIMIT <count>            (m[1] = count)
//   LIMIT <count> OFFSET <n> (m[1] = count)
//   LIMIT <offset>, <count>  (m[1] = offset, m[2] = count)
const LIMIT_TAIL = /\blimit\s+(\d+)(?:\s*,\s*(\d+)|\s+offset\s+\d+)?\s*$/i

// Remove -- line comments and /* */ block comments so they can't smuggle a
// second statement or a forbidden keyword past the checks.
function stripComments(sql: string): string {
  return sql
    .replace(/--[^\n]*/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .trim()
}

// Validate `sql` is a single read-only SELECT/WITH statement and return it with
// an enforced LIMIT. Throws on anything else.
export function guardSelect(sql: string): string {
  let s = stripComments(sql)
    .replace(/;\s*$/, '')
    .trim()
  if (!s) throw new Error('Empty query')
  if (s.includes(';')) throw new Error('Multiple statements are not allowed')
  if (!/^(SELECT|WITH)\b/i.test(s)) throw new Error('Only SELECT/WITH queries are allowed')
  if (FORBIDDEN.test(s)) throw new Error('Only read-only queries are allowed')

  const m = s.match(LIMIT_TAIL)
  if (m) {
    if (m[2] !== undefined) {
      // LIMIT <offset>, <count> — cap the count (m[2]), preserve the offset.
      if (Number(m[2]) > MAX_LIMIT) {
        s = s.replace(LIMIT_TAIL, (_full, off: string) => `LIMIT ${off}, ${MAX_LIMIT}`)
      }
    } else if (Number(m[1]) > MAX_LIMIT) {
      // LIMIT <count> [OFFSET <n>] — cap the count, preserve any OFFSET.
      s = s.replace(LIMIT_TAIL, (full) => full.replace(/\blimit\s+\d+/i, `LIMIT ${MAX_LIMIT}`))
    }
  } else if (!/\blimit\b/i.test(s)) {
    // No LIMIT anywhere — add one. (If a LIMIT exists but not at the tail, e.g.
    // inside a subquery, leave the query alone: appending would be a syntax
    // error, and the readonly connection is the real safety boundary.)
    s = `${s} LIMIT ${MAX_LIMIT}`
  }
  return s
}
