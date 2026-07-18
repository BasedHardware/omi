// In-memory "what's on screen right now": the latest OCR'd screen text, kept hot
// by the Rewind capture pipeline so the chat can read it with ZERO latency at send
// time — no DB scan, no on-demand OCR, no desktopCapturer. Frames captured by the
// Rewind host already exclude Omi's own windows, so this is the user's actual work,
// not Omi's UI. Freshness is ~1s (the capture cadence); the chat accepts that in
// exchange for an instant, always-ready answer.

let text = ''
let ts = 0

// The capture loop refreshes the cache ~every 1s while active, but pauses on idle
// (60s)/lock/excluded-app — beyond this window the cached text is no longer
// trustworthy as "right now", so the chat must not send it.
export const CACHE_FRESH_MS = 30000

/**
 * Pure freshness predicate (no db import, so it's unit-testable under node vitest):
 * true iff the cache has been seeded (ts !== 0) AND it's within CACHE_FRESH_MS of now.
 */
export function screenCacheFresh(now: number): boolean {
  return ts !== 0 && now - ts <= CACHE_FRESH_MS
}

export function setCurrentScreen(t: string): void {
  text = t
  ts = Date.now()
}

export function getCurrentScreen(): { text: string; ts: number } {
  return { text, ts }
}

/** Age of the cached text in ms; Infinity if never set. For diagnostics/staleness. */
export function currentScreenAgeMs(): number {
  return ts === 0 ? Infinity : Date.now() - ts
}
