import { desktopCapturer, screen } from 'electron'
import { getForegroundWindowRect } from '../usage/nativeForeground'

// desktopCapturer.getSources() is pathologically slow on some machines (multiple
// seconds even with thumbnails disabled), and it is the dominant cost of enabling
// Rewind capture. Screen source ids are stable for a display layout, so fetch the
// id-to-display map once, cache it, and choose from it cheaply as focus moves
// between monitors. The cache is invalidated when the layout changes. A
// single-flight promise dedupes concurrent callers.

type SourceIdentity = { id: string; displayId: string }

let cached: SourceIdentity[] | null = null
let inflight: Promise<SourceIdentity[]> | null = null

// The most recent fetch failure, if any — cleared on a successful fetch. On
// Linux this is almost always a Wayland desktop-portal gap (no
// org.freedesktop.portal.ScreenCast implementation registered for the running
// compositor — confirmed live: niri + no xdg-desktop-portal-wlr produced
// "Failed to get sources." here with no further detail reaching JS; the real
// GDBus error only appears in Chromium's native stderr log, not this
// exception). getRewindCaptureDiagnostics() surfaces this to the UI instead of
// the previous behavior: an uncaught rejection out of the
// 'rewind:captureSourceId' IPC handler and a silently-never-starting capture.
let lastFetchError: Error | null = null

export function getSourceFetchError(): string | null {
  return lastFetchError?.message ?? null
}

async function fetchSourceIdentities(): Promise<SourceIdentity[]> {
  try {
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 0, height: 0 } // ids only - no screen bitmap
    })
    lastFetchError = null
    return sources.map((source) => ({ id: source.id, displayId: source.display_id }))
  } catch (e) {
    // Cache the empty result like any other outcome (see the module header) —
    // a portal gap is a launch-time environment fact, not a transient blip;
    // retrying every call would just re-hit the same missing D-Bus interface.
    lastFetchError = e as Error
    return []
  }
}

async function getSourceIdentities(): Promise<SourceIdentity[]> {
  if (cached) return cached
  if (!inflight) {
    inflight = fetchSourceIdentities()
      .then((sources) => {
        cached = sources
        return sources
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

function sourceIdForDisplay(sources: SourceIdentity[], displayId: string): string | null {
  return sources.find((source) => source.displayId === displayId)?.id ?? null
}

/** Cached primary-screen source id; computes the source map once, then reuses it. */
export async function getPrimarySourceId(): Promise<string | null> {
  const sources = await getSourceIdentities()
  const primaryDisplayId = String(screen.getPrimaryDisplay().id)
  return sourceIdForDisplay(sources, primaryDisplayId) ?? sources[0]?.id ?? null
}

function foregroundDisplayId(): string | null {
  const { rect } = getForegroundWindowRect()
  if (!rect || rect.width <= 0 || rect.height <= 0) return null
  try {
    // Win32 reports physical pixels while Electron's display geometry is DIP.
    // Let Electron perform the per-monitor conversion before matching.
    const dipRect = screen.screenToDipRect(null, rect)
    return String(screen.getDisplayMatching(dipRect).id)
  } catch {
    return null
  }
}

function cursorDisplayId(): string | null {
  try {
    return String(screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).id)
  } catch {
    return null
  }
}

/**
 * Source for the display containing the foreground window. Fall back to the
 * cursor display when native foreground geometry is unavailable, then primary.
 */
export async function getRewindCaptureSourceId(): Promise<string | null> {
  const sources = await getSourceIdentities()
  const targetDisplayId = foregroundDisplayId() ?? cursorDisplayId()
  if (targetDisplayId) {
    const target = sourceIdForDisplay(sources, targetDisplayId)
    if (target) return target
  }
  const primary = sourceIdForDisplay(sources, String(screen.getPrimaryDisplay().id))
  return primary ?? sources[0]?.id ?? null
}

/** Reject a frame if foreground focus changed displays while it was encoded. */
export async function isCurrentRewindCaptureSource(sourceId: string): Promise<boolean> {
  return sourceId.length > 0 && sourceId === (await getRewindCaptureSourceId())
}

let invalidatorBound = false

/**
 * Kick off the slow getSources() once at startup-idle so the cache is warm
 * before the user enables capture. Also bind display-change cache invalidation.
 */
export function prewarmPrimarySourceId(): void {
  if (!invalidatorBound) {
    const invalidate = (): void => {
      cached = null
    }
    screen.on('display-added', invalidate)
    screen.on('display-removed', invalidate)
    screen.on('display-metrics-changed', invalidate)
    invalidatorBound = true
  }
  void getPrimarySourceId()
}

export type RewindCaptureDiagnostics = {
  /** Whether at least one screen source resolved. */
  available: boolean
  /** The underlying fetch error's message, present only when unavailable. */
  reason: string | null
  /** Linux desktopCapturer.getSources() has one dominant failure mode: no
   *  org.freedesktop.portal.ScreenCast implementation registered for the
   *  running Wayland compositor (confirmed live on niri without
   *  xdg-desktop-portal-wlr installed/preferred). The JS-catchable error
   *  message is a generic "Failed to get sources." either way — Chromium logs
   *  the real GDBus detail only to its own stderr, never into the exception —
   *  so this is a platform heuristic, not a message-content match. */
  likelyMissingLinuxPortal: boolean
}

/** Ensure a fetch attempt has happened, then report whether it succeeded — for
 *  the UI to show a real error instead of Rewind silently never starting. */
export async function getRewindCaptureDiagnostics(): Promise<RewindCaptureDiagnostics> {
  await getPrimarySourceId()
  const reason = getSourceFetchError()
  return {
    available: !reason,
    reason,
    likelyMissingLinuxPortal: !!reason && process.platform === 'linux'
  }
}
