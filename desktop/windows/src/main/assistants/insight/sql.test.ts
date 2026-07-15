import { describe, expect, it, vi } from 'vitest'
import {
  appendLimit,
  executeSql,
  formatRows,
  isReadOnlySql,
  loadScreenshotBase64,
  MAX_ROWS,
  CELL_CAP
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
    expect(isReadOnlySql("SELECT ocr_text FROM rewind_frames WHERE ocr_text LIKE '%delete%'")).toBe(true)
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE window_title LIKE '%Create%'")).toBe(true)
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE ocr_text LIKE '%update%'")).toBe(true)
    expect(isReadOnlySql("SELECT id FROM rewind_frames WHERE ocr_text LIKE '%insert file%'")).toBe(true)
  })
  it('handles an escaped quote inside a literal and still allows it', () => {
    expect(isReadOnlySql("SELECT ocr_text FROM rewind_frames WHERE ocr_text LIKE '%it''s delete%'")).toBe(true)
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

describe('appendLimit', () => {
  it('appends LIMIT 200 when absent', () => {
    expect(appendLimit('SELECT * FROM rewind_frames')).toBe('SELECT * FROM rewind_frames LIMIT 200')
  })
  it('leaves an existing LIMIT alone and strips a trailing ;', () => {
    expect(appendLimit('SELECT * FROM rewind_frames LIMIT 5;')).toBe(
      'SELECT * FROM rewind_frames LIMIT 5'
    )
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
  it('auto-appends LIMIT and passes the query to the runner', () => {
    const runQuery = vi.fn(() => ({ columns: ['id'], rows: [[1]] }))
    const out = executeSql('SELECT id FROM rewind_frames', runQuery)
    expect(runQuery).toHaveBeenCalledWith('SELECT id FROM rewind_frames LIMIT 200')
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
    expect(runQuery).toHaveBeenCalledWith('SELECT app FROM rewind_frames LIMIT 200')
  })
  it('allows the FTS mirror table and a rewind_frames↔fts join', () => {
    const runQuery = vi.fn(() => ({ columns: ['id'], rows: [[1]] }))
    executeSql("SELECT rowid FROM rewind_frames_fts WHERE rewind_frames_fts MATCH 'foo'", runQuery)
    expect(runQuery).toHaveBeenCalledTimes(1)
    executeSql('SELECT f.id FROM rewind_frames f JOIN rewind_frames_fts x ON x.rowid = f.id', runQuery)
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
