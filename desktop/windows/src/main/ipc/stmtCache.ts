// Per-connection prepared-statement cache.
//
// better-sqlite3 (and node:sqlite) already compile SQL once internally, but
// re-calling `db.prepare(sql)` on every IPC hit still allocates a fresh JS
// statement wrapper and re-does the compiled-statement lookup. Preparing once
// and reusing the statement is the driver-recommended pattern; this helper makes
// that mechanical without hand-hoisting hundreds of module-scoped `let`s.
//
// The cache is keyed on the *connection object* via a WeakMap, which is load-
// bearing for correctness:
//   - A prepared statement is bound to the connection it was prepared on; keying
//     by connection means a statement is never reused across the main / read-only
//     / kernel connections (or, in tests, across the fresh DatabaseSync each case
//     opens).
//   - When a connection is closed/GC'd, its statement cache is collected with it —
//     no manual invalidation, no dangling statements over a swapped handle.
//
// Do NOT route these through the cache (callers keep inline `db.prepare`):
//   - SQL built with a variable number of placeholders (IN (?,?,…)) or a dynamic
//     column set — each shape is a distinct string, so caching would grow without
//     bound.
//   - Statements put into a sticky mode (`.raw()`, `.pluck()`, `.safeIntegers()`),
//     since the mode would leak to every other caller of the same SQL.
//
// Type-only import (fully erased at compile time — no runtime `require`), so
// taskStore.ts (driver-agnostic, loaded under plain-node vitest) can still import
// this module without pulling in better-sqlite3's native binary.
import type BetterSqlite3 from 'better-sqlite3'

const caches = new WeakMap<object, Map<string, unknown>>()

/**
 * Return a prepared statement for `sql`, cached per `db` connection. The first
 * call on a given (connection, sql) pair prepares it; later calls reuse it.
 *
 * The overloads preserve each caller's exact statement type:
 *   - better-sqlite3's `Database` gets a real `Statement` (its generic `prepare`
 *     conditional-return type would otherwise degrade to a bad union through
 *     `ReturnType`, breaking `.get()/.run()` arities).
 *   - any other connection (node:sqlite's `DatabaseSync`, the kernel/taskStore
 *     structural surfaces) infers its statement type from its own `prepare`.
 */
export function cachedStmt(
  db: BetterSqlite3.Database,
  sql: string
): BetterSqlite3.Statement<unknown[]>
export function cachedStmt<D extends { prepare(sql: string): unknown }>(
  db: D,
  sql: string
): ReturnType<D['prepare']>
export function cachedStmt(db: { prepare(sql: string): unknown }, sql: string): unknown {
  let cache = caches.get(db)
  if (cache === undefined) {
    cache = new Map<string, unknown>()
    caches.set(db, cache)
  }
  let stmt = cache.get(sql)
  if (stmt === undefined) {
    stmt = db.prepare(sql)
    cache.set(sql, stmt)
  }
  return stmt
}
