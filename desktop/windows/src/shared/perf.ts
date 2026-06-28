import { appendFileSync, mkdirSync } from 'fs'
import { dirname } from 'path'

// One structured perf event. `ts` is wall-clock epoch ms (for ordering across
// runs); `mono` is performance.now() high-resolution ms (for phase deltas within
// a single process run).
export interface PerfMark {
  name: string
  ts: number
  mono: number
  meta?: Record<string, unknown>
}

// Path is resolved lazily on every call so the main process can set
// process.env.OMI_PERF_LOG AFTER this module is imported (import order would
// otherwise capture an empty value at module load).
function logPath(): string {
  return process.env.OMI_PERF_LOG ?? ''
}

const buffer: string[] = []
let dirEnsured = false

// Append a perf event. Cheap and always-on: buffered in memory and flushed on
// exit (or every 50 marks) so marking itself adds negligible latency. No-op
// unless OMI_PERF_LOG is set.
export function perfMark(name: string, meta?: Record<string, unknown>): void {
  if (!logPath()) return
  const mark: PerfMark = { name, ts: Date.now(), mono: performance.now(), meta }
  buffer.push(JSON.stringify(mark))
  if (buffer.length >= 50) flushPerfMarks()
}

// Synchronously write any buffered marks to disk. Safe to call multiple times.
export function flushPerfMarks(): void {
  const path = logPath()
  if (!path || buffer.length === 0) return
  if (!dirEnsured) {
    mkdirSync(dirname(path), { recursive: true })
    dirEnsured = true
  }
  appendFileSync(path, buffer.join('\n') + '\n')
  buffer.length = 0
}

// Flush on process exit so marks survive an app.quit(). exit handlers must be
// synchronous; appendFileSync is.
process.on('exit', () => flushPerfMarks())
