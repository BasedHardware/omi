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
import {
  closeSync,
  existsSync,
  mkdtempSync,
  openSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeSync
} from 'node:fs'
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

// The option-B loop, on the real app and the real better-sqlite3 driver: a damaged
// DATA page is invisible to the startup check, so a live query has to trip it, and
// the repair lands on the next launch. This is the path that actually saves the
// user's data — and the one macOS designed (reportQueryError) but never wired up.
test('a damaged data page trips at runtime and is repaired on the next launch', async (t) => {
  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-dbtrip-e2e-'))
  const dbFile = path.join(userDataDir, 'omi.db')
  const backupsDir = path.join(userDataDir, 'backups')

  seedDb(dbFile)
  // Clobber a page in the middle of the file: it lands in a data page of
  // local_conversation and leaves the schema page perfectly readable.
  const size = readFileSync(dbFile).length
  clobber(dbFile, Math.floor(size / 2) & ~4095, 4096)

  const env = {
    ...process.env,
    OMI_E2E: '1',
    OMI_AUTOMATION: '0',
    OMI_SKIP_TUNNEL: '1',
    OMI_DB_PATH: dbFile
  }
  const launch = () => electron.launch({ args: [mainEntry, `--user-data-dir=${userDataDir}`], env })

  // --- session 1: startup does NOT detect it; a live query trips the flag ---
  let app = await launch()
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
  let page = await app.firstWindow()

  const first = await page.evaluate(() => window.omi.dbRecoveryStatus())
  assert.equal(first.recovered, false, 'a data-page corruption is invisible to the startup check')
  assert.equal(existsSync(backupsDir), false, 'nothing should have been backed up yet')

  // Drive the REAL app code path that reads the damaged table. listConversations
  // goes main -> better-sqlite3 -> the corrupt page, so it must throw — and that
  // throw is what arms the trip.
  const threw = await page.evaluate(async () => {
    try {
      await window.omi.listLocalConversations()
      return false
    } catch {
      return true
    }
  })
  assert.equal(threw, true, 'reading the damaged table should throw through the real IPC path')

  await app.close()

  // Inspect the file between sessions — and ALWAYS close the handle. On Windows an
  // open handle (even a read-only one, which brings a -wal/-shm with it) blocks the
  // app's own unlink during the swap with EBUSY, so a leaked handle here fails the
  // repair under test and looks exactly like a product bug.
  {
    const d = new DatabaseSync(dbFile, { readOnly: true })
    try {
      // The trip persisted the suspicion to disk, in the app's own database.
      const flagged = d
        .prepare("SELECT value FROM app_meta WHERE key = 'db_corruption_suspected'")
        .get()
      assert.equal(flagged?.value, '1', 'the live corrupt error should have flagged the DB')

      // The damage is genuinely still on disk — the app did not "heal" it by accident.
      assert.throws(
        () => d.prepare('SELECT * FROM local_conversation').all(),
        /malformed/,
        'the damaged table should still be unreadable after session 1'
      )
    } finally {
      d.close()
    }
  }

  // --- session 2 (the restart): re-verify, salvage, swap ---
  app = await launch()
  // Surface any main-process failure during the repair. The repair once died on a
  // Windows EBUSY unlinking omi.db-wal and silently re-ran forever; without this
  // the only symptom was an unhelpful `recovered === false`.
  const mainErrors = []
  app.process().stderr?.on('data', (b) => {
    const s = String(b)
    if (s.includes('database init failed')) mainErrors.push(s.trim())
  })
  page = await app.firstWindow()
  const second = await page.evaluate(() => window.omi.dbRecoveryStatus())

  assert.deepEqual(mainErrors, [], 'the repair must not throw in the main process')
  assert.equal(second.recovered, true, 'the next launch should repair the flagged database')
  assert.equal(second.reset, false, 'a data-page corruption is salvageable — never a wipe')
  assert.ok(second.rowsRecovered > 0, `expected rows to be salvaged, got ${second.rowsRecovered}`)
  assert.ok(second.backupPath, 'the corrupt original should be archived')
  assert.equal(readdirSync(backupsDir).length, 1)

  // The damaged table is READABLE again through the real app path — the actual
  // user-visible outcome. Before this, it threw forever.
  const conversations = await page.evaluate(() => window.omi.listLocalConversations())
  assert.ok(Array.isArray(conversations), 'conversations should load after the repair')
  assert.ok(
    conversations.length > 150,
    `most rows should survive the repair, got ${conversations.length} of 200`
  )

  await app.close()
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
