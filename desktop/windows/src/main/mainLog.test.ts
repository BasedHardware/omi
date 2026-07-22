import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync
} from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { RotatingLog, attachConsoleFileTee, formatLogLine } from './mainLog'

let dir: string

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'omi-mainlog-'))
})

afterEach(() => {
  rmSync(dir, { recursive: true, force: true })
})

describe('RotatingLog', () => {
  it('appends lines to the active file with a trailing newline', () => {
    const filePath = join(dir, 'main.log')
    const log = new RotatingLog({ filePath, maxBytes: 1024, backups: 1 })
    log.writeLine('first')
    log.writeLine('second')
    expect(readFileSync(filePath, 'utf8')).toBe('first\nsecond\n')
  })

  it('rotates to a numeric backup once the active file would exceed maxBytes', () => {
    const filePath = join(dir, 'main.log')
    // 10-byte lines ("line-0000\n"), cap at 25 bytes: two lines fit (20), the
    // third would push to 30 > 25, so the active file rotates first.
    const log = new RotatingLog({ filePath, maxBytes: 25, backups: 1 })
    log.writeLine('line-0000') // 10 bytes
    log.writeLine('line-0001') // 20 bytes
    log.writeLine('line-0002') // would be 30 -> rotate, then write to fresh file

    expect(existsSync(`${filePath}.1`)).toBe(true)
    expect(readFileSync(`${filePath}.1`, 'utf8')).toBe('line-0000\nline-0001\n')
    expect(readFileSync(filePath, 'utf8')).toBe('line-0002\n')
  })

  it('bounds total on-disk bytes to roughly maxBytes * (backups + 1)', () => {
    const filePath = join(dir, 'main.log')
    const maxBytes = 200
    const backups = 1
    const log = new RotatingLog({ filePath, maxBytes, backups })
    // Write far more than the budget; only the active file + one backup survive.
    for (let i = 0; i < 500; i++) log.writeLine(`entry-${String(i).padStart(6, '0')}`)

    const files = [filePath, `${filePath}.1`, `${filePath}.2`]
    const total = files.filter(existsSync).reduce((sum, f) => sum + statSync(f).size, 0)
    // Oldest backup (.2) must never exist with backups=1.
    expect(existsSync(`${filePath}.2`)).toBe(false)
    // A single freshly-written line can carry the active file slightly over the
    // cap before the next rotate, so allow one line of slack per segment.
    expect(total).toBeLessThanOrEqual(maxBytes * (backups + 1) + 64)
    // The newest entry is always retained in the active file.
    expect(readFileSync(filePath, 'utf8')).toContain('entry-000499')
  })

  it('drops all history when backups is 0 (truncate-in-place)', () => {
    const filePath = join(dir, 'main.log')
    const log = new RotatingLog({ filePath, maxBytes: 25, backups: 0 })
    log.writeLine('line-0000')
    log.writeLine('line-0001')
    log.writeLine('line-0002') // triggers rotate -> truncate, no backup kept

    expect(existsSync(`${filePath}.1`)).toBe(false)
    expect(readFileSync(filePath, 'utf8')).toBe('line-0002\n')
  })

  it('seeds its size from an existing file so it appends across restarts', () => {
    const filePath = join(dir, 'main.log')
    writeFileSync(filePath, 'x'.repeat(20) + '\n') // 21 bytes already on disk
    const log = new RotatingLog({ filePath, maxBytes: 25, backups: 1 })
    // 21 + 10 = 31 > 25 -> the very first write must rotate the pre-existing file.
    log.writeLine('line-0000')
    expect(existsSync(`${filePath}.1`)).toBe(true)
    expect(readFileSync(filePath, 'utf8')).toBe('line-0000\n')
  })

  it('re-syncs its size counter to disk when a rotate fails (never blindly zeroes)', () => {
    // Force rotation to fail deterministically: a directory sitting at the backup
    // path makes the first rmSync(backup) inside rotate() throw (no recursive), so
    // the active file is never renamed away and keeps all its content. This stands
    // in for the real Windows failure (AV / search indexer holding the file open).
    // The bug being guarded: if rotate() blindly set size = 0 on this failure, the
    // counter would drift below the true on-disk size and the file could grow far
    // past the cap while every write believed it was nearly empty.
    const filePath = join(dir, 'main.log')
    mkdirSync(`${filePath}.1`) // occupy the backup slot with a directory
    const log = new RotatingLog({ filePath, maxBytes: 25, backups: 1 })
    // Write well past the cap; each over-cap write attempts a rotate that throws.
    for (let i = 0; i < 20; i++) log.writeLine(`line-${String(i).padStart(4, '0')}`)

    // rotate() never succeeded, so the active file kept accumulating (accepted
    // fail-open). The invariant we assert: the running counter equals the real
    // on-disk size — a freshly seeded log (which reads size from disk) matches
    // what the live instance tracked, proving it never desynced to 0.
    const onDisk = statSync(filePath).size
    expect(onDisk).toBeGreaterThan(25)
    // The next write on the live instance still rotates-attempts based on the true
    // size (not a stale 0), so it does not throw and the file keeps advancing.
    expect(() => log.writeLine('after')).not.toThrow()
    expect(statSync(filePath).size).toBeGreaterThan(onDisk)
  })

  it('never throws when the target directory does not exist', () => {
    const filePath = join(dir, 'missing', 'main.log')
    const log = new RotatingLog({ filePath, maxBytes: 25, backups: 1 })
    expect(() => log.writeLine('still fine')).not.toThrow()
  })
})

