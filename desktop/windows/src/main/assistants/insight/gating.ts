// Insight's cadence/skip decisions, all pure. The deliberate CONTRAST with Focus:
// Insight has NO cooldown, NO error backoff, NO context-change bypass. Its only
// cadence control is a fixed extraction interval (Mac's `extractionInterval`,
// default 600s), and its only pre-Gemini filter is the three-way app denylist.
//
// The three-way denylist (Mac's `isAppExcluded`): builtin ∪ user-list ∪ private.
// `mayAnalyzeFrame` (core/privacy) already covers builtin + private + denied
// contexts; the USER leg (the Insight settings denylist) is added here, mirroring
// the renderer `isUserDenied` logic but living main-side and pure.
import { mayAnalyzeFrame } from '../core/privacy'
import type { RewindFrame } from '../../../shared/types'

/** Mac's `adviceExtractionInterval` default (600s). The live interval is the
 *  user's InsightSettings.intervalMin; this is the documented parity anchor and
 *  the floor a junk setting falls back to. */
export const MAC_EXTRACTION_INTERVAL_MS = 600_000

/** Mac's `adviceMinConfidence` default. A notably high bar — Insight ships
 *  fewer, better insights. */
export const MIN_CONFIDENCE = 0.85

/** Has the fixed extraction interval elapsed since the last analysis? */
export function intervalElapsed(timeSinceLastMs: number, intervalMs: number): boolean {
  return timeSinceLastMs >= intervalMs
}

/** Mac's post-provide_advice confidence filter. */
export function passesConfidence(confidence: number, min: number = MIN_CONFIDENCE): boolean {
  return confidence >= min
}

/** The USER denylist leg — case-insensitive substring over app + windowTitle +
 *  processName, mirroring the renderer `isUserDenied`. An empty list never
 *  matches. Pure. */
export function isUserDeniedApp(
  frame: Pick<RewindFrame, 'app' | 'windowTitle' | 'processName'>,
  userDenylist: string[]
): boolean {
  if (userDenylist.length === 0) return false
  const hay = `${frame.app} ${frame.windowTitle} ${frame.processName}`.toLowerCase()
  return userDenylist.some((n) => {
    const t = n.trim().toLowerCase()
    return t.length > 0 && hay.includes(t)
  })
}

/** The full three-way gate: may Insight analyze THIS frame? builtin ∪ private ∪
 *  denied-context (mayAnalyzeFrame) AND not on the user's own Insight denylist.
 *  Returns true only when every leg allows it. */
export function insightFrameAllowed(
  frame: Pick<RewindFrame, 'app' | 'windowTitle' | 'processName'>,
  userDenylist: string[]
): boolean {
  return mayAnalyzeFrame(frame) && !isUserDeniedApp(frame, userDenylist)
}
