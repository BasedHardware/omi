// The proactive-assistant framework. Port of macOS `AssistantCoordinator`:
// one shared loop reads the latest screen frame and fans it out to every
// registered assistant, which are peers — no ordering, no priority, each gated
// by its own `isEnabled` / `shouldAnalyze`.
//
// Windows differences from Mac, and why:
//
//  * Mac's capture plugin PUSHES each captured frame into the coordinator.
//    Windows has no frame-captured signal at all (capture lives in a hidden
//    renderer and only writes rows), so we POLL `latestRewindFrame()` on our own
//    tick. Consequence: the same row can come back twice (capture pauses when the
//    user is idle / on the lock screen), so we skip a frame we have already seen
//    — otherwise an assistant would re-analyze one static screen forever.
//
//  * The cadence lives HERE, not on capture. Windows capture runs flat at 1s with
//    no power awareness and belongs to another track; Mac's "3s base, ×3 on
//    battery" is therefore applied to the coordinator's own tick instead.
//
// The class takes every impure edge as a dep (clock, frame source, settings,
// power) so the gating and backpressure logic is testable with no timers, no DB
// and no Electron.
import { powerMonitor } from 'electron'
import { getAppSettings } from '../../appSettings'
import { latestRewindFrame } from '../../ipc/db'
import type { RewindFrame } from '../../../shared/types'
import { didContextChange } from './contextDetection'
import { mayAnalyzeFrame } from './privacy'

/** Whatever an assistant produced. The framework never inspects it — it only
 *  hands it back to the assistant's own `handleResult`. */
export type AssistantResult = Record<string, unknown>

/** Single fan-in point for assistant events (UI bridge). */
export type SendEvent = (type: string, data: Record<string, unknown>) => void

/** Mac's `ProactiveAssistant` protocol. Optional members have the same defaults
 *  Mac's protocol extension supplies. */
export interface ProactiveAssistant {
  readonly identifier: string
  readonly displayName: string
  /** Per-assistant on/off (its own setting), checked on every frame. */
  isEnabled(): boolean | Promise<boolean>
  analyze(frame: RewindFrame): Promise<AssistantResult | null>
  handleResult(result: AssistantResult, sendEvent: SendEvent): void | Promise<void>
  stop(): void | Promise<void>
  /** The assistant's own cadence policy. Default: analyze every frame. */
  shouldAnalyze?(frameNumber: number, timeSinceLastAnalysisMs: number): boolean
  /** The user moved to a different app/window. `departingFrame` is the last frame
   *  from the context they just left (null if we never had one). Default: no-op. */
  onContextSwitch?(
    departingFrame: RewindFrame | null,
    newApp: string,
    newWindowTitle: string
  ): void | Promise<void>
  /** Opt in to keep receiving frames during the post-switch analysis delay (for
   *  time-sensitive detections like "did they come back?"). Default: false. */
  needsFrameDuringDelay?(): boolean
  /** Drop queued/scheduled work — called when the context changes under it.
   *  Default: no-op. */
  clearPendingWork?(): void | Promise<void>
}

export type CoordinatorDeps = {
  latestFrame: () => RewindFrame | null
  now: () => number
  isOnBattery: () => boolean
  /** Master toggle. When false the loop does not run at all (not a per-frame gate). */
  isScreenAnalysisEnabled: () => boolean
  /** Quiet window after a context switch, during which only opted-in assistants
   *  see frames. Mac default: 60s. */
  analysisDelayMs: () => number
  /** Privacy gate — no frame that fails it reaches any assistant. */
  mayAnalyzeFrame: (frame: RewindFrame) => boolean
  /** Tick interval with the machine on mains power. Mac default: 3s. */
  baseIntervalMs: number
  /** Mac's `batteryCaptureIntervalMultiplier`. */
  batteryMultiplier: number
}

export const DEFAULT_BASE_INTERVAL_MS = 3_000
export const DEFAULT_BATTERY_MULTIPLIER = 3
export const DEFAULT_ANALYSIS_DELAY_MS = 60_000

