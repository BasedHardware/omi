// cachedStmt is exercised against a REAL SQLite via node:sqlite (better-sqlite3 is
// built for Electron's ABI and can't load under plain-node vitest — same seam the
// other ipc tests use). node:sqlite's DatabaseSync satisfies the `{ prepare }`
// surface structurally, so it lands on the generic overload.
//
// The one new failure mode this cache introduces is a statement outliving its
// connection: a prepared statement is bound to the connection it was compiled on,
// so the cache MUST be keyed per connection and MUST NOT hand a statement from one
// connection to another. These tests pin exactly that.
import { DatabaseSync } from 'node:sqlite'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cachedStmt, statementCacheSize, STATEMENT_CACHE_CAP } from './stmtCache'

const SQL = 'SELECT value FROM kv WHERE key = ?'

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec('CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
  return db
}

let db: DatabaseSync

beforeEach(() => {
  db = makeDb()
  db.prepare('INSERT INTO kv (key, value) VALUES (?, ?)').run('a', 'alpha')
  db.prepare('INSERT INTO kv (key, value) VALUES (?, ?)').run('b', 'beta')
})

afterEach(() => {
  db.close()
})

describe('cachedStmt', () => {
  it('returns the SAME statement object for a repeated (connection, sql)', () => {
    const first = cachedStmt(db, SQL)
    const second = cachedStmt(db, SQL)
    expect(second).toBe(first)
  })

  it('returns DISTINCT statements for different sql on one connection', () => {
    const a = cachedStmt(db, SQL)
    const b = cachedStmt(db, 'SELECT key FROM kv ORDER BY key')
    expect(b).not.toBe(a)
  })

  it('reuses the statement across calls with different bind params', () => {
    expect((cachedStmt(db, SQL).get('a') as { value: string }).value).toBe('alpha')
    // Same cached statement, different params — must not carry state between runs.
    expect((cachedStmt(db, SQL).get('b') as { value: string }).value).toBe('beta')
    expect(cachedStmt(db, SQL).get('missing')).toBeUndefined()
  })

  it('sees rows written after the statement was first cached (no stale snapshot)', () => {
    const before = cachedStmt(db, 'SELECT COUNT(*) AS n FROM kv').get() as { n: number }
    expect(before.n).toBe(2)
    db.prepare('INSERT INTO kv (key, value) VALUES (?, ?)').run('c', 'gamma')
    const after = cachedStmt(db, 'SELECT COUNT(*) AS n FROM kv').get() as { n: number }
    expect(after.n).toBe(3)
  })

  it('keys the cache per connection — a swapped handle gets its own statements', () => {
    const onFirst = cachedStmt(db, SQL)

    // Simulate a connection swap (sign-out / profile switch / recovery reopen):
    // a brand-new Database instance must NOT reuse the first connection's statement.
    const db2 = makeDb()
    db2.prepare('INSERT INTO kv (key, value) VALUES (?, ?)').run('a', 'ALPHA2')
    const onSecond = cachedStmt(db2, SQL)

    expect(onSecond).not.toBe(onFirst)
    // And each statement queries its own connection's data.
    expect((onSecond.get('a') as { value: string }).value).toBe('ALPHA2')
    expect((onFirst.get('a') as { value: string }).value).toBe('alpha')
    db2.close()
  })

  it('bounds the per-connection cache with LRU eviction, staying correct on re-miss', () => {
    // A statement that we keep exercising must survive eviction (its recency is
    // refreshed on every hit). A never-touched-again one must be evicted once the
    // flood of distinct dynamic SQL shapes exceeds the cap.
    const HOT = 'SELECT value FROM kv WHERE key = ? /* hot */'
    const COLD = 'SELECT value FROM kv WHERE key = ? /* cold */'
    const hot0 = cachedStmt(db, HOT)
    const cold0 = cachedStmt(db, COLD)

    // Flood with > cap distinct shapes (mimics variable IN (?,…) clauses). Keep the
    // HOT statement warm across the flood so LRU protects it.
    for (let i = 0; i < STATEMENT_CACHE_CAP + 300; i++) {
      cachedStmt(db, `SELECT value FROM kv WHERE key = ? /* shape ${i} */`)
      if (i % 5 === 0) cachedStmt(db, HOT) // refresh recency
    }

    expect(statementCacheSize(db)).toBeLessThanOrEqual(STATEMENT_CACHE_CAP)

    // HOT was kept warm -> same object, still works.
    const hot1 = cachedStmt(db, HOT)
    expect(hot1).toBe(hot0)
    expect((hot1.get('a') as { value: string }).value).toBe('alpha')

    // COLD was never touched again -> evicted -> a fresh, working statement on re-miss.
    const cold1 = cachedStmt(db, COLD)
    expect(cold1).not.toBe(cold0)
    expect((cold1.get('b') as { value: string }).value).toBe('beta')
  })

  it('does not leak a closed connection’s statements onto a new one', () => {
    const dead = makeDb()
    expect(cachedStmt(dead, SQL)).toBeDefined()
    dead.close()

    // A fresh connection prepares its OWN statement rather than reviving the dead
    // one (a revived statement would throw "statement has been finalized" when
    // stepped). Proving the new statement queries the live connection's data is
    // proof it isn't the dead one — we deliberately never touch the dead statement
    // after close(), since inspecting a finalized statement throws.
    const live = makeDb()
    live.prepare('INSERT INTO kv (key, value) VALUES (?, ?)').run('a', 'fresh')
    const liveStmt = cachedStmt(live, SQL)
    expect((liveStmt.get('a') as { value: string }).value).toBe('fresh')
    live.close()
  })
})
