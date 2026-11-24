// The pre-cloud AI-profile table reader/dropper, against a real SQLite db with the
// table exactly as older builds created it (node:sqlite; see dbMigrations.test.ts
// for why not better-sqlite3).
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import {
  dropLegacyProfile,
  readNewestLegacyProfile,
  type LegacyProfileDb
} from './legacyProfileTable'

const OLD_TABLE = `
  CREATE TABLE ai_user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_text TEXT NOT NULL,
    data_sources_used TEXT,
    generated_at INTEGER NOT NULL,
    backend_synced INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX idx_ai_user_profiles_generated_at ON ai_user_profiles(generated_at);
`

const asDb = (db: DatabaseSync): LegacyProfileDb => db as unknown as LegacyProfileDb
const exists = (db: DatabaseSync, name: string): boolean =>
  Boolean(db.prepare('SELECT 1 AS x FROM sqlite_master WHERE name = ?').get(name))

describe('legacy AI-profile table', () => {
  it('reads the newest row (by generated_at, then id) with its sync marker', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_TABLE)
    const ins = db.prepare(
      'INSERT INTO ai_user_profiles (profile_text, generated_at, backend_synced) VALUES (?, ?, ?)'
    )
    ins.run('oldest', 1000, 1)
    ins.run('newest, edited', 3000, 1)
    ins.run('newer id, older time', 2000, 0)
    expect(readNewestLegacyProfile(asDb(db))).toEqual({
      profileText: 'newest, edited',
      generatedAt: 3000,
      backendSynced: true
    })
    db.close()
  })

  it('returns null for an empty table and for a missing one', () => {
    const db = new DatabaseSync(':memory:')
    expect(readNewestLegacyProfile(asDb(db))).toBeNull()
    db.exec(OLD_TABLE)
    expect(readNewestLegacyProfile(asDb(db))).toBeNull()
    db.close()
  })

  it('drops the table and its index, idempotently', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(OLD_TABLE)
    dropLegacyProfile(asDb(db))
    expect(exists(db, 'ai_user_profiles')).toBe(false)
    expect(exists(db, 'idx_ai_user_profiles_generated_at')).toBe(false)
    expect(() => dropLegacyProfile(asDb(db))).not.toThrow()
    db.close()
  })
})
