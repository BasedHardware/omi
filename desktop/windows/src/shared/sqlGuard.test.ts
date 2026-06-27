import { describe, it, expect } from 'vitest'
import { guardSelect } from './sqlGuard'

describe('guardSelect', () => {
  it('accepts a plain SELECT and appends a LIMIT', () => {
    expect(guardSelect('SELECT label FROM local_kg_nodes')).toBe(
      'SELECT label FROM local_kg_nodes LIMIT 200'
    )
  })
  it('accepts WITH (CTE) queries', () => {
    const sql = 'WITH t AS (SELECT 1) SELECT * FROM t'
    expect(guardSelect(sql)).toBe(`${sql} LIMIT 200`)
  })
  it('keeps an existing LIMIT when <= cap', () => {
    expect(guardSelect('SELECT 1 LIMIT 10')).toBe('SELECT 1 LIMIT 10')
  })
  it('caps an oversized LIMIT', () => {
    expect(guardSelect('SELECT 1 LIMIT 99999')).toBe('SELECT 1 LIMIT 200')
  })
  it('preserves a trailing OFFSET and does not double-append', () => {
    expect(guardSelect('SELECT 1 LIMIT 50 OFFSET 10')).toBe('SELECT 1 LIMIT 50 OFFSET 10')
    expect(guardSelect('SELECT 1 LIMIT 99999 OFFSET 3')).toBe('SELECT 1 LIMIT 200 OFFSET 3')
  })
  it('handles the LIMIT offset, count form', () => {
    expect(guardSelect('SELECT 1 LIMIT 10, 5')).toBe('SELECT 1 LIMIT 10, 5')
    expect(guardSelect('SELECT 1 LIMIT 10, 99999')).toBe('SELECT 1 LIMIT 10, 200')
  })
  it('does not append a second LIMIT when one is nested in a subquery', () => {
    const sql = 'SELECT * FROM (SELECT x FROM y LIMIT 5) t'
    expect(guardSelect(sql)).toBe(sql)
  })
  it('rejects load_extension / writefile / readfile', () => {
    expect(() => guardSelect("SELECT load_extension('evil.dll')")).toThrow()
    expect(() => guardSelect("SELECT writefile('/tmp/x', 'data')")).toThrow()
    expect(() => guardSelect("SELECT readfile('/etc/passwd')")).toThrow()
  })
  it('strips trailing semicolons', () => {
    expect(guardSelect('SELECT 1;')).toBe('SELECT 1 LIMIT 200')
  })
  it('rejects writes and DDL', () => {
    for (const q of [
      'DELETE FROM local_kg_nodes',
      'UPDATE local_kg_nodes SET label=1',
      'INSERT INTO x VALUES (1)',
      'DROP TABLE indexed_files',
      'ALTER TABLE x ADD COLUMN y',
      'CREATE TABLE x (a)',
      'ATTACH DATABASE ":memory:" AS z',
      'PRAGMA table_info(x)'
    ]) {
      expect(() => guardSelect(q)).toThrow()
    }
  })
  it('rejects multiple statements (stacked write)', () => {
    expect(() => guardSelect('SELECT 1; DROP TABLE x')).toThrow()
  })
  it('rejects a write hidden behind a comment', () => {
    expect(() => guardSelect('SELECT 1 -- ok\n; DROP TABLE x')).toThrow()
    expect(() => guardSelect('/* SELECT */ DELETE FROM x')).toThrow()
  })
  it('rejects empty / non-select input', () => {
    expect(() => guardSelect('   ')).toThrow()
    expect(() => guardSelect('EXPLAIN SELECT 1')).toThrow()
  })
})
