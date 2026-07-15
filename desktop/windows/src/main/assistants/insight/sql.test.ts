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
