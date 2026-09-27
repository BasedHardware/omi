import { describe, it, expect, afterAll, vi } from 'vitest'
import {
  mkdtempSync,
  writeFileSync,
  readFileSync,
  readdirSync,
  rmSync,
  existsSync,
  mkdirSync,
  symlinkSync,
  lstatSync,
  chmodSync
} from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { atomicWriteFileSync } from './atomicWrite'

// fs' ESM namespace can't be spied on; wrap fsyncSync in a module mock whose
// failure is switched per-test. Everything else delegates to the real fs.
const mocks = vi.hoisted(() => ({ fsyncShouldFail: false }))
vi.mock('fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('fs')>()
  return {
    ...actual,
    fsyncSync: (fd: number) => {
      if (mocks.fsyncShouldFail) throw new Error('simulated fsync failure')
      return actual.fsyncSync(fd)
    }
  }
})

const dir = mkdtempSync(join(tmpdir(), 'atomic-write-test-'))
afterAll(() => rmSync(dir, { recursive: true, force: true }))

function tempsIn(d: string): string[] {
  return readdirSync(d).filter((f) => f.includes('.omi-tmp-'))
}

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
    expect(tempsIn(dir)).toEqual([])
  })

  it('on a failing write (missing parent dir) it throws and leaves no partial file', () => {
    const p = join(dir, 'does', 'not', 'exist', 'd.txt')
    expect(() => atomicWriteFileSync(p, 'x')).toThrow()
    expect(existsSync(p)).toBe(false)
    // No stray temp left in the (nonexistent) target dir either.
    expect(tempsIn(dir)).toEqual([])
  })

  it('writes through a symlink to the REAL file and keeps the link', () => {
    if (process.platform === 'win32') return // symlink needs privileges on Windows
    const sub = join(dir, 'symlinked')
    mkdirSync(sub, { recursive: true })
    const real = join(sub, 'real.json')
    const link = join(sub, 'link.json')
    writeFileSync(real, 'old', 'utf8')
    symlinkSync(real, link)
    atomicWriteFileSync(link, 'new')
    expect(readFileSync(real, 'utf8')).toBe('new')
    // The link itself still points at the real file (not replaced by a file).
    expect(lstatSync(link).isSymbolicLink()).toBe(true)
    expect(readFileSync(link, 'utf8')).toBe('new')
    expect(tempsIn(sub)).toEqual([])
  })

  it('refuses a BROKEN symlink — the link is left untouched', () => {
    if (process.platform === 'win32') return
    const sub = join(dir, 'broken-link')
    mkdirSync(sub, { recursive: true })
    const link = join(sub, 'dangling.json')
    symlinkSync(join(sub, 'missing-target.json'), link)
    expect(() => atomicWriteFileSync(link, 'x')).toThrow()
    expect(lstatSync(link).isSymbolicLink()).toBe(true) // still a link
    expect(existsSync(join(sub, 'missing-target.json'))).toBe(false)
    expect(tempsIn(sub)).toEqual([])
  })

  it('on an fsync failure it throws, keeps the original, and leaves no residue', () => {
    const sub = join(dir, 'fsync-fail')
    mkdirSync(sub, { recursive: true })
    const p = join(sub, 'e.txt')
    writeFileSync(p, 'original', 'utf8')
    mocks.fsyncShouldFail = true
    try {
      expect(() => atomicWriteFileSync(p, 'new')).toThrow(/fsync/)
    } finally {
      mocks.fsyncShouldFail = false
    }
    expect(readFileSync(p, 'utf8')).toBe('original')
    expect(tempsIn(sub)).toEqual([])
  })

  it('on a permission-denied target dir it throws and leaves no residue', () => {
    if (process.platform === 'win32') return
    const sub = join(dir, 'no-write')
    mkdirSync(sub, { recursive: true })
    const p = join(sub, 'f.txt')
    writeFileSync(p, 'original', 'utf8')
    chmodSync(sub, 0o555)
    try {
      expect(() => atomicWriteFileSync(p, 'new')).toThrow()
      expect(readFileSync(p, 'utf8')).toBe('original')
      expect(tempsIn(sub)).toEqual([])
    } finally {
      chmodSync(sub, 0o755)
    }
  })
})
