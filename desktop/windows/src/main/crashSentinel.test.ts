import { describe, it, expect, vi, afterAll, beforeEach } from 'vitest'
import { mkdtempSync, writeFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Point the module's userData at a REAL throwaway temp dir so the file-backed
// read/write path (readSentinelFile / writeSentinelFile) exercises real I/O — the
// "corrupt/partial → null → no report" degradation must be proven by feeding real
// garbage through the real parse, not asserted in reasoning (this program's
// recurring SQL-test-drift lesson). getPath dereferences tmpDir lazily (only when
// the tests call it), so referencing it in the hoisted mock is safe — same pattern
// as appSettings.test.ts. Sentry is stubbed so importing the module doesn't pull
// the native SDK.
const tmpDir = mkdtempSync(join(tmpdir(), 'omi-crashsentinel-'))
vi.mock('electron', () => ({ app: { getPath: (): string => tmpDir } }))
vi.mock('./sentry', () => ({ captureMessage: (): void => {} }))

import {
  previousSessionCrashed,
  runCrashDetection,
  readSentinelFile,
  writeSentinelFile,
  type Sentinel,
  type SentinelDeps
} from './crashSentinel'

const sentinelPath = join(tmpDir, 'clean-exit-sentinel.json')
afterAll(() => rmSync(tmpDir, { recursive: true, force: true }))

describe('previousSessionCrashed', () => {
  it('treats a missing sentinel (first launch / wiped profile) as NOT a crash', () => {
    expect(previousSessionCrashed(null)).toBe(false)
  })

  it('treats a clean previous exit as NOT a crash', () => {
    expect(previousSessionCrashed({ cleanExit: true })).toBe(false)
  })

  it('treats a dirty previous exit as a crash', () => {
    expect(previousSessionCrashed({ cleanExit: false })).toBe(true)
  })
})

describe('runCrashDetection', () => {
  // A tiny in-memory sentinel store so the orchestration is exercised end-to-end
  // (read → maybe report → write) without touching the filesystem or electron.
  function makeDeps(initial: Sentinel | null): {
    deps: SentinelDeps
    report: ReturnType<typeof vi.fn>
    stored: () => Sentinel | null
  } {
    let stored = initial
    const report = vi.fn()
    return {
      deps: {
        read: () => stored,
        write: (s) => {
          stored = s
        },
        report
      },
      report,
      stored: () => stored
    }
  }

  it('clean previous exit → no report, and marks this session dirty', () => {
    const { deps, report, stored } = makeDeps({ cleanExit: true })
    const crashed = runCrashDetection(deps)
    expect(crashed).toBe(false)
    expect(report).not.toHaveBeenCalled()
    // The whole mechanism: this session is now dirty until a clean quit flips it.
    expect(stored()).toEqual({ cleanExit: false })
  })

  it('dirty previous exit → reports exactly once, and marks this session dirty', () => {
    const { deps, report, stored } = makeDeps({ cleanExit: false })
    const crashed = runCrashDetection(deps)
    expect(crashed).toBe(true)
    expect(report).toHaveBeenCalledTimes(1)
    expect(stored()).toEqual({ cleanExit: false })
  })

  it('first launch (no sentinel) → no report, and still marks this session dirty', () => {
    const { deps, report, stored } = makeDeps(null)
    const crashed = runCrashDetection(deps)
    expect(crashed).toBe(false)
    expect(report).not.toHaveBeenCalled()
    expect(stored()).toEqual({ cleanExit: false })
  })

  it('does not double-count: a clean exit after a detected crash reports only the crash', () => {
    // Boot 1 finds a crash (dirty) and reports once; session marked dirty.
    const { deps, report, stored } = makeDeps({ cleanExit: false })
    expect(runCrashDetection(deps)).toBe(true)
    expect(report).toHaveBeenCalledTimes(1)

    // App exits cleanly this time.
    deps.write({ cleanExit: true })
    expect(stored()).toEqual({ cleanExit: true })

    // Boot 2 sees the clean flag → no new report (still one total).
    expect(runCrashDetection(deps)).toBe(false)
    expect(report).toHaveBeenCalledTimes(1)
    expect(stored()).toEqual({ cleanExit: false })
  })
})

// Runs the REAL readSentinelFile / writeSentinelFile against a REAL file in the
// temp userData dir — the degradation layer the injected-deps tests above can't
// cover. Corrupt/partial JSON must degrade to null (no crash report), and only a
// genuinely dirty flag written to disk must be detected.
describe('readSentinelFile / writeSentinelFile — real file I/O', () => {
  beforeEach(() => {
    rmSync(sentinelPath, { force: true })
  })

  it('missing file → null (no report)', () => {
    expect(readSentinelFile()).toBeNull()
  })

  it('literal garbage → null (parse throws → degrades safe, never a false crash)', () => {
    writeFileSync(sentinelPath, 'this is not json at all {{{', 'utf-8')
    expect(readSentinelFile()).toBeNull()
  })

  it('truncated/partial JSON → null', () => {
    writeFileSync(sentinelPath, '{"cleanExit":', 'utf-8')
    expect(readSentinelFile()).toBeNull()
  })

  it('valid JSON without a boolean cleanExit → null (shape mismatch, not a crash)', () => {
    writeFileSync(sentinelPath, JSON.stringify({ cleanExit: 'nope' }), 'utf-8')
    expect(readSentinelFile()).toBeNull()
    writeFileSync(sentinelPath, JSON.stringify({ other: 1 }), 'utf-8')
    expect(readSentinelFile()).toBeNull()
  })

  it('valid {cleanExit:true} → read as clean → not detected as a crash', () => {
    writeFileSync(sentinelPath, JSON.stringify({ cleanExit: true }), 'utf-8')
    expect(readSentinelFile()).toEqual({ cleanExit: true })
    const report = vi.fn()
    expect(runCrashDetection({ read: readSentinelFile, write: writeSentinelFile, report })).toBe(
      false
    )
    expect(report).not.toHaveBeenCalled()
  })

  it('valid {cleanExit:false} on disk → detected exactly once, and boot rewrites dirty', () => {
    writeFileSync(sentinelPath, JSON.stringify({ cleanExit: false }), 'utf-8')
    expect(readSentinelFile()).toEqual({ cleanExit: false })
    const report = vi.fn()
    // Real read + real write + spy report: exercises the on-disk detection outcome.
    expect(runCrashDetection({ read: readSentinelFile, write: writeSentinelFile, report })).toBe(
      true
    )
    expect(report).toHaveBeenCalledTimes(1)
    // The boot's dirty write persisted through the real writeSentinelFile.
    expect(readSentinelFile()).toEqual({ cleanExit: false })
  })

  it('writeSentinelFile → readSentinelFile round-trips clean through real files', () => {
    writeSentinelFile({ cleanExit: true })
    expect(readSentinelFile()).toEqual({ cleanExit: true })
    writeSentinelFile({ cleanExit: false })
    expect(readSentinelFile()).toEqual({ cleanExit: false })
  })
})
