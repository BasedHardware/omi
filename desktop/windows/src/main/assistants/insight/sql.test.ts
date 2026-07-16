import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it, vi } from 'vitest'
import {
  applyDenylistShadow,
  buildDenyFilter,
  executeSql,
  executeReadOnlySql,
  formatRows,
  isReadOnlySql,
  loadScreenshotBase64,
  MAX_ROWS,
  ROW_FETCH_CAP,
  CELL_CAP,
  rejectDangerousShape,
  wrapWithRowCap,
  type QueryRunner
} from './sql'

describe('isReadOnlySql', () => {
  it('accepts SELECT and WITH', () => {
    expect(isReadOnlySql('SELECT * FROM rewind_frames')).toBe(true)
    expect(isReadOnlySql('  with x as (select 1) select * from x')).toBe(true)
  })
  it('rejects writes and DDL as whole words', () => {
    for (const q of [
      'DELETE FROM rewind_frames',
      'UPDATE rewind_frames SET app = ""',
      'INSERT INTO rewind_frames VALUES (1)',
      'DROP TABLE rewind_frames',
      'PRAGMA table_info(rewind_frames)',
      'SELECT 1; DELETE FROM rewind_frames',
      'select 1 union select 2; drop table x'
    ]) {
      expect(isReadOnlySql(q), q).toBe(false)
    }
  })
  it('ignores keywords hidden in comments', () => {
    expect(isReadOnlySql('SELECT 1 -- delete everything')).toBe(true)
    expect(isReadOnlySql('SELECT 1 /* drop */ FROM rewind_frames')).toBe(true)
  })
  it('ignores keywords that only appear inside a string literal', () => {
    // OCR text / window titles routinely contain these words — they must not trip
    // the blocklist when they live in a literal rather than as SQL structure.
    expect(isReadOnlySql("SELECT ocr_text FROM rewind_frames WHERE ocr_text LIKE '%delete%'")).toBe(
      true
    )
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE window_title LIKE '%Create%'")).toBe(
      true
    )
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE ocr_text LIKE '%update%'")).toBe(true)
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE ocr_text LIKE '%insert file%'")).toBe(
      true
    )
  })
  it('handles an escaped quote inside a literal and still allows it', () => {
    expect(
      isReadOnlySql("SELECT ocr_text FROM rewind_frames WHERE ocr_text LIKE '%it''s delete%'")
    ).toBe(true)
  })
  it('ignores a keyword used as a double-quoted identifier', () => {
    expect(isReadOnlySql('SELECT "create" FROM rewind_frames')).toBe(true)
  })
  it('still rejects a real write even when a literal is also present', () => {
    // The write is SQL structure, not a literal — must remain rejected.
    expect(isReadOnlySql("DELETE FROM rewind_frames WHERE app LIKE '%safe%'")).toBe(false)
    expect(isReadOnlySql("SELECT 1; DELETE FROM rewind_frames WHERE app = 'x'")).toBe(false)
  })
})

describe('wrapWithRowCap', () => {
  it('wraps the query in an unsuppressible outer LIMIT (cap + 1)', () => {
    expect(wrapWithRowCap('SELECT * FROM rewind_frames')).toBe(
      `SELECT * FROM (SELECT * FROM rewind_frames) LIMIT ${ROW_FETCH_CAP}`
    )
  })
  it('strips a trailing ; and keeps the outer LIMIT even when the inner query has its own', () => {
    expect(wrapWithRowCap('SELECT * FROM rewind_frames LIMIT 5;')).toBe(
      `SELECT * FROM (SELECT * FROM rewind_frames LIMIT 5) LIMIT ${ROW_FETCH_CAP}`
    )
  })
  it('cannot be suppressed by the word "limit" hidden in a string literal or alias', () => {
    // The old conditional append skipped whenever the raw query merely contained
    // "limit"; the outer wrap applies regardless.
    for (const q of [
      "SELECT ocr_text FROM rewind_frames WHERE ocr_text LIKE '%limit%'",
      'SELECT app AS limit_col FROM rewind_frames'
    ]) {
      expect(wrapWithRowCap(q).endsWith(`) LIMIT ${ROW_FETCH_CAP}`)).toBe(true)
    }
  })
})

