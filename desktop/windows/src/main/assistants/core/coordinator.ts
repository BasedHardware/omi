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
import { getAppSettings, onAppSettingsChanged } from '../../appSettings'
import { latestRewindFrame } from '../../ipc/db'
import { lastRewindCaptureAtMs } from '../../rewind/captureSignal'
import type { RewindFrame } from '../../../shared/types'
import { didContextChange } from './contextDetection'
import { DEBOUNCE_MS, distributionDecision, fallbackIntervalMs } from './distributionGate'
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
   *  from the context they just left (null if we never had one).
   *
   *  CONTRACT: `newWindowTitle` is **null when the new context failed the privacy
   *  gate** (an incognito window, a bank, a password manager). You are still told
   *  the user left — that is not private — but you never receive the sensitive
   *  title, because an assistant that pastes it into a prompt would ship
   *  "Chase — Log in" to a cloud model. Default: no-op. */
  onContextSwitch?(
    departingFrame: RewindFrame | null,
    newApp: string,
    newWindowTitle: string | null
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
  /** Cheap "newest stored frame changed" signal (capture's last-stored timestamp),
   *  read before `latestFrame` so the DB poll is skipped while capture is idle. A
   *  value that has not advanced since the last read means `latestFrame` would
   *  return the same row we already handled. Undefined disables the optimization
   *  (the loop always reads) — the lastFrameKey dedup below is the correctness
   *  authority regardless. */
  captureSignal?: () => number | null
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

/** Sentinel for "no tick has read the DB yet" — distinct from any real capture
 *  signal (number | null), so the first tick never short-circuits the DB read. */
const NEVER_READ = Symbol('never-read')

function defaultDeps(): CoordinatorDeps {
  return {
    latestFrame: latestRewindFrame,
    captureSignal: lastRewindCaptureAtMs,
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
  /** Capture signal value at our last DB read. While it is unchanged, `latestFrame`
   *  would return the same row, so the read is skipped. NEVER_READ until the first
   *  read so that read always happens. */
  private lastCaptureSignalAtRead: number | null | typeof NEVER_READ = NEVER_READ
  /** The last frame that PASSED the privacy gate — the only kind we ever hand to
   *  an assistant, including as a departing frame. */
  private lastAllowedFrame: RewindFrame | null = null
  private trackedApp: string | null = null
  private trackedTitle: string | null = null
  private hasContext = false
  /** End of the post-context-switch quiet window; null = not in one. */
  private delayUntil: number | null = null
  /** When a post-switch debounce is settling, the time it may flush. */
  private pendingFlushAt: number | null = null
  /** When the assistants last actually got a frame (drives the fallback interval). */
  private lastDistributedAt: number | null = null
  private eventCallback: SendEvent | null = null
  private lastTickErrorAt = 0

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
    // The tick reads the DB, which throws on a closed handle (app quit) or an I/O
    // error. Unguarded, that escapes to `uncaughtException` — and it would do so
    // every 3 seconds, forever, filling crash.log. Swallow it, log at most once a
    // minute, and keep the loop alive.
    this.timer = setInterval(() => {
      try {
        this.tick()
      } catch (e) {
        const now = this.deps.now()
        if (now - this.lastTickErrorAt < 60_000) return
        this.lastTickErrorAt = now
        console.warn('[assistants] coordinator tick failed:', e)
      }
    }, this.intervalMs())
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

  /** Stop the loop AND every assistant (app shutdown / sign-out). Also drops the
   *  registry and all per-frame state: a later start() must not resume feeding
   *  assistants we just told to stop, nor inherit a stale quiet window. */
  async stopAll(): Promise<void> {
    this.stop()
    const registered = [...this.assistants.values()]
    this.assistants.clear()
    this.analyzing.clear()
    this.lastAnalysisAt.clear()
    this.lastFrameKey = null
    this.lastCaptureSignalAtRead = NEVER_READ
    this.lastAllowedFrame = null
    this.lastDistributedAt = null
    this.pendingFlushAt = null
    this.delayUntil = null
    this.hasContext = false
    this.trackedApp = null
    this.trackedTitle = null
    this.frameNumber = 0
    await Promise.allSettled(registered.map((a) => a.stop()))
  }

  /** One pass of the loop. Public so tests drive it directly — the timer's only
   *  job is to call this. */
  tick(): void {
    if (!this.deps.isScreenAnalysisEnabled()) return

    // Cheap pre-check before the DB read: capture is the sole writer of rewind
    // frames, so when its "newest frame" signal has not advanced since our last
    // read, latestFrame() would return the same row we already handled (and we'd
    // short-circuit on lastFrameKey below anyway). Skip the DB read entirely.
    // An undefined signal source disables this — we always read.
    const sig = this.deps.captureSignal?.()
    if (sig !== undefined && sig === this.lastCaptureSignalAtRead) return

    const frame = this.deps.latestFrame()
    // Record the signal we read at (even on a null frame) so an unchanged signal
    // skips the next read rather than re-polling a still-empty / still-same DB.
    this.lastCaptureSignalAtRead = sig ?? null
    if (!frame) return

    const key = frame.id ?? frame.ts
    if (key === this.lastFrameKey) return // same row we already handled
    this.lastFrameKey = key
    this.frameNumber += 1

    const allowed = this.deps.mayAnalyzeFrame(frame)

    // Context tracking runs on EVERY frame's metadata, including frames the
    // privacy gate rejects: leaving a banking tab and coming back is a real
    // context switch, and the assistants must learn about it even though they
    // never see the bank's pixels — or its title (see the protocol contract).
    const contextChanged = this.checkContextSwitch(frame, allowed)

    if (!allowed) return
    this.lastAllowedFrame = frame

    const now = this.deps.now()

    // Change-gated distribution (distributionGate.ts): a settling debounce wins
    // over a fresh decision, so rapid app-hopping produces ONE distribution of
    // the latest frame rather than one per hop.
    if (this.pendingFlushAt !== null) {
      if (contextChanged) this.pendingFlushAt = now + DEBOUNCE_MS // context moved again — resettle
      // ...but a context that changes on EVERY frame (a title carrying a counter
      // the normalizer doesn't strip, or a user hopping apps nonstop) would push
      // the debounce out forever and starve the assistants completely. The
      // fallback interval is the floor: once it has elapsed, distribute anyway.
      const starved =
        this.lastDistributedAt !== null &&
        now - this.lastDistributedAt >= fallbackIntervalMs(frame.app)
      if (now < this.pendingFlushAt && !starved) return
      this.flush(frame, now)
      return
    }

    const decision = distributionDecision({
      contextChanged,
      app: frame.app,
      now,
      lastDistributedAt: this.lastDistributedAt
    })
    if (decision === 'skip') return
    if (decision === 'scheduleDebounce') {
      this.pendingFlushAt = now + DEBOUNCE_MS
      return
    }
    this.flush(frame, now)
  }

  private flush(frame: RewindFrame, now: number): void {
    this.pendingFlushAt = null
    this.lastDistributedAt = now
    this.distribute(frame, now)
  }

  /** Returns whether this frame is a context switch. */
  private checkContextSwitch(frame: RewindFrame, allowed: boolean): boolean {
    const app = frame.app
    const title = frame.windowTitle
    if (!this.hasContext) {
      // First frame ever — there is no "from", so nothing switched.
      this.hasContext = true
      this.trackedApp = app
      this.trackedTitle = title
      return false
    }
    if (!didContextChange(this.trackedApp, this.trackedTitle, app, title)) return false

    this.trackedApp = app
    this.trackedTitle = title

    // Fire-and-forget, in parallel: no ordering guarantee across assistants, and
    // a slow/throwing hook must not stall the loop. A privacy-denied context is
    // reported WITHOUT its title.
    const departing = this.lastAllowedFrame
    const reportedTitle = allowed ? title : null
    for (const a of this.assistants.values()) {
      if (!a.onContextSwitch) continue
      void Promise.resolve(a.onContextSwitch(departing, app, reportedTitle)).catch((e) =>
        console.warn(`[assistants] ${a.identifier}.onContextSwitch failed:`, e)
      )
    }

    const now = this.deps.now()
    // Already inside a quiet window → don't extend it (Mac's isInDelayPeriod
    // guard), or rapid app-hopping would defer analysis indefinitely.
    if (this.delayUntil !== null && now < this.delayUntil) return true
    this.delayUntil = now + this.deps.analysisDelayMs()
    this.clearAllPendingWork()
    return true
  }

  private clearAllPendingWork(): void {
    for (const a of this.assistants.values()) {
      if (!a.clearPendingWork) continue
      void Promise.resolve(a.clearPendingWork()).catch((e) =>
        console.warn(`[assistants] ${a.identifier}.clearPendingWork failed:`, e)
      )
    }
  }

  private distribute(frame: RewindFrame, now: number): void {
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
let settingsHooked = false

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
  hookSettingsChanges()
  syncAssistantCoordinator()
}

/** Re-read the master toggle and start/stop the loop accordingly. */
export function syncAssistantCoordinator(): void {
  const coordinator = getAssistantCoordinator()
  if (getAppSettings().screenAnalysisEnabled) coordinator.start()
  else coordinator.stop()
}

/** Without this the master toggle is one-way: `tick()` re-checks the setting so
 *  turning it OFF works, but nothing re-arms the timer when it goes back ON —
 *  the feature would stay dead until the next app launch. Any writer of
 *  AppSettings (a Settings toggle, a backend sync) now re-syncs the loop. */
function hookSettingsChanges(): void {
  if (settingsHooked) return
  settingsHooked = true
  onAppSettingsChanged(() => syncAssistantCoordinator())
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
  settingsHooked = false
}