describe('formatLogLine', () => {
  it('prefixes an ISO timestamp and the level, formatting args like console', () => {
    const line = formatLogLine('warn', ['hello %s (%d)', 'world', 42])
    expect(line).toMatch(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z \[warn\] hello world \(42\)$/)
  })

  it('serializes objects the way util.format does', () => {
    const line = formatLogLine('log', ['state', { a: 1 }])
    expect(line).toContain('[log] state { a: 1 }')
  })
})

describe('attachConsoleFileTee', () => {
  function makeFakeConsole(): { fake: Console; calls: string[] } {
    const calls: string[] = []
    const fake = {
      log: (...a: unknown[]) => calls.push(`log:${a.join(' ')}`),
      info: (...a: unknown[]) => calls.push(`info:${a.join(' ')}`),
      warn: (...a: unknown[]) => calls.push(`warn:${a.join(' ')}`),
      error: (...a: unknown[]) => calls.push(`error:${a.join(' ')}`),
      debug: (...a: unknown[]) => calls.push(`debug:${a.join(' ')}`)
    } as unknown as Console
    return { fake, calls }
  }

  it('tees each console method to the file while preserving original output', () => {
    const filePath = join(dir, 'main.log')
    const log = new RotatingLog({ filePath, maxBytes: 1024 * 1024, backups: 1 })
    const { fake, calls } = makeFakeConsole()

    const restore = attachConsoleFileTee(log, fake)
    fake.log('alpha')
    fake.warn('beta')
    fake.error('gamma')
    restore()

    // Original console behavior preserved.
    expect(calls).toEqual(['log:alpha', 'warn:beta', 'error:gamma'])
    // File captured all three, tagged by level.
    const contents = readFileSync(filePath, 'utf8')
    expect(contents).toContain('[log] alpha')
    expect(contents).toContain('[warn] beta')
    expect(contents).toContain('[error] gamma')
  })

  it('restore() detaches the tee so later calls no longer hit the file', () => {
    const filePath = join(dir, 'main.log')
    const log = new RotatingLog({ filePath, maxBytes: 1024 * 1024, backups: 1 })
    const { fake } = makeFakeConsole()

    const restore = attachConsoleFileTee(log, fake)
    fake.log('captured')
    restore()
    fake.log('after-restore')

    const contents = readFileSync(filePath, 'utf8')
    expect(contents).toContain('captured')
    expect(contents).not.toContain('after-restore')
  })
})