describe('formatRows caps', () => {
  it('renders a pipe table with a row count', () => {
    const out = formatRows(
      ['id', 'app'],
      [
        [1, 'Terminal'],
        [2, 'Chrome']
      ]
    )
    expect(out).toContain('id | app')
    expect(out).toContain('1 | Terminal')
    expect(out.endsWith('2 row(s)')).toBe(true)
  })
  it('empty set → "No results"', () => {
    expect(formatRows(['id'], [])).toBe('No results')
  })
  it('truncates a cell longer than 500 chars', () => {
    const big = 'x'.repeat(CELL_CAP + 100)
    const out = formatRows(['ocr'], [[big]])
    expect(out).toContain(`${'x'.repeat(CELL_CAP)}...`)
    expect(out).not.toContain('x'.repeat(CELL_CAP + 1))
  })
  it('caps at 200 rows', () => {
    const rows = Array.from({ length: 250 }, (_, i) => [i])
    const out = formatRows(['id'], rows)
    expect(out.endsWith(`${MAX_ROWS} row(s)`)).toBe(true)
  })
})

describe('executeSql', () => {
  it('rejects a non-SELECT BEFORE running it', () => {
    const runQuery = vi.fn()
    const out = executeSql('DELETE FROM rewind_frames', runQuery)
    expect(out).toMatch(/read-only/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects multiple statements', () => {
    const runQuery = vi.fn()
    expect(executeSql('SELECT 1; SELECT 2', runQuery)).toMatch(/single statement/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('wraps the query in an unsuppressible outer LIMIT and passes it to the runner', () => {
    const runQuery = vi.fn(() => ({ columns: ['id'], rows: [[1]] }))
    const out = executeSql('SELECT id FROM rewind_frames', runQuery)
    expect(runQuery).toHaveBeenCalledWith(
      `SELECT * FROM (SELECT id FROM rewind_frames) LIMIT ${ROW_FETCH_CAP}`
    )
    expect(out).toContain('1 row(s)')
  })
  it('returns an error string (not a throw) when the runner throws', () => {
    const runQuery = vi.fn(() => {
      throw new Error('no such column: bogus')
    })
    expect(executeSql('SELECT bogus FROM rewind_frames', runQuery)).toMatch(/^Error:/)
  })
})

describe('executeSql table allowlist', () => {
  it('allows a plain read of rewind_frames', () => {
    const runQuery = vi.fn(() => ({ columns: ['app'], rows: [['Terminal']] }))
    executeSql('SELECT app FROM rewind_frames', runQuery)
    expect(runQuery).toHaveBeenCalledWith(
      `SELECT * FROM (SELECT app FROM rewind_frames) LIMIT ${ROW_FETCH_CAP}`
    )
  })
  it('allows the FTS mirror table and a rewind_frames↔fts join', () => {
    const runQuery = vi.fn(() => ({ columns: ['id'], rows: [[1]] }))
    executeSql("SELECT rowid FROM rewind_frames_fts WHERE rewind_frames_fts MATCH 'foo'", runQuery)
    expect(runQuery).toHaveBeenCalledTimes(1)
    executeSql(
      'SELECT f.id FROM rewind_frames f JOIN rewind_frames_fts x ON x.rowid = f.id',
      runQuery
    )
    expect(runQuery).toHaveBeenCalledTimes(2)
  })
  it('allows a CTE / derived table that only reads rewind_frames', () => {
    const runQuery = vi.fn(() => ({ columns: ['app'], rows: [] }))
    executeSql('WITH recent AS (SELECT app FROM rewind_frames) SELECT app FROM recent', runQuery)
    expect(runQuery).toHaveBeenCalledTimes(1)
    executeSql('SELECT app FROM (SELECT app FROM rewind_frames) t', runQuery)
    expect(runQuery).toHaveBeenCalledTimes(2)
  })
  it('rejects a read of a non-allowlisted table before running it', () => {
    const runQuery = vi.fn()
    for (const q of [
      'SELECT * FROM local_conversation',
      'SELECT display_name FROM ai_user_profiles',
      'SELECT * FROM local_kg_nodes'
    ]) {
      expect(executeSql(q, runQuery), q).toMatch(/only the rewind_frames table is queryable/i)
    }
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects a JOIN onto a non-allowlisted table', () => {
    const runQuery = vi.fn()
    const out = executeSql(
      'SELECT f.app FROM rewind_frames f JOIN local_conversation c ON c.id = f.id',
      runQuery
    )
    expect(out).toMatch(/only the rewind_frames table is queryable/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('cannot be bypassed by comma-joins, quoting, or a subquery', () => {
    const runQuery = vi.fn()
    for (const q of [
      'SELECT * FROM rewind_frames, local_conversation', // implicit comma-join
      'SELECT * FROM "local_conversation"', // double-quoted identifier
      'SELECT * FROM [local_conversation]', // bracket-quoted identifier
      'SELECT * FROM (SELECT * FROM ai_user_profiles)' // hidden inside a subquery
    ]) {
      expect(executeSql(q, runQuery), q).toMatch(/only the rewind_frames table is queryable/i)
    }
    expect(runQuery).not.toHaveBeenCalled()
  })
})

describe('rejectDangerousShape (DoS guard)', () => {
  it('rejects an unbounded recursive CTE', () => {
    expect(
      rejectDangerousShape(
        'WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r'
      )
    ).toMatch(/recursive/i)
  })
  it('allows a recursive CTE whose body carries its own LIMIT', () => {
    expect(
      rejectDangerousShape(
        'WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r LIMIT 100) SELECT * FROM r'
      )
    ).toBeNull()
  })
  it('allows a non-self-referential WITH RECURSIVE (cannot infinite-loop)', () => {
    expect(rejectDangerousShape('WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r')).toBeNull()
  })
  it('rejects an implicit comma-join cartesian', () => {
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames a, rewind_frames b, rewind_frames c')
    ).toMatch(/cartesian/i)
  })
  it('rejects a CROSS JOIN', () => {
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames a CROSS JOIN rewind_frames b')
    ).toMatch(/cartesian/i)
  })
  it('rejects a JOIN with no ON/USING predicate', () => {
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames a JOIN rewind_frames b')
    ).toMatch(/cartesian/i)
  })
  it('allows a proper JOIN ... ON and a single-table aggregate', () => {
    expect(
      rejectDangerousShape(
        'SELECT f.id FROM rewind_frames f JOIN rewind_frames_fts x ON x.rowid = f.id'
      )
    ).toBeNull()
    expect(rejectDangerousShape('SELECT count(*) FROM rewind_frames')).toBeNull()
  })
  it('allows an ON predicate that references columns nested in a subquery', () => {
    // The correlation is real (f.ts is compared), even though a subquery follows.
    expect(
      rejectDangerousShape(
        'SELECT f.id FROM rewind_frames f JOIN rewind_frames_fts x ON x.rowid = f.id AND f.ts > (SELECT min(ts) FROM rewind_frames)'
      )
    ).toBeNull()
  })
})

// Regression tests for the 4 DoS shape-guard bypasses closed together. Each was an
// otherwise-valid, read-only, allowlisted query that the outer-LIMIT wrap could not
// bound and the guard used to let through.
describe('rejectDangerousShape — closed bypasses', () => {
  it('bypass 1: a recursive-CTE bomb nested inside a subquery (not a leading WITH)', () => {
    expect(
      rejectDangerousShape(
        'SELECT * FROM (WITH RECURSIVE r AS (SELECT 1 AS x UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r) t'
      )
    ).toMatch(/recursive/i)
  })
  it('bypass 2: a LIMIT smuggled into a nested subquery does NOT count as bounding the recursion', () => {
    expect(
      rejectDangerousShape(
        'WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x < (SELECT 100 LIMIT 1)) SELECT max(x) FROM r'
      )
    ).toMatch(/recursive/i)
    // A genuine top-level LIMIT on the recursive body still terminates → still allowed.
    expect(
      rejectDangerousShape(
        'WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r LIMIT 100) SELECT * FROM r'
      )
    ).toBeNull()
  })
  it('bypass 3: a tautological ON predicate (ON 1=1 / ON true) is a cartesian in disguise', () => {
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames a JOIN rewind_frames b ON 1=1')
    ).toMatch(/cartesian/i)
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames a JOIN rewind_frames b ON true')
    ).toMatch(/cartesian/i)
    expect(
      rejectDangerousShape("SELECT count(*) FROM rewind_frames a JOIN rewind_frames b ON 'x'='x'")
    ).toMatch(/cartesian/i)
  })
  it('bypass 4: a comma-subquery (FROM a, (SELECT …)) is an implicit cartesian', () => {
    expect(
      rejectDangerousShape('SELECT count(*) FROM rewind_frames, (SELECT id FROM rewind_frames)')
    ).toMatch(/cartesian/i)
    // The old "scalar subquery" idiom is now rejected too (its cardinality is
    // unverifiable) — this is a deliberate tightening.
    expect(
      rejectDangerousShape('SELECT * FROM rewind_frames, (SELECT max(ts) m FROM rewind_frames)')
    ).toMatch(/cartesian/i)
  })
})

describe('executeSql DoS protections', () => {
  it('a "limit" in a string literal does NOT suppress the outer row cap', () => {
    const runQuery = vi.fn((_sql: string) => ({ columns: ['ocr'], rows: [['x']] }))
    executeSql("SELECT ocr_text ocr FROM rewind_frames WHERE ocr_text LIKE '%limit%'", runQuery)
    const sql = runQuery.mock.calls[0][0]
    expect(sql.endsWith(`) LIMIT ${ROW_FETCH_CAP}`)).toBe(true)
  })
  it('rejects a recursive-CTE bomb BEFORE it ever reaches the DB (no hang)', () => {
    // The runner is a real node:sqlite handle; if the guard let this through it
    // would loop forever. It must never be called.
    const db = new DatabaseSync(':memory:')
    db.exec('CREATE TABLE rewind_frames (id INTEGER)')
    const runQuery = vi.fn((sql: string) => {
      const stmt = db.prepare(sql)
      const rows = stmt.all() as Record<string, unknown>[]
      const columns = rows.length ? Object.keys(rows[0]) : []
      return { columns, rows: rows.map((r) => columns.map((c) => r[c])) }
    })
    const out = executeSql(
      'WITH RECURSIVE r AS (SELECT 1 AS x UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r',
      runQuery
    )
    expect(out).toMatch(/recursive/i)
    expect(runQuery).not.toHaveBeenCalled()
    db.close()
  })
  it('rejects a recursive-CTE bomb NESTED in a subquery (reaches the shape guard, no hang)', () => {
    // No column list, so the allowlist recognizes `r` as a CTE-bound relation and
    // lets it through to the shape guard — which must reject it before the DB runs it.
    const db = new DatabaseSync(':memory:')
    db.exec('CREATE TABLE rewind_frames (id INTEGER)')
    const runQuery = vi.fn((sql: string) => {
      const stmt = db.prepare(sql)
      const rows = stmt.all() as Record<string, unknown>[]
      const columns = rows.length ? Object.keys(rows[0]) : []
      return { columns, rows: rows.map((r) => columns.map((c) => r[c])) }
    })
    const out = executeSql(
      'SELECT * FROM (WITH RECURSIVE r AS (SELECT 1 AS x UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r) t',
      runQuery
    )
    expect(out).toMatch(/recursive/i)
    expect(runQuery).not.toHaveBeenCalled()
    db.close()
  })
  it('also rejects the column-list recursion form (defense in depth — allowlist layer)', () => {
    // `r(x) AS (…)` is not recognized as a CTE binding by the table allowlist, so
    // `r` reads as a disallowed table and the query is rejected there — still no hang.
    const runQuery = vi.fn(() => ({ columns: [], rows: [] as unknown[][] }))
    const out = executeSql(
      'WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r',
      runQuery
    )
    expect(out).toMatch(/^Error:/)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects a cartesian-join aggregate BEFORE it ever reaches the DB (no N³ scan)', () => {
    const runQuery = vi.fn(() => ({ columns: ['n'], rows: [[0]] }))
    const out = executeSql(
      'SELECT count(*) FROM rewind_frames a, rewind_frames b, rewind_frames c',
      runQuery
    )
    expect(out).toMatch(/cartesian/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('flags truncation when more than MAX_ROWS come back (cap + 1 sentinel)', () => {
    const rows = Array.from({ length: ROW_FETCH_CAP }, (_, i) => [i])
    const runQuery = vi.fn(() => ({ columns: ['id'], rows }))
    const out = executeSql('SELECT id FROM rewind_frames', runQuery)
    expect(out).toContain(`${MAX_ROWS} row(s)`)
    expect(out).toMatch(/Auto-limited to 200 rows/i)
  })
  it('does NOT flag truncation at exactly MAX_ROWS', () => {
    const rows = Array.from({ length: MAX_ROWS }, (_, i) => [i])
    const runQuery = vi.fn(() => ({ columns: ['id'], rows }))
    const out = executeSql('SELECT id FROM rewind_frames', runQuery)
    expect(out).not.toMatch(/Auto-limited/i)
  })
})

describe('executeReadOnlySql DoS protections (agent surface)', () => {
  const allowlist = new Set(['rewind_frames', 'memories'])
  it('rejects a recursive-CTE bomb, runner never called', () => {
    const runQuery = vi.fn(() => ({ columns: [], rows: [] }))
    const out = executeReadOnlySql(
      'WITH RECURSIVE r AS (SELECT 1 AS x UNION ALL SELECT x+1 FROM r) SELECT max(x) FROM r',
      runQuery,
      allowlist
    )
    expect(out).toMatch(/recursive/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects a cartesian join of allowlisted tables, runner never called', () => {
    const runQuery = vi.fn(() => ({ columns: [], rows: [] }))
    const out = executeReadOnlySql(
      'SELECT count(*) FROM memories a, memories b',
      runQuery,
      allowlist
    )
    expect(out).toMatch(/cartesian/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('still wraps a valid query in the unsuppressible outer LIMIT', () => {
    const runQuery = vi.fn((_sql: string) => ({ columns: ['n'], rows: [[1]] }))
    executeReadOnlySql('SELECT count(*) n FROM memories', runQuery, allowlist)
    expect(runQuery.mock.calls[0][0]).toBe(
      `SELECT * FROM (SELECT count(*) n FROM memories) LIMIT ${ROW_FETCH_CAP}`
    )
  })
})

describe('loadScreenshotBase64', () => {
  const frame = {
    id: 5,
    ts: 1,
    app: 'X',
    windowTitle: '',
    processName: '',
    ocrText: '',
    imagePath: '/f.jpg',
    width: 0,
    height: 0,
    indexed: 1
  }
  it('returns base64 for a found frame', async () => {
    const b = await loadScreenshotBase64(5, {
      getFramesByIds: () => [frame],
      readImageBase64: async () => 'BASE64'
    })
    expect(b).toBe('BASE64')
  })
  it('returns null when the frame is not in the DB', async () => {
    const b = await loadScreenshotBase64(5, {
      getFramesByIds: () => [],
      readImageBase64: async () => 'BASE64'
    })
    expect(b).toBeNull()
  })
  it('returns null when the image is missing on disk', async () => {
    const b = await loadScreenshotBase64(5, {
      getFramesByIds: () => [frame],
      readImageBase64: async () => null
    })
    expect(b).toBeNull()
  })
})

// --- FIX 4(b): the execute_sql denylist closure ------------------------------

describe('buildDenyFilter', () => {
  it('is empty when there are no usable terms', () => {
    expect(buildDenyFilter([])).toBe('')
    expect(buildDenyFilter(['   ', ''])).toBe('')
  })
  it('emits one NOT LIKE per term over the concatenated identity columns', () => {
    expect(buildDenyFilter(['Signal'])).toBe(
      "(app || ' ' || window_title || ' ' || process_name) NOT LIKE '%Signal%' ESCAPE '\\'"
    )
    expect(buildDenyFilter(['a', 'b'])).toContain(' AND ')
  })
  it('escapes LIKE metacharacters and embedded quotes so a term matches literally', () => {
    expect(buildDenyFilter(["100%_o'clock"])).toBe(
      "(app || ' ' || window_title || ' ' || process_name) NOT LIKE '%100\\%\\_o''clock%' ESCAPE '\\'"
    )
  })
})

describe('applyDenylistShadow', () => {
  it('is a no-op with no usable terms', () => {
    expect(applyDenylistShadow('SELECT 1', [])).toBe('SELECT 1')
  })
  it('prepends a filtered CTE for a plain SELECT', () => {
    const out = applyDenylistShadow('SELECT app FROM rewind_frames', ['Signal'])
    expect(out.startsWith('WITH rewind_frames AS (SELECT * FROM main.rewind_frames WHERE ')).toBe(
      true
    )
    expect(out.endsWith('SELECT app FROM rewind_frames')).toBe(true)
  })
  it('merges ahead of an existing WITH', () => {
    const out = applyDenylistShadow('WITH x AS (SELECT 1) SELECT * FROM x', ['Signal'])
    expect(out).toMatch(/^WITH rewind_frames AS \(.*\), x AS \(SELECT 1\) SELECT \* FROM x$/s)
  })
  it('merges after WITH RECURSIVE, keeping RECURSIVE first', () => {
    const out = applyDenylistShadow('WITH RECURSIVE r AS (SELECT 1) SELECT * FROM r', ['Signal'])
    expect(out).toMatch(/^WITH RECURSIVE rewind_frames AS \(.*\), r AS/s)
  })
  it('detects a WITH hidden behind a leading comment', () => {
    const out = applyDenylistShadow('/* c */ WITH x AS (SELECT 1) SELECT * FROM x', ['Signal'])
    expect(out).toMatch(/WITH rewind_frames AS \(.*\), x AS/s)
  })
})

describe('executeSql under an active denylist', () => {
  it('leaves the query unchanged when the denylist is empty', () => {
    const runQuery = vi.fn(() => ({ columns: ['app'], rows: [['X']] }))
    executeSql('SELECT app FROM rewind_frames', runQuery, [])
    expect(runQuery).toHaveBeenCalledWith(
      `SELECT * FROM (SELECT app FROM rewind_frames) LIMIT ${ROW_FETCH_CAP}`
    )
  })
  it('shadows rewind_frames with a filtered CTE before running', () => {
    const runQuery = vi.fn((_sql: string) => ({ columns: ['app'], rows: [] as unknown[][] }))
    executeSql('SELECT app FROM rewind_frames', runQuery, ['Signal'])
    const sql = runQuery.mock.calls[0][0]
    // Shadowed (filtered CTE) AND wrapped in the unsuppressible outer LIMIT.
    expect(sql).toContain('WITH rewind_frames AS (SELECT * FROM main.rewind_frames WHERE')
    expect(sql).toContain('SELECT app FROM rewind_frames')
    expect(sql.startsWith('SELECT * FROM (WITH rewind_frames AS')).toBe(true)
    expect(sql.endsWith(`) LIMIT ${ROW_FETCH_CAP}`)).toBe(true)
  })
  it('rejects the FTS mirror (it cannot be shadow-filtered) before running', () => {
    const runQuery = vi.fn()
    const out = executeSql(
      "SELECT ocr_text FROM rewind_frames_fts WHERE rewind_frames_fts MATCH 'x'",
      runQuery,
      ['Signal']
    )
    expect(out).toMatch(/only the rewind_frames table is queryable/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects a schema-qualified ref that would bypass the CTE, before running', () => {
    const runQuery = vi.fn()
    const out = executeSql("SELECT ocr_text FROM main.rewind_frames WHERE app='Signal'", runQuery, [
      'Signal'
    ])
    expect(out).toMatch(/only the rewind_frames table is queryable/i)
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('rejects a schema-qualified ref hidden in a subquery', () => {
    const runQuery = vi.fn()
    executeSql('SELECT * FROM (SELECT * FROM main.rewind_frames) t', runQuery, ['Signal'])
    expect(runQuery).not.toHaveBeenCalled()
  })
  it('still allows an unqualified CTE that reads rewind_frames', () => {
    const runQuery = vi.fn(() => ({ columns: ['app'], rows: [] }))
    executeSql('WITH r AS (SELECT app FROM rewind_frames) SELECT app FROM r', runQuery, ['Signal'])
    expect(runQuery).toHaveBeenCalledTimes(1)
  })
})

describe('executeSql denylist closure (real SQLite)', () => {
  // rewind_frames DDL verbatim from db.ts get(); better-sqlite3 can't load under
  // vitest, so — same node:sqlite pattern as rewindFtsSearch.test.ts — the DDL is
  // replicated while the LOGIC under test (executeSql + applyDenylistShadow) is the
  // REAL exported code driven against a real engine.
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
  function makeDb(): DatabaseSync {
    const db = new DatabaseSync(':memory:')
    db.exec(SCHEMA)
    const ins = db.prepare(
      'INSERT INTO rewind_frames (ts, app, window_title, process_name, ocr_text, image_path) VALUES (?, ?, ?, ?, ?, ?)'
    )
    ins.run(1, 'Signal', 'John Doe', 'Signal.exe', 'SECRET signal message', '/1.jpg')
    ins.run(2, 'Chrome', 'Docs', 'chrome.exe', 'ordinary web page', '/2.jpg')
    ins.run(3, 'Chrome', 'signal group chat', 'chrome.exe', 'TITLELEAK denied in title', '/3.jpg')
    return db
  }
  function runnerFor(db: DatabaseSync): QueryRunner {
    return (sql) => {
      const rows = db.prepare(sql).all() as Record<string, unknown>[]
      const columns = rows.length ? Object.keys(rows[0]) : []
      return { columns, rows: rows.map((r) => Object.values(r)) }
    }
  }

  it('a WHERE app=<denied> query physically returns no rows', () => {
    const db = makeDb()
    const out = executeSql("SELECT ocr_text FROM rewind_frames WHERE app='Signal'", runnerFor(db), [
      'Signal'
    ])
    expect(out).toBe('No results')
    expect(out).not.toContain('SECRET')
    db.close()
  })
  it('excludes a denied term that appears only in the window title (matches the frame gate)', () => {
    const db = makeDb()
    const out = executeSql('SELECT app, ocr_text FROM rewind_frames ORDER BY ts', runnerFor(db), [
      'Signal'
    ])
    expect(out).toContain('ordinary web page') // the one allowed row survives
    expect(out).not.toContain('SECRET') // app match excluded
    expect(out).not.toContain('TITLELEAK') // window-title match excluded too
    db.close()
  })
  it('is case-insensitive: denylist "signal" excludes app "Signal"', () => {
    const db = makeDb()
    const out = executeSql('SELECT ocr_text FROM rewind_frames', runnerFor(db), ['signal'])
    expect(out).not.toContain('SECRET')
    db.close()
  })
  it('an empty denylist returns the denied row unchanged (baseline)', () => {
    const db = makeDb()
    const out = executeSql(
      "SELECT ocr_text FROM rewind_frames WHERE app='Signal'",
      runnerFor(db),
      []
    )
    expect(out).toContain('SECRET signal message')
    db.close()
  })
})
