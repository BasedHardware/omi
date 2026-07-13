// Sign-out teardown (SQLite half): wipeUserDataOn must clear EVERY user-scoped
// table so a second account on the same machine can't see the prior user's data.
// Proven against a real SQLite DB via node:sqlite (better-sqlite3 is built for
// Electron's ABI and won't load under plain-node vitest — same reason
// dbMigrations.test.ts uses node:sqlite).
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { USER_DATA_TABLES, wipeUserDataOn } from './dbWipe'

// Minimal one-column stand-ins for each user table — enough to insert + count.
function makeSeededDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  for (const table of USER_DATA_TABLES) {
    db.exec(`CREATE TABLE ${table} (v INTEGER)`)
    db.prepare(`INSERT INTO ${table} (v) VALUES (1)`).run()
  }
  return db
}

function count(db: DatabaseSync, table: string): number {
  return (db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n
}

describe('wipeUserDataOn (sign-out teardown)', () => {
  it('clears every user-scoped table', () => {
    const db = makeSeededDb()
    for (const t of USER_DATA_TABLES) expect(count(db, t)).toBe(1)

    wipeUserDataOn(db)

    for (const t of USER_DATA_TABLES) expect(count(db, t)).toBe(0)
  })

  it('rolls back and leaves data intact if a delete fails mid-wipe', () => {
    const db = makeSeededDb()
    // Drop one table so its DELETE throws partway through the transaction.
    db.exec('DROP TABLE insights')

    expect(() => wipeUserDataOn(db)).toThrow()

    // The tables deleted before the failure must be restored by the ROLLBACK —
    // an all-or-nothing wipe, never a partial one.
    for (const t of USER_DATA_TABLES) {
      if (t === 'insights') continue
      expect(count(db, t)).toBe(1)
    }
  })
})
