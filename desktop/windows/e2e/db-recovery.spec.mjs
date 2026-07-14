/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// DB corruption recovery E2E: boots the REAL built app (out/main/index.js) against a
// deliberately corrupted omi.db and proves it recovers, starts, and reports what it
// did — through the real better-sqlite3 driver, the real IPC chain and the real
// preload bridge.
//
// This is the piece the unit tests structurally cannot cover: dbRecovery.test.ts
// drives the recovery core with node:sqlite (better-sqlite3 is rebuilt for
// Electron's ABI and cannot load under plain-node vitest), so the production driver
// binding is only ever exercised here.
//
// Hermetic: throwaway --user-data-dir + a throwaway OMI_DB_PATH. Never touches the
// real profile. No network needed — the renderer's Firebase errors are irrelevant.
//
// Build first, then run: `pnpm test:e2e:db-recovery`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { DatabaseSync } from 'node:sqlite'
import { randomBytes } from 'node:crypto'
import { closeSync, existsSync, mkdtempSync, openSync, readdirSync, readFileSync, rmSync, writeSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

// A database that looks like a real omi.db: user tables the app's bootstrap also
// declares, seeded with rows, so a reset is observable (rows gone, schema back).
function seedDb(file) {
  const d = new DatabaseSync(file)
  d.exec(`
    CREATE TABLE local_conversation (
      id TEXT PRIMARY KEY, started_at INTEGER NOT NULL, ended_at INTEGER NOT NULL,
      transcript TEXT NOT NULL, created_at INTEGER NOT NULL
    );
    CREATE TABLE app_usage (exe_path TEXT PRIMARY KEY, exe_name TEXT NOT NULL);
  `)
  d.exec('BEGIN')
  const c = d.prepare('INSERT INTO local_conversation VALUES (?, ?, ?, ?, ?)')
  for (let i = 0; i < 200; i++) c.run(`conv-${i}`, i, i + 1, `transcript ${i}`.repeat(20), i)
  d.exec('COMMIT')
  d.close()
}

function clobber(file, offset, len) {
  const fd = openSync(file, 'r+')
  writeSync(fd, randomBytes(len), 0, len, offset)
  closeSync(fd)
}

test('a corrupt omi.db is recovered at startup; the app boots and reports it', async (t) => {
  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-dbrec-e2e-'))
  const dbFile = path.join(userDataDir, 'omi.db')
  const backupsDir = path.join(userDataDir, 'backups')

  seedDb(dbFile)
  // Destroy the page-1 b-tree header: SQLite reports "database disk image is
  // malformed" the moment anything reads the schema. The app must not crash on it.
  clobber(dbFile, 100, 8)
  const corruptBytes = readFileSync(dbFile)

  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      OMI_DB_PATH: dbFile // point the app at the corrupted throwaway DB
    }
  })
  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  })

  // (1) The app starts at all. Before this change, the first DB read threw.
  const page = await app.firstWindow()
  assert.ok(page, 'the app should boot with a corrupt database')

  // (2) The REAL IPC chain (renderer -> preload -> main -> better-sqlite3) reports
  // the recovery. This is the flag macOS declares and never sets.
  const status = await page.evaluate(() => window.omi.dbRecoveryStatus())
  assert.equal(status.recovered, true, 'corruption should have been detected')
  assert.equal(status.reset, true, 'a dead schema page leaves nothing to salvage')
  assert.equal(status.rowsRecovered, 0)
  assert.ok(status.backupPath, 'the corrupt original should have been archived')

  // (3) The corrupt original was really backed up, byte for byte.
  const backups = readdirSync(backupsDir)
  assert.equal(backups.length, 1, `expected exactly one backup, got ${backups.join(', ')}`)
  assert.ok(
    readFileSync(path.join(backupsDir, backups[0])).equals(corruptBytes),
    'the backup should be the corrupt bytes verbatim'
  )
  assert.match(backups[0], /^omi_corrupted_\d{8}_\d{6}\.db$/)

  // (4) The app is left with a WORKING database carrying its real schema — proof
  // the bootstrap + migrations ran on the replaced file.
  await app.close()
  const d = new DatabaseSync(dbFile, { readOnly: true })
  const tables = d
    .prepare("SELECT name FROM sqlite_master WHERE type='table'")
    .all()
    .map((r) => r.name)
  const version = d.prepare('PRAGMA user_version').get().user_version
  const convs = d.prepare('SELECT count(*) AS n FROM local_conversation').get().n
  d.close()

  for (const expected of ['local_conversation', 'rewind_frames', 'rewind_frames_fts', 'app_meta']) {
    assert.ok(tables.includes(expected), `schema should be recreated: missing ${expected}`)
  }
  assert.ok(version >= 2, `migrations should have run (user_version=${version})`)
  assert.equal(convs, 0, 'an unsalvageable database resets to empty')
})

test('a healthy omi.db is opened untouched — no false-positive recovery', async (t) => {
  // The safety case. A wrong corruption verdict would destroy real user data, so
  // prove the real app leaves a good database exactly as it found it.
  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-dbok-e2e-'))
  const dbFile = path.join(userDataDir, 'omi.db')
  seedDb(dbFile)

  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      OMI_DB_PATH: dbFile
    }
  })
  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  })

  const page = await app.firstWindow()
  const status = await page.evaluate(() => window.omi.dbRecoveryStatus())
  assert.equal(status.recovered, false, 'a healthy database must never be "recovered"')
  assert.equal(status.reset, false)
  assert.equal(status.backupPath, null)
  assert.equal(existsSync(path.join(userDataDir, 'backups')), false, 'no backup should be taken')

  // The user's rows are all still there.
  await app.close()
  const d = new DatabaseSync(dbFile, { readOnly: true })
  const convs = d.prepare('SELECT count(*) AS n FROM local_conversation').get().n
  d.close()
  assert.equal(convs, 200, 'every row of a healthy database must survive startup')
})
