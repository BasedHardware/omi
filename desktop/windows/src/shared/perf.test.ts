import { it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { perfMark, flushPerfMarks } from './perf'

let dir: string

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'perf-'))
  process.env.OMI_PERF_LOG = join(dir, 'perf.jsonl')
})

afterEach(() => {
  delete process.env.OMI_PERF_LOG
  rmSync(dir, { recursive: true, force: true })
})

it('writes one JSON line per mark after flush', () => {
  perfMark('app:start')
  perfMark('db:listX', { ms: 1.5 })
  flushPerfMarks()
  const lines = readFileSync(process.env.OMI_PERF_LOG!, 'utf8').trim().split('\n')
  expect(lines).toHaveLength(2)
  const first = JSON.parse(lines[0])
  const second = JSON.parse(lines[1])
  expect(first.name).toBe('app:start')
  expect(typeof first.mono).toBe('number')
  expect(typeof first.ts).toBe('number')
  expect(second.name).toBe('db:listX')
  expect(second.meta.ms).toBe(1.5)
})

it('is a no-op when OMI_PERF_LOG is unset', () => {
  delete process.env.OMI_PERF_LOG
  expect(() => {
    perfMark('app:start')
    flushPerfMarks()
  }).not.toThrow()
  expect(existsSync(join(dir, 'perf.jsonl'))).toBe(false)
})
