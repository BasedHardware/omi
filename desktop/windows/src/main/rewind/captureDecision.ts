import { hammingDistance } from './frameHash'
import { SENSITIVE_WINDOW_MARKERS } from '../../shared/rewindExclusions'

/** Max bit difference for two frames to count as "the same screen" → skip. */
export const DUP_HAMMING_THRESHOLD = 4

export type CaptureState = {
  locked: boolean
  idleSeconds: number
  idleThresholdSeconds: number
  busy: boolean
  appName: string
  /** Foreground process name (e.g. "chrome"); matched alongside appName. */
  processName?: string
  /** Foreground window title; matched against sensitive markers (login/private). */
  windowTitle?: string
  excludedApps: string[]
  hash: string
  lastHash: string | null
}

export type CaptureDecision =
  | { capture: true }
  | { capture: false; reason: 'locked' | 'idle' | 'busy' | 'excluded' | 'sensitive' | 'duplicate' }

// Case-insensitive substring match so a user entry like "chrome" excludes
// "Google Chrome" (and the "chrome" process). Matched against the friendly app
// name and the process name; empty entries never match.
function isExcluded(appName: string, processName: string, excludedApps: string[]): boolean {
  const haystack = `${appName} ${processName}`.toLowerCase()
  return excludedApps.some((e) => {
    const needle = e.trim().toLowerCase()
    return needle.length > 0 && haystack.includes(needle)
  })
}

// True when the window title looks like a login / password / private-browsing
// screen — so Rewind skips it even when the app itself isn't excluded (e.g. a
// login page in a normal browser).
function isSensitiveTitle(windowTitle: string): boolean {
  const t = windowTitle.toLowerCase()
  return SENSITIVE_WINDOW_MARKERS.some((m) => t.includes(m))
}

export function shouldCaptureFrame(s: CaptureState): CaptureDecision {
  if (s.locked) return { capture: false, reason: 'locked' }
  if (s.busy) return { capture: false, reason: 'busy' }
  if (s.idleSeconds >= s.idleThresholdSeconds) return { capture: false, reason: 'idle' }
  if (isExcluded(s.appName, s.processName ?? '', s.excludedApps)) {
    return { capture: false, reason: 'excluded' }
  }
  if (isSensitiveTitle(s.windowTitle ?? '')) {
    return { capture: false, reason: 'sensitive' }
  }
  if (s.lastHash && hammingDistance(s.hash, s.lastHash) <= DUP_HAMMING_THRESHOLD) {
    return { capture: false, reason: 'duplicate' }
  }
  return { capture: true }
}
