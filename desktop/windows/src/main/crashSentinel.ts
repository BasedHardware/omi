// Clean-shutdown sentinel — crash detection across launches.
//
// Windows cannot tell a crash from a clean exit on the NEXT launch: a hard crash,
// an OS kill, or a main-process death that bypasses uncaughtException all just
// leave the process gone, with nothing recorded. macOS solves this with
// `lastSessionCleanExit` (a UserDefaults bool cleared to dirty at every launch and
// set clean only in applicationWillTerminate) + AnalyticsManager.detectAndReportCrash,
// which fires a Sentry MESSAGE — developer-facing telemetry only, no user-visible
// banner or recovery UI. This mirrors that shape:
//
//   - On boot: read the persisted flag. If the PREVIOUS session left it dirty
//     (wrote "running" but never reached the quit path), report a crash to Sentry
//     as a message (not an exception, no banner). Then mark THIS session dirty.
//   - On the real quit path (will-quit): mark the flag clean.
//
// The flag is written EAGERLY and synchronously, so a hard crash — which never
// reaches markCleanExit — leaves it dirty and is correctly detected next launch.
// A normal quit writes clean, so the next launch does NOT report: only an actual
// crash (flag left dirty) reports, never a double-count.
import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import { captureMessage } from './sentry'

export type Sentinel = { cleanExit: boolean }

/**
 * Pure: did the previous session crash? A missing sentinel (first launch ever, or
 * a freshly wiped profile) is NOT a crash — only an explicit dirty flag counts
 * (the previous launch wrote "running" but never wrote "clean"). This is what
 * keeps a first run from reporting a phantom crash.
 */
export function previousSessionCrashed(prev: Sentinel | null): boolean {
  return prev?.cleanExit === false
}

export type SentinelDeps = {
  /** Read + parse the persisted sentinel; null when absent/corrupt. */
  read: () => Sentinel | null
  /** Persist the sentinel synchronously. */
  write: (s: Sentinel) => void
  /** Report the detected crash (Sentry message). Called at most once per boot. */
  report: () => void
}

/**
 * Pure orchestration (deps injected for tests): report a crash if the previous
 * session was left dirty, then mark THIS session dirty/running. Returns whether a
 * crash was detected on this boot. Marking dirty eagerly is the whole mechanism —
 * a session that dies before markCleanExit stays dirty and is caught next launch.
 */
export function runCrashDetection(deps: SentinelDeps): boolean {
  const crashed = previousSessionCrashed(deps.read())
  if (crashed) deps.report()
  deps.write({ cleanExit: false })
  return crashed
}

function sentinelFile(): string {
  return join(app.getPath('userData'), 'clean-exit-sentinel.json')
}

// Exported so a test can feed real garbage / truncated JSON / valid content
// through the REAL parse+degrade path against a real file (not the injected-deps
// mock) — the "corrupt → null → no report" safety is the recurring lesson this
// program keeps relearning, so it's asserted by running I/O, not just reasoning.
export function readSentinelFile(): Sentinel | null {
  try {
    const raw = JSON.parse(readFileSync(sentinelFile(), 'utf-8')) as Partial<Sentinel>
    return typeof raw?.cleanExit === 'boolean' ? { cleanExit: raw.cleanExit } : null
  } catch {
    // Missing or corrupt → treat as absent (no crash report). Never throw from
    // the crash path.
    return null
  }
}

export function writeSentinelFile(s: Sentinel): void {
  try {
    writeFileSync(sentinelFile(), JSON.stringify(s), 'utf-8')
  } catch {
    /* best-effort; a sentinel we can't write just means the next launch can't
       distinguish this session's exit — never worth throwing over. */
  }
}

let bootCrashDetected = false

/**
 * Wire the real deps and run detection once at startup. Must run AFTER Sentry init
 * (so a detected crash can report) and AFTER the single-instance lock (so a losing
 * duplicate process never reads/rewrites the live instance's sentinel). Returns
 * whether a crash was detected this boot.
 */
export function initCrashSentinel(): boolean {
  bootCrashDetected = runCrashDetection({
    read: readSentinelFile,
    write: writeSentinelFile,
    report: () => captureMessage('App crash detected', { area: 'lifecycle-crash', level: 'error' })
  })
  return bootCrashDetected
}

/** Whether the previous session was detected as a crash on this boot (E2E/debug). */
export function crashDetectedOnBoot(): boolean {
  return bootCrashDetected
}

/** Mark a clean exit on the real quit path. Cheap synchronous write — call early
 *  in will-quit, before the heavier teardown. */
export function markCleanExit(): void {
  writeSentinelFile({ cleanExit: true })
}
