// Packaged builds emit all main-process console output to stdout, which is
// invisible for an installed app — so a packaged-only failure (an agent spawn,
// a provider error, a service crash) leaves nothing on the user's machine to
// diagnose from. crash.log only captures fatal lifecycle events. This module
// tees main-process console output to a size-bounded file under userData/logs
// so the ordinary log stream survives on disk, capped so it can never grow
// without bound.
//
// Redaction: this is a plumbing change, not a new log source. It captures the
// exact strings already passed to console — which callers sanitize before
// logging (e.g. sanitizeProcessDiagnostic in codingAgent/failures.ts) — so the
// file inherits the same redaction as stdout. Do not log new raw data here.

import { appendFileSync, mkdirSync, renameSync, rmSync, statSync } from 'fs'
import { join } from 'path'
import { format } from 'util'

const CONSOLE_METHODS = ['log', 'info', 'warn', 'error', 'debug'] as const
type ConsoleMethod = (typeof CONSOLE_METHODS)[number]

export interface RotatingLogOptions {
  /** Active log file path (rotated backups get a numeric suffix). */
  filePath: string
  /** Rotate once the active file would exceed this many bytes. */
  maxBytes: number
  /** Number of rotated backups to keep, each up to maxBytes. */
  backups: number
}

/**
 * A minimal size-bounded append log with numeric-suffix rotation. Total on-disk
 * bytes stay under roughly `maxBytes * (backups + 1)`. Synchronous by design:
 * a log line must survive a hard crash of the main process, so every write hits
 * disk immediately (matching crash.log's appendFileSync). All methods are
 * best-effort and never throw — a logger must not take the app down.
 */
export class RotatingLog {
  private readonly filePath: string
  private readonly maxBytes: number
  private readonly backups: number
  private size: number

  constructor(options: RotatingLogOptions) {
    this.filePath = options.filePath
    // Guard against a nonsensical cap that would rotate on every line.
    this.maxBytes = Math.max(1, options.maxBytes)
    this.backups = Math.max(0, options.backups)
    // Seed the running size from any existing file so logging appends across
    // restarts instead of resetting the rotation budget each launch.
    this.size = this.statSize(this.filePath)
  }

  /** Append one already-formatted line (a trailing newline is added). */
  writeLine(line: string): void {
    const payload = `${line}\n`
    const bytes = Buffer.byteLength(payload)
    // Rotate BEFORE writing when this line would push us past the cap — but never
    // rotate an empty active file (a single line larger than maxBytes still lands
    // in its own segment rather than being dropped).
    if (this.size > 0 && this.size + bytes > this.maxBytes) this.rotate()
    try {
      appendFileSync(this.filePath, payload)
      this.size += bytes
    } catch {
      /* best-effort; disk full / permissions must not crash the app */
    }
  }

  private rotate(): void {
    try {
      if (this.backups === 0) {
        // No backups kept: truncate by dropping the active file.
        rmSync(this.filePath, { force: true })
      } else {
        // Drop the oldest, then shift each backup up one slot: .(n-1) -> .n.
        rmSync(this.backupPath(this.backups), { force: true })
        for (let i = this.backups - 1; i >= 1; i--) {
          this.renameIfExists(this.backupPath(i), this.backupPath(i + 1))
        }
        this.renameIfExists(this.filePath, this.backupPath(1))
      }
    } catch {
      /* if rotation fails, keep appending to the active file rather than crash */
    }
    // Re-derive size from disk rather than assuming the active file is now empty.
    // rmSync/renameSync swallow their own errors (AV or a search indexer can hold
    // the file open on Windows), so on a FAILED rotate the file keeps its content;
    // zeroing the counter blindly would let it grow unbounded past the cap. After a
    // successful rotate the active file is gone, so statSize reads 0.
    this.size = this.statSize(this.filePath)
  }

  private backupPath(n: number): string {
    return `${this.filePath}.${n}`
  }

  private renameIfExists(from: string, to: string): void {
    try {
      renameSync(from, to)
    } catch {
      /* source may not exist yet; ignore */
    }
  }

  private statSize(path: string): number {
    try {
      return statSync(path).size
    } catch {
      return 0
    }
  }
}

/** Format a console call the way Node's console would, prefixed with an ISO
 * timestamp and level. Pure — exported for tests. */
export function formatLogLine(level: ConsoleMethod, args: unknown[]): string {
  const message = format(...(args as [unknown, ...unknown[]]))
  return `${new Date().toISOString()} [${level}] ${message}`
}

/**
 * Tee every console method on `target` into `log`, preserving the original
 * stdout/stderr behavior. Returns a restore function (used by tests). The
 * original methods are captured before patching so the file write can never
 * recurse through the patched console.
 */
export function attachConsoleFileTee(log: RotatingLog, target: Console = console): () => void {
  const originals = new Map<ConsoleMethod, (...args: unknown[]) => void>()
  for (const method of CONSOLE_METHODS) {
    const original = target[method].bind(target) as (...args: unknown[]) => void
    originals.set(method, target[method] as (...args: unknown[]) => void)
    target[method] = ((...args: unknown[]) => {
      original(...args)
      try {
        log.writeLine(formatLogLine(method, args))
      } catch {
        /* never let file logging break a console call */
      }
    }) as Console[ConsoleMethod]
  }
  return () => {
    for (const [method, fn] of originals) target[method] = fn as Console[ConsoleMethod]
  }
}

// ~5 MB per segment, one backup kept => ~10 MB total on disk.
const MAX_BYTES = 5 * 1024 * 1024
const BACKUPS = 1

let initialized = false

/**
 * Wire main-process console output to a bounded file under `<userData>/logs`.
 * Idempotent. Always-on (dev and packaged) for dev/prod parity — in dev the
 * console still prints to the terminal, this only adds the persisted copy.
 */
export function initMainLog(userDataPath: string): void {
  if (initialized) return
  initialized = true
  try {
    const dir = join(userDataPath, 'logs')
    mkdirSync(dir, { recursive: true })
    const log = new RotatingLog({
      filePath: join(dir, 'main.log'),
      maxBytes: MAX_BYTES,
      backups: BACKUPS
    })
    attachConsoleFileTee(log)
    // Session banner so the file has a clear per-launch boundary.
    console.log(`[mainLog] session start pid=${process.pid}`)
  } catch {
    // A logging failure must never prevent the app from starting; we keep the
    // initialized flag set so we don't risk double-patching console on a retry.
  }
}
