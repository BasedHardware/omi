// Voice-plane flight recorder (2026-07-18): a bounded in-memory ring of the
// voice plane's observable events — gestures, lane routing, reducer transitions,
// hub session lifecycle, gate decisions, network attempts, system-audio
// mute/restore, contained errors — dumped to a rotating file on demand.
//
// Why it exists: voice failed silently three different ways in one day, and each
// diagnosis required live CDP archaeology of a wedged instance. The recorder
// makes the NEXT unknown failure self-evidencing: when the bar-side supervisor
// fires (or the user runs "Reset voice"), the last ~200 events land in a file
// under userData/logs with a one-line console.error pointer.
//
// Privacy contract (load-bearing): entries carry NO transcript text, NO audio
// content, NO PII — callers pass bounded labels and numbers (lengths, codes,
// phases). `record` additionally truncates any oversized payload so a future
// call site can't turn the ring into a text log by accident.
//
// Main-process resident: every window (bar, main, capture) feeds it over a
// fire-and-forget IPC (`voice:flightRecord`), and main-side code calls `record`
// directly — one merged, cross-window timeline, which is exactly what the
// multi-window voice plane needs (the 2026-07-18 wedges each spanned windows).

import fs from 'fs'
import path from 'path'

export type VoiceFlightEntry = {
  /** Epoch ms. */
  t: number
  /** Where the event was observed: 'main' | 'bar' | 'home' | 'capture' | … */
  src: string
  /** Bounded event label, e.g. 'gesture', 'turn', 'hub_error', 'mute'. */
  type: string
  data?: Record<string, unknown>
}

export const VOICE_FLIGHT_RING_LIMIT = 200
/** Per-entry serialized-payload cap — a data blob past this is replaced with a
 *  truncation marker so no call site can smuggle transcript-sized text in. */
export const VOICE_FLIGHT_DATA_CAP = 512
/** How many dump files are kept before the oldest is deleted. */
export const VOICE_FLIGHT_MAX_DUMPS = 10

export type VoiceFlightRecorderDeps = {
  now?: () => number
  /** Resolves the dump directory lazily (Electron `app` isn't ready at import). */
  logsDir?: () => string
  limit?: number
  maxDumps?: number
  /** Carry-over entries (original timestamps preserved) — the init handoff. */
  seed?: VoiceFlightEntry[]
}

export class VoiceFlightRecorder {
  private readonly now: () => number
  private readonly logsDir: (() => string) | null
  private readonly limit: number
  private readonly maxDumps: number
  private ring: VoiceFlightEntry[] = []

  constructor(deps: VoiceFlightRecorderDeps = {}) {
    this.now = deps.now ?? (() => Date.now())
    this.logsDir = deps.logsDir ?? null
    this.limit = Math.max(1, deps.limit ?? VOICE_FLIGHT_RING_LIMIT)
    this.maxDumps = Math.max(1, deps.maxDumps ?? VOICE_FLIGHT_MAX_DUMPS)
    if (deps.seed) this.ring = deps.seed.slice(-this.limit)
  }

  /** Append one event. Cheap (bounded ring, no I/O) and throw-proof — the
   *  recorder must never be able to break the plane it observes. */
  record(src: string, type: string, data?: Record<string, unknown>): void {
    try {
      const entry: VoiceFlightEntry = { t: this.now(), src, type }
      if (data !== undefined) {
        const json = JSON.stringify(data)
        entry.data =
          json.length > VOICE_FLIGHT_DATA_CAP
            ? { truncated: true, bytes: json.length }
            : (JSON.parse(json) as Record<string, unknown>)
      }
      this.ring.push(entry)
      if (this.ring.length > this.limit) {
        this.ring = this.ring.slice(this.ring.length - this.limit)
      }
    } catch {
      /* an unserializable payload must never throw into the caller */
    }
  }

  snapshot(): VoiceFlightEntry[] {
    return [...this.ring]
  }

  /** Write the ring to a rotating file under the logs dir and return its path.
   *  Never throws (a broken disk must not break the reset that triggered the
   *  dump); returns null when writing was impossible. The ring is NOT cleared —
   *  a second trigger seconds later should still show the same history. */
  dump(reason: string): string | null {
    try {
      if (!this.logsDir) return null
      const dir = this.logsDir()
      fs.mkdirSync(dir, { recursive: true })
      const stamp = new Date(this.now()).toISOString().replace(/[:.]/g, '-')
      const file = path.join(dir, `voice-flight-${stamp}.json`)
      fs.writeFileSync(
        file,
        JSON.stringify({ reason, dumpedAt: this.now(), entries: this.ring }, null, 1)
      )
      this.rotate(dir)
      console.error(
        `[voice-flight] dumped ${this.ring.length} events (reason=${reason}) -> ${file}`
      )
      return file
    } catch (err) {
      console.error('[voice-flight] dump failed:', err)
      return null
    }
  }

  private rotate(dir: string): void {
    const dumps = fs
      .readdirSync(dir)
      .filter((f) => f.startsWith('voice-flight-') && f.endsWith('.json'))
      .sort()
    for (const stale of dumps.slice(0, Math.max(0, dumps.length - this.maxDumps))) {
      try {
        fs.unlinkSync(path.join(dir, stale))
      } catch {
        /* a locked stale dump is not worth failing over */
      }
    }
  }
}

// The app-wide instance. `logsDir` is injected at wiring time (main/index.ts)
// because Electron's `app` paths aren't available at import; until then dumps
// no-op safely (record still works, so early events aren't lost).
let appRecorder = new VoiceFlightRecorder()

export function initVoiceFlightRecorder(logsDir: () => string): void {
  appRecorder = new VoiceFlightRecorder({ logsDir, seed: appRecorder.snapshot() })
}

export function recordVoiceFlight(src: string, type: string, data?: Record<string, unknown>): void {
  appRecorder.record(src, type, data)
}

export function dumpVoiceFlight(reason: string): string | null {
  return appRecorder.dump(reason)
}
