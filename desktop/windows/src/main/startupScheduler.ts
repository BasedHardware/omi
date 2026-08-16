// Cooperative startup scheduler. The main-window `ready-to-show` handler used to
// run ~20 background-service starts AND three auxiliary BrowserWindow creations
// (capture / insight-toast / glow) synchronously in a SINGLE tick right at first
// paint. Measured cost: a ~0.9–1.4s main-thread stall plus a 4→7 renderer-process
// spawn storm, landing exactly when the user is looking at the just-opened window —
// which stutters the whole desktop (the main process can't service GPU/compositor
// IPC or window messages while it is blocked, and the simultaneous transparent-
// window creations churn the Windows DWM compositor). See
// docs/perf-startup-burst-2026-07-19.md.
//
// This spreads that work across the first ~second: each step runs on its own timer
// tick, so the event loop yields between steps (the compositor/input threads get
// serviced, no single long stall) and the window creations are staggered instead
// of simultaneous. Nothing is dropped — every step still runs, in order, within a
// second of first paint — so no user-visible startup behavior changes; only the
// burst is flattened.
import { timedStep } from './dev/startupProfiler'

export interface StartupStep {
  /** Stable label (also used for per-step startup-profiler attribution). */
  name: string
  run: () => void
}

/** Default spacing between steps: ~1.5 display frames at 60Hz — enough for the
 *  compositor/input to be serviced between steps without stretching the whole
 *  schedule out noticeably. */
export const DEFAULT_STEP_GAP_MS = 24

export type TimerFn = (cb: () => void, ms: number) => unknown

/**
 * Run `steps` one per timer tick, `gapMs` apart, each isolated so a throw in one
 * never blocks the rest (a failed background service must not strand the others).
 * The FIRST step runs on the next tick (gap 0) so genuinely time-sensitive work
 * (e.g. bringing the capture window up for continuous recording) isn't needlessly
 * delayed, then the remainder are spaced out.
 *
 * `setTimerFn` is injectable for tests (assert ordering + error isolation without
 * real timers). `shouldStop`, when it returns true, skips the step (and thus any
 * later ones once it stays true) — wired to isQuitting() so a quit during the
 * ~0.5s stagger window doesn't run a window-creation step against a tearing-down
 * app. Returns immediately; steps run asynchronously.
 */
export function scheduleStartupSteps(
  steps: StartupStep[],
  gapMs: number = DEFAULT_STEP_GAP_MS,
  setTimerFn: TimerFn = setTimeout,
  shouldStop?: () => boolean
): void {
  steps.forEach((step, i) => {
    setTimerFn(() => {
      if (shouldStop?.()) return
      try {
        timedStep(step.name, step.run)
      } catch (e) {
        console.warn(`[startup] step "${step.name}" failed: ${(e as Error).message}`)
      }
    }, i * gapMs)
  })
}