function defaultDeps(): CoordinatorDeps {
  return {
    latestFrame: latestRewindFrame,
    now: () => Date.now(),
    // `onBatteryPower` is undefined on stubs / non-laptops — treat as mains.
    isOnBattery: () => powerMonitor.onBatteryPower === true,
    isScreenAnalysisEnabled: () => getAppSettings().screenAnalysisEnabled,
    analysisDelayMs: () => DEFAULT_ANALYSIS_DELAY_MS,
    mayAnalyzeFrame,
    baseIntervalMs: DEFAULT_BASE_INTERVAL_MS,
    batteryMultiplier: DEFAULT_BATTERY_MULTIPLIER
  }
}

export class AssistantCoordinator {
  private readonly deps: CoordinatorDeps
  private readonly assistants = new Map<string, ProactiveAssistant>()
  /** Backpressure: an assistant still working on frame N is SKIPPED for N+1,
   *  never queued — queuing would pile up JPEG-sized frames behind a slow
   *  analyze(). Other assistants are unaffected. */
  private readonly analyzing = new Set<string>()
  private readonly lastAnalysisAt = new Map<string, number>()

  private timer: ReturnType<typeof setInterval> | null = null
  private frameNumber = 0
  /** Identity of the last frame distributed, so a re-read of the same row (idle
   *  user → capture paused) is not re-analyzed. */
  private lastFrameKey: number | null = null
  /** The last frame that PASSED the privacy gate — the only kind we ever hand to
   *  an assistant, including as a departing frame. */
  private lastAllowedFrame: RewindFrame | null = null
  private trackedApp: string | null = null
  private trackedTitle: string | null = null
  private hasContext = false
  /** End of the post-context-switch quiet window; null = not in one. */
  private delayUntil: number | null = null
  private eventCallback: SendEvent | null = null

  constructor(deps: Partial<CoordinatorDeps> = {}) {
    this.deps = { ...defaultDeps(), ...deps }
  }

  register(assistant: ProactiveAssistant): void {
    this.assistants.set(assistant.identifier, assistant)
    // -Infinity, Mac's `.distantPast`: the first frame always reads as "never
    // analyzed", so a cadence policy of "at most every N seconds" fires at once.
    this.lastAnalysisAt.set(assistant.identifier, -Infinity)
  }

  setEventCallback(cb: SendEvent | null): void {
    this.eventCallback = cb
  }

  /** Current tick interval — Mac's `effectiveCaptureInterval`. */
  intervalMs(): number {
    const { baseIntervalMs, batteryMultiplier } = this.deps
    return this.deps.isOnBattery() ? baseIntervalMs * batteryMultiplier : baseIntervalMs
  }

  isRunning(): boolean {
    return this.timer !== null
  }

  /** Start (or restart, e.g. on a power-source change) the loop. A no-op while
   *  the master toggle is off — off means the timer never runs, so no frame is
   *  ever read. */
  start(): void {
    this.stopTimer()
    if (!this.deps.isScreenAnalysisEnabled()) return
    this.timer = setInterval(() => this.tick(), this.intervalMs())
    // Node keeps the process alive for a pending interval; this one is pure
    // background work and must never be the reason the app lingers.
    this.timer.unref?.()
  }

  /** Stop the loop. Does not stop the assistants themselves (see `stopAll`). */
  stop(): void {
    this.stopTimer()
  }

