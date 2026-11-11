// Focus's two decision functions, both pure:
//
//  * shouldSkipAnalysis — may we spend a Gemini call on this frame? (Mac's
//    `FocusAssistant.shouldSkipAnalysis`, ported branch for branch.)
//  * decideTransition — given a verdict, what actually happens? (Mac's
//    `lastNotifiedState` dance.)
//
// Both are the parts that are easy to get subtly wrong and expensive when you
// do — a gating bug bills the user for a Gemini call every 3 seconds; a
// transition bug flashes a halo on every frame instead of once. Keeping them
// pure means both are pinned by tests with no clock, no network and no DB.
import { didContextChange } from '../core/contextDetection'
import type { FocusSessionStatus } from '../../../shared/types'
import type { ScreenAnalysis } from './models'

/** Exponential error backoff: 5s, 10s, 20s, 40s… capped at 5 minutes. */
export function errorBackoffMs(consecutiveErrors: number): number {
  const n = Math.max(1, consecutiveErrors)
  return Math.min(5000 * 2 ** (n - 1), 300_000)
}

/** Everything the skip decision reads. All of it is Focus's own state — the
 *  coordinator's backpressure and privacy gates already ran. */
export type SkipInput = {
  now: number
  /** Frame's app + window title. */
  app: string
  windowTitle: string | null
  /** Context of the last frame we ANALYZED (not the last frame we saw). */
  lastAnalyzedApp: string | null
  lastAnalyzedWindowTitle: string | null
  /** Verdict of the last completed analysis; null before the first one. */
  lastStatus: FocusSessionStatus | null
  /** End of the post-distraction cooldown, or null. */
  cooldownEndsAt: number | null
  /** End of the error backoff, or null. */
  backoffEndsAt: number | null
}

export type SkipDecision =
  | { skip: true; reason: 'error_backoff' | 'cooldown' | 'focused_same_context' }
  | { skip: false; reason: 'cold_start' | 'context_changed' | 'not_focused' }

/**
 * Mac's order, and the order matters:
 *
 *  1. error backoff — checked FIRST, before the cold-start guard. If the API is
 *     failing, `lastStatus` stays null forever, so a cold-start-first order
 *     would retry every single frame through an outage.
 *  2. cold start (no verdict yet) → analyze.
 *  3. context changed → analyze, BYPASSING the cooldown. The cooldown exists to
 *     stop us re-billing a user who is still on the same distracting page; the
 *     moment they move, it has done its job.
 *  4. cooldown (set only after a distraction) → skip.
 *  5. focused AND same context → skip. This is the steady state: someone working
 *     in one window costs nothing.
 *  6. otherwise (distracted, same context, cooldown lapsed) → analyze.
 */
export function shouldSkipAnalysis(input: SkipInput): SkipDecision {
  if (input.backoffEndsAt !== null && input.now < input.backoffEndsAt)
    return { skip: true, reason: 'error_backoff' }

  if (input.lastStatus === null) return { skip: false, reason: 'cold_start' }

  const contextChanged = didContextChange(
    input.lastAnalyzedApp,
    input.lastAnalyzedWindowTitle,
    input.app,
    input.windowTitle
  )
  if (contextChanged) return { skip: false, reason: 'context_changed' }

  if (input.cooldownEndsAt !== null && input.now < input.cooldownEndsAt)
    return { skip: true, reason: 'cooldown' }

  if (input.lastStatus === 'focused') return { skip: true, reason: 'focused_same_context' }

  return { skip: false, reason: 'not_focused' }
}

/** What a verdict is allowed to do. */
export type TransitionAction = {
  /** Write the focus_sessions row + the memory. Only on a transition. */
  persist: boolean
  /** Fire the halo, and in which colour. */
  glow: 'distracted' | 'focused' | null
  /** Send a (throttled) notification with this body. null = say nothing. */
  notifyBody: string | null
  /** Arm the post-distraction cooldown. */
  startCooldown: boolean
  /** The new `lastNotifiedState` (unchanged when this was not a transition). */
  notifiedState: FocusSessionStatus | null
}

const NOTHING: TransitionAction = {
  persist: false,
  glow: null,
  notifyBody: null,
  startCooldown: false,
  notifiedState: null
}

/**
 * The state machine. Guarded on `lastNotifiedState`, NOT on the verdict alone —
 * up to 3 analyses can be in flight at once and a distracted user produces a
 * "distracted" verdict on every one of them. Without the guard the user gets
 * three halos and three toasts for one lapse.
 *
 * The asymmetry between the two transitions is deliberate and is the whole
 * point of the feature: going distracted is always news, while going focused is
 * only news if we had previously told them they weren't. A cold-start "focused"
 * (the app just started and the user is, as usual, working) persists the row and
 * says NOTHING — no halo, no toast. Congratulating someone for working when they
 * never stopped is the fastest way to get the feature turned off.
 */
export function decideTransition(
  lastNotifiedState: FocusSessionStatus | null,
  analysis: ScreenAnalysis
): TransitionAction {
  if (analysis.status === 'distracted') {
    if (lastNotifiedState === 'distracted') return { ...NOTHING, notifiedState: 'distracted' }
    return {
      persist: true,
      glow: 'distracted',
      // "Chrome - You've been on YouTube for a while." Mac prefixes the app so a
      // banner with no window context still says where the user is.
      notifyBody: analysis.message ? `${analysis.appOrSite} - ${analysis.message}` : null,
      startCooldown: true,
      notifiedState: 'distracted'
    }
  }

  if (lastNotifiedState === 'focused') return { ...NOTHING, notifiedState: 'focused' }
  const wasDistracted = lastNotifiedState === 'distracted'
  return {
    persist: true,
    // Cold start (lastNotifiedState === null): persist only.
    glow: wasDistracted ? 'focused' : null,
    // "Back on track" carries just the message — the app name would be noise
    // (they are back in the window they are looking at).
    notifyBody: wasDistracted ? analysis.message : null,
    startCooldown: false,
    notifiedState: 'focused'
  }
}
