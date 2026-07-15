import { describe, it, expect, vi } from 'vitest'

// The pure functions under test take injected deps and touch neither electron nor
// Sentry — but the module's file-backed wiring imports both at the top. Stub them
// so importing the module doesn't pull the native electron binary / Sentry SDK
// (matching appSettings.test.ts's local electron mock).
vi.mock('electron', () => ({ app: { getPath: (): string => '/tmp' } }))
vi.mock('./sentry', () => ({ captureMessage: (): void => {} }))

import {
  previousSessionCrashed,
  runCrashDetection,
  type Sentinel,
  type SentinelDeps
} from './crashSentinel'

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
