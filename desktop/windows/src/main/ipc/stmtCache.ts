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
// The per-connection map is **LRU-bounded** (STATEMENT_CACHE_CAP). Most call sites
// pass a small fixed set of literal SQL, but some route dynamic SQL through here —
// variable-length `IN (?,?,…)` clauses and dynamic column sets each mint a distinct
// string, so an unbounded map would grow for the life of a long-lived connection
// (the agent-kernel store especially). Evicting the least-recently-used entry is
// correctness-safe: a re-miss just re-prepares, which is exactly the pre-cache
// behavior, and no caller retains a statement across calls (outside a synchronous
// transaction that finishes before returning). Hot literal statements stay resident
// because every hit refreshes their recency.
//
// Still keep inline `db.prepare` for statements put into a sticky mode
// (`.raw()`, `.pluck()`, `.safeIntegers()`) — the mode would leak to every other
// caller of the same SQL through the shared cached statement.
//
// Type-only import (fully erased at compile time — no runtime `require`), so
// taskStore.ts (driver-agnostic, loaded under plain-node vitest) can still import
// this module without pulling in better-sqlite3's native binary.
import type BetterSqlite3 from 'better-sqlite3'

/** Max prepared statements retained per connection before LRU eviction kicks in.
 *  Comfortably above the count of distinct literal SQL any one connection uses, so
 *  only genuinely-dynamic SQL ever causes eviction. */
export const STATEMENT_CACHE_CAP = 512

const caches = new WeakMap<object, Map<string, unknown>>()

/**
 * Return a prepared statement for `sql`, cached (LRU, per connection) on `db`. The
 * first call on a given (connection, sql) pair prepares it; later calls reuse it.
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
  const existing = cache.get(sql)
  if (existing !== undefined) {
    // LRU touch: re-insert so this key becomes most-recently-used (Map preserves
    // insertion order, so the first key is always the least-recently-used).
    cache.delete(sql)
    cache.set(sql, existing)
    return existing
  }
  const stmt = db.prepare(sql)
  cache.set(sql, stmt)
  if (cache.size > STATEMENT_CACHE_CAP) {
    const lru = cache.keys().next().value
    if (lru !== undefined) cache.delete(lru)
  }
  return stmt
}

/** Test/introspection only: current cached-statement count for a connection. */
export function statementCacheSize(db: object): number {
  return caches.get(db)?.size ?? 0
}
