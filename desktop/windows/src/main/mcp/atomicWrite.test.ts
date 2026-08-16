import { describe, it, expect, afterAll } from 'vitest'
import { mkdtempSync, writeFileSync, readFileSync, readdirSync, rmSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { atomicWriteFileSync } from './atomicWrite'

const dir = mkdtempSync(join(tmpdir(), 'atomic-write-test-'))
afterAll(() => rmSync(dir, { recursive: true, force: true }))

describe('atomicWriteFileSync', () => {
  it('writes data and round-trips it', () => {
    const p = join(dir, 'a.json')
    atomicWriteFileSync(p, '{"x":1}')
    expect(readFileSync(p, 'utf8')).toBe('{"x":1}')
  })

  it('overwrites an existing file', () => {
    const p = join(dir, 'b.txt')
    writeFileSync(p, 'old', 'utf8')
    atomicWriteFileSync(p, 'new')
    expect(readFileSync(p, 'utf8')).toBe('new')
  })

  it('leaves NO temp file behind after a successful write', () => {
    const p = join(dir, 'c.txt')
    atomicWriteFileSync(p, 'hi')
    const temps = readdirSync(dir).filter((f) => f.includes('.omi-tmp-'))
    expect(temps).toEqual([])
  })

  it('on a failing write (missing parent dir) it throws and leaves no partial file', () => {
    const p = join(dir, 'does', 'not', 'exist', 'd.txt')
    expect(() => atomicWriteFileSync(p, 'x')).toThrow()
    expect(existsSync(p)).toBe(false)
    // No stray temp left in the (nonexistent) target dir either.
    const temps = readdirSync(dir).filter((f) => f.includes('.omi-tmp-'))
    expect(temps).toEqual([])
  })
})
