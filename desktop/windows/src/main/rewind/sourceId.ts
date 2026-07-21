import { desktopCapturer, screen } from 'electron'

// desktopCapturer.getSources() is pathologically slow on some machines (multiple
// seconds even with thumbnails disabled), and it's the dominant cost of enabling
// Rewind capture. The primary screen's source id is stable for a session, so we
// fetch it once, cache it, and reuse it. The cache is invalidated when the
// display layout changes. A single-flight promise dedupes concurrent callers
// (e.g. the startup prewarm racing the user's first enable).

let cached: string | null = null
let inflight: Promise<string | null> | null = null
// Bumped whenever the display layout changes, so an in-flight fetch that resolves
// after a change does not write its now-stale id into the cache.
let generation = 0

async function fetchPrimarySourceId(): Promise<string | null> {
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: 0, height: 0 } // ids only — no screen bitmap
  })
  // A source's `id` is a sequential screen number, and getSources() makes no
  // ordering guarantee — so sources[0] is not necessarily the primary display.
  // `display_id` is the documented link to the Screen API; match on it and only
  // fall back to the first source when Electron doesn't report one.
  const primaryDisplayId = String(screen.getPrimaryDisplay().id)
  const primary = sources.find((s) => s.display_id === primaryDisplayId)
  return primary?.id ?? sources[0]?.id ?? null
}

/** Cached primary-screen source id; computes it (slowly) once, then reuses it. */
export async function getPrimarySourceId(): Promise<string | null> {
  if (cached) return cached
  if (!inflight) {
    const gen = generation
    inflight = fetchPrimarySourceId()
      .then((id) => {
        // Drop the result if the display layout changed mid-fetch; the id was
        // enumerated against the old layout and may now be stale.
        if (generation === gen) cached = id
        return generation === gen ? id : null
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

let invalidatorBound = false

/**
 * Kick off the slow getSources() once at startup-idle so the cache is warm
 * before the user enables capture — turning the multi-second enable hitch into
 * an instant cache hit. Also binds display-change listeners that drop the cache.
 */
export function prewarmPrimarySourceId(): void {
  if (!invalidatorBound) {
    const invalidate = (): void => {
      generation++
      cached = null
    }
    screen.on('display-added', invalidate)
    screen.on('display-removed', invalidate)
    screen.on('display-metrics-changed', invalidate)
    invalidatorBound = true
  }
  void getPrimarySourceId()
}