  private stopTimer(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  /** Stop the loop AND every assistant (app shutdown / sign-out). */
  async stopAll(): Promise<void> {
    this.stop()
    await Promise.allSettled([...this.assistants.values()].map((a) => a.stop()))
  }

  /** One pass of the loop. Public so tests drive it directly — the timer's only
   *  job is to call this. */
  tick(): void {
    if (!this.deps.isScreenAnalysisEnabled()) return
    const frame = this.deps.latestFrame()
    if (!frame) return

    const key = frame.id ?? frame.ts
    if (key === this.lastFrameKey) return // same row we already handled
    this.lastFrameKey = key
    this.frameNumber += 1

    // Context tracking runs on EVERY frame's metadata, including frames the
    // privacy gate will reject: leaving a banking tab and coming back is a real
    // context switch, and the assistants must learn about it even though they
    // never see the bank's pixels.
    this.checkContextSwitch(frame)

    if (!this.deps.mayAnalyzeFrame(frame)) return
    this.lastAllowedFrame = frame
    this.distribute(frame)
  }

  private checkContextSwitch(frame: RewindFrame): void {
    const app = frame.app
    const title = frame.windowTitle
    if (!this.hasContext) {
      // First frame ever — there is no "from", so nothing switched.
      this.hasContext = true
      this.trackedApp = app
      this.trackedTitle = title
      return
    }
    if (!didContextChange(this.trackedApp, this.trackedTitle, app, title)) return

    this.trackedApp = app
    this.trackedTitle = title

    // Fire-and-forget, in parallel: no ordering guarantee across assistants, and
    // a slow/throwing hook must not stall the loop.
    const departing = this.lastAllowedFrame
    for (const a of this.assistants.values()) {
      if (!a.onContextSwitch) continue
      void Promise.resolve(a.onContextSwitch(departing, app, title)).catch((e) =>
        console.warn(`[assistants] ${a.identifier}.onContextSwitch failed:`, e)
      )
    }

    const now = this.deps.now()
    // Already inside a quiet window → don't extend it (Mac's isInDelayPeriod
    // guard), or rapid app-hopping would defer analysis indefinitely.
    if (this.delayUntil !== null && now < this.delayUntil) return
    this.delayUntil = now + this.deps.analysisDelayMs()
    this.clearAllPendingWork()
  }

  private clearAllPendingWork(): void {
    for (const a of this.assistants.values()) {
      if (!a.clearPendingWork) continue
      void Promise.resolve(a.clearPendingWork()).catch((e) =>
        console.warn(`[assistants] ${a.identifier}.clearPendingWork failed:`, e)
      )
    }
  }

  private distribute(frame: RewindFrame): void {
    const now = this.deps.now()
    const inDelay = this.delayUntil !== null && now < this.delayUntil
    for (const a of this.assistants.values()) {
      // During the post-switch quiet window only assistants that explicitly need
      // frames (refocus tracking and the like) get one.
      if (inDelay && a.needsFrameDuringDelay?.() !== true) continue
      if (this.analyzing.has(a.identifier)) continue // still busy → skip, never queue
      this.analyzing.add(a.identifier)
      void this.run(a, frame, now)
    }
  }

  private async run(a: ProactiveAssistant, frame: RewindFrame, now: number): Promise<void> {
    try {
      if (!(await a.isEnabled())) return
      const last = this.lastAnalysisAt.get(a.identifier) ?? -Infinity
      if (a.shouldAnalyze && !a.shouldAnalyze(this.frameNumber, now - last)) return
      // Mac stamps the time only once the assistant has agreed to analyze, so a
      // declined frame does not reset its cadence clock.
      this.lastAnalysisAt.set(a.identifier, now)

      const result = await a.analyze(frame)
      if (!result) return
      await a.handleResult(result, (type, data) => this.eventCallback?.(type, data))
    } catch (e) {
      console.warn(`[assistants] ${a.identifier} analysis failed:`, e)
    } finally {
      this.analyzing.delete(a.identifier)
    }
  }
}

// --- Runtime singleton -------------------------------------------------------

let singleton: AssistantCoordinator | null = null
let powerHooked = false

export function getAssistantCoordinator(): AssistantCoordinator {
  if (!singleton) singleton = new AssistantCoordinator()
  return singleton
}

/** Register an assistant and bring the loop up if the master toggle allows it.
 *  The loop only exists to feed assistants, so registration is what starts it —
 *  no assistants, no polling. */
export function registerAssistant(assistant: ProactiveAssistant): void {
  const coordinator = getAssistantCoordinator()
  coordinator.register(assistant)
  hookPowerChanges(coordinator)
  syncAssistantCoordinator()
}

/** Re-read the master toggle and start/stop the loop accordingly. Call after a
 *  settings change. */
export function syncAssistantCoordinator(): void {
  const coordinator = getAssistantCoordinator()
  if (getAppSettings().screenAnalysisEnabled) coordinator.start()
  else coordinator.stop()
}

/** The tick interval depends on the power source, so a change has to reschedule
 *  it — restarting is exactly what Mac's `setupPowerAwareCaptureTimer` does. */
function hookPowerChanges(coordinator: AssistantCoordinator): void {
  if (powerHooked) return
  powerHooked = true
  const restart = (): void => {
    if (coordinator.isRunning()) coordinator.start()
  }
  powerMonitor.on('on-battery', restart)
  powerMonitor.on('on-ac', restart)
}

/** Test-only: drop the singleton (and its power hook) between suites. */
export function _resetCoordinatorForTests(): void {
  singleton?.stop()
  singleton = null
  powerHooked = false
}
