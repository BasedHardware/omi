// Main-process coordinator that turns 429 "storms" across the backend fetch
// helpers into a single degraded/healthy signal broadcast to the UI.
//
// The storm-detection logic lives in the pure, tested RateLimitDegradedTracker;
// this module is the thin electron glue: it classifies each request outcome,
// feeds the tracker, and on a transition broadcasts an IPC event to every window
// and records a structured fallback line. Helpers call `noteBackendStatus(status)`
// after each backend response (or `noteBackendStatus(undefined)` on a thrown
// network error, which is ignored — only a real 429 counts as a rate-limit hit).

import { BrowserWindow, ipcMain } from 'electron'
import { RateLimitDegradedTracker } from './rateLimitDegraded'
import { recordFallback } from './fallback'

// A storm = ≥ THRESHOLD 429s across ≥ MIN_DISTINCT_KEYS request paths within
// WINDOW_MS. The distinct-key rule keeps one endpoint's retry loop from tripping
// the indicator; only an account-wide rate-limit hits multiple paths at once.
const THRESHOLD = 5
const WINDOW_MS = 60_000
const MIN_DISTINCT_KEYS = 2

export type DegradedBroadcaster = (degraded: boolean) => void

/** Default broadcaster: fan the state out to every live window. Only the main
 *  window mounts the notice; other windows receive and ignore it. */
function broadcastToAllWindows(degraded: boolean): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (w.isDestroyed()) continue
    w.webContents.send('backend:degraded', degraded)
  }
}

let broadcaster: DegradedBroadcaster = broadcastToAllWindows
let clock: (() => number) | undefined
let tracker: RateLimitDegradedTracker | null = null

function getTracker(): RateLimitDegradedTracker {
  if (!tracker) {
    tracker = new RateLimitDegradedTracker({
      threshold: THRESHOLD,
      windowMs: WINDOW_MS,
      minDistinctKeys: MIN_DISTINCT_KEYS,
      now: clock,
      onChange: (degraded) => {
        broadcaster(degraded)
        recordFallback({
          component: 'backend_fetch',
          from: degraded ? 'normal' : 'rate_limited',
          to: degraded ? 'rate_limited' : 'normal',
          reason: 'http_429',
          outcome: degraded ? 'degraded' : 'recovered'
        })
      }
    })
  }
  return tracker
}

/** How a response status maps to the rate-limit tracker. Exported for tests. */
export function classifyForRateLimit(status: number | undefined): 'hit' | 'ok' | 'ignore' {
  if (status === 429) return 'hit'
  // Any success (2xx/3xx) is a recovery signal. 4xx/5xx (other than 429) and
  // thrown network errors are neither a rate-limit hit nor proof of recovery.
  if (status !== undefined && status >= 200 && status < 400) return 'ok'
  return 'ignore'
}

/**
 * Record the outcome of one backend request. Call after every main-process
 * backend fetch: pass the HTTP status (or `undefined` if it threw before a
 * response) and a stable request key (e.g. "GET /v1/action-items") so the
 * distinct-path storm rule can work. Safe to call from any lane; non-throwing.
 */
export function noteBackendStatus(status: number | undefined, key = 'default'): void {
  const kind = classifyForRateLimit(status)
  if (kind === 'ignore') return
  const t = getTracker()
  if (kind === 'hit') t.record429(key)
  else t.recordSuccess()
}

/** Current degraded state — for a renderer that mounts mid-storm and must sync. */
export function isBackendDegraded(): boolean {
  return tracker?.isDegraded() ?? false
}

/** Drop all 429-storm state. Called on sign-out so one account's storm never carries
 *  into the next account's session. */
export function resetBackendDegraded(): void {
  tracker = null
}

/** Register the pull channel so a late-mounting window can read current state. */
export function registerBackendDegradedIpc(): void {
  ipcMain.handle('backend:degradedState', () => isBackendDegraded())
}

/** Test seam: swap the broadcaster + clock and reset the tracker between cases. */
export function __setDegradedInternalsForTest(opts: {
  broadcaster?: DegradedBroadcaster | null
  now?: (() => number) | null
}): void {
  broadcaster = opts.broadcaster ?? broadcastToAllWindows
  clock = opts.now ?? undefined
  tracker = null
}
