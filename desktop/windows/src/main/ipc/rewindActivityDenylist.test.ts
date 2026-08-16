// FIX 4(a): the Insight activity summary (db.ts rewindActivityAggregate) must
// exclude denylisted-app frames at the SQL layer, so their app names / window
// titles never enter Gemini's Phase-1 prompt.
//
// db.ts's better-sqlite3 can't load under plain-node vitest (Electron ABI), so —
// the established repo pattern (rewindFtsSearch.test.ts / dbTrack3.test.ts) — the
// rewind_frames DDL and the aggregate's exclusion query shape are replicated here
// verbatim from db.ts and exercised against a REAL node:sqlite engine. The
// drift-proof half (that the denylist is actually threaded into the aggregate) is
// pinned separately in ../assistants/insight/context.test.ts, and the shared
// substring-filter semantics are proven on a real engine in
// ../assistants/insight/sql.test.ts.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'

const SCHEMA = `
  CREATE TABLE rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    process_name TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
  );
`

// Verbatim shape of db.ts rewindActivityAggregate (the exclusion clause is the
// part under test).
function escapeLikeTerm(term: string): string {
  return term.replace(/[\\%_]/g, (c) => `\\${c}`)
}
function aggregate(
  db: DatabaseSync,
  fromMs: number,
  toMs: number,
  limit: number,
  excludedTerms: string[]
): { app: string; windowTitle: string; count: number }[] {
  const terms = excludedTerms.map((t) => t.trim()).filter((t) => t.length > 0)
  const exclusion = terms
    .map(() => `AND (app || ' ' || window_title || ' ' || process_name) NOT LIKE ? ESCAPE '\\'`)
    .join(' ')
  const patterns = terms.map((t) => `%${escapeLikeTerm(t)}%`)
  return db
    .prepare(
      `SELECT app, window_title AS windowTitle, COUNT(*) AS count,
              MIN(ts) AS firstSeen, MAX(ts) AS lastSeen
         FROM rewind_frames
        WHERE ts >= ? AND ts <= ? AND app IS NOT NULL AND app != ''
        ${exclusion}
        GROUP BY app, window_title
        ORDER BY count DESC
        LIMIT ?`
    )
    .all(fromMs, toMs, ...patterns, limit) as { app: string; windowTitle: string; count: number }[]
}

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec(SCHEMA)
  const ins = db.prepare(
    'INSERT INTO rewind_frames (ts, app, window_title, process_name, image_path) VALUES (?, ?, ?, ?, ?)'
  )
  ins.run(1, 'Signal', 'John Doe', 'Signal.exe', '/1.jpg')
  ins.run(2, 'Signal', 'John Doe', 'Signal.exe', '/2.jpg')
  ins.run(3, 'Chrome', 'Docs', 'chrome.exe', '/3.jpg')
  ins.run(4, 'Chrome', 'signal group chat', 'chrome.exe', '/4.jpg') // denied via title
  return db
}

describe('rewindActivityAggregate denylist exclusion (real SQLite)', () => {
  it('drops a denylisted app entirely from the summary', () => {
    const db = makeDb()
    const rows = aggregate(db, 0, 10, 30, ['Signal'])
    const apps = rows.map((r) => r.app)
    expect(apps).not.toContain('Signal')
    // The allowed Chrome/Docs group survives; the Chrome group whose TITLE contains
    // the denied term is also excluded (same substring predicate as the frame gate).
    expect(rows.map((r) => ({ app: r.app, windowTitle: r.windowTitle, count: r.count }))).toEqual([
      { app: 'Chrome', windowTitle: 'Docs', count: 1 }
    ])
    db.close()
  })

  it('is case-insensitive (denylist "signal" removes app "Signal")', () => {
    const db = makeDb()
    expect(aggregate(db, 0, 10, 30, ['signal']).map((r) => r.app)).not.toContain('Signal')
    db.close()
  })

  it('an empty denylist returns every group, including the denied app', () => {
    const db = makeDb()
    const apps = aggregate(db, 0, 10, 30, []).map((r) => r.app)
    expect(apps).toContain('Signal')
    expect(apps).toContain('Chrome')
    db.close()
  })
})
