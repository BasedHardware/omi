// The Task assistant — Mac's screen→task extractor on Windows. The fourth
// coordinator peer (with Focus, Insight, Memory). It watches whitelisted screen
// frames and, on a context switch (primary trigger), a fallback tick, or the
// messaging fast-path, runs the single-phase multi-tool Gemini loop
// (loop.ts), applies a confidence gate, and stages each extracted task through
// the create → sync → embed → promote lifecycle (create.ts). No glow, no
// notification in PR-B — it stages durable tasks silently.
//
// TRIGGERS (spec §3, a mechanism-only deviation from Mac's internal trigger
// actor with identical net behavior — Mac's trigger stream collapses into the
// coordinator's two seams):
//   * analyze()        — the coordinator's cadence path. shouldAnalyze gates it
//                        with the effective interval (15s for a messaging app,
//                        else taskFallbackIntervalMin·60s), realizing both the
//                        messaging fast-path and the 600s fallback tick.
//   * onContextSwitch()— the PRIMARY trigger. Extracts from the DEPARTING frame
//                        the moment the user leaves a context. Fires fire-and-
//                        forget from the coordinator, in parallel with analyze,
//                        so runPipeline takes a re-entrancy lock and a per-window
//                        dedupe so the two paths can't overlap or double-analyze.
//
// Both triggers call the SAME runPipeline(frame, epoch). It pins the session
// epoch before the (long) Gemini loop and re-checks it before every write
// (Memory's discipline); a monotonic seq additionally guards the dev analyzeNow
// path. Titles, OCR and task contents are NEVER logged — only app names + counts.
import { getAppSettings } from '../../appSettings'
import { mayAnalyzeFrame } from '../core/privacy'
import { readFrameImageBase64 } from '../core/frameImage'
import { getBackendSession, getSessionEpoch } from '../core/session'
import { intervalElapsed } from '../insight/gating'
import type { AssistantResult, ProactiveAssistant } from '../core/coordinator'
import type { RewindFrame } from '../../../shared/types'
import { isAppAllowed, isMessagingApp, isPromptMessagingApp, isWindowAllowed } from './appLists'
import { runExtractionLoop } from './loop'
import { createStagedTaskFromExtraction } from './create'
import type { ExtractedTask } from './models'

const IDENTIFIER = 'tasks'

/** The messaging fast-path effective interval (Mac `messagingFastPathDelay`, 15s):
 *  a hot chat window re-analyzes ~every 15s instead of the 600s fallback. */
const MESSAGING_INTERVAL_MS = 15_000

/** Per-window dedupe TTL (Mac `analysisDelay`, 60s) for non-messaging apps; the
 *  same window analyzed within this window is skipped. Distinct from the fallback
 *  cadence interval (600s) — this is the context-switch trigger's own throttle. */
const DEDUPE_TTL_MS = 60_000

/** Pure app/window gate (spec §3 steps 2–4): a frame is eligible for extraction
 *  when its app is NOT on the user's `taskExcludedApps`, IS on the positive
 *  whitelist (Task gates on the whitelist, not the shared exclude list), AND —
 *  for a browser — the window title clears the keyword filter. Exported so the
 *  gate is unit-tested in isolation. */
export function shouldExtractForApp(
  app: string,
  windowTitle: string,
  excludedApps: readonly string[]
): boolean {
  if (isTaskExcluded(app, excludedApps)) return false
  return isAppAllowed(app) && isWindowAllowed(app, windowTitle)
}

/** The user's excluded-apps leg (Mac's `isExcludedApp`), substring-matched against
 *  the app name with the same lowercased idiom as the whitelist. Pure. */
function isTaskExcluded(app: string, excludedApps: readonly string[]): boolean {
  const a = app.toLowerCase()
  return excludedApps.some((e) => {
    const t = e.trim().toLowerCase()
    return t.length > 0 && a.includes(t)
  })
}

/** "yyyy-MM-dd (EEEE)" — Mac's `todayStr` format fed to buildUserPrompt. */
function formatToday(d: Date = new Date()): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const weekday = d.toLocaleDateString('en-US', { weekday: 'long' })
  return `${y}-${m}-${day} (${weekday})`
}

export class TaskAssistant implements ProactiveAssistant {
  readonly identifier = IDENTIFIER
  readonly displayName = 'Tasks'

  /** Monotonic run id; a result whose run is older than the last committed run is
   *  discarded (guards the dev analyzeNow path vs a coordinator run). */
  private seq = 0
  private lastCommittedSeq = -1
  private stopped = false

  /** Re-entrancy lock shared by BOTH triggers (analyze + onContextSwitch), so a
   *  context-switch run and a coordinator analyze run can never overlap for this
   *  assistant (spec §3 — the coordinator serializes analyze via its own set, but
   *  fires onContextSwitch in parallel). */
  private running = false

  /** The last frame that reached a trigger (analyze or onContextSwitch), used as
   *  the departing-frame fallback when the coordinator has none. */
  private latestFrame: RewindFrame | null = null
  /** The app of the most recent frame/context, so shouldAnalyze (which is handed
   *  no frame) can pick the messaging vs fallback interval. */
  private latestFrameApp = ''

  /** Per-window dedupe: `app::title` → last-analyzed epoch-ms. Mac's `analyzedKey`
   *  TTL map — 15s messaging, 60s otherwise. */
  private readonly analyzedWindows = new Map<string, number>()

  /** Master gate: `taskEnabled` ONLY (default OFF — opt-in; decoupled from
   *  notifications, per DECIDED #1 / Deviation D2). The coordinator's
   *  `screenAnalysisEnabled` master already gates the whole loop for every peer,
   *  so it is NOT re-checked here. */
  isEnabled(): boolean {
    if (this.stopped) return false
    return getAppSettings().taskEnabled
  }

  /** Fallback cadence (spec §3c) with the messaging fast-path folded in: the
   *  effective interval is 15s for a messaging app, else `taskFallbackIntervalMin`
   *  minutes (Mac's 600s default). */
  private effectiveIntervalMs(app: string): number {
    if (isMessagingApp(app)) return MESSAGING_INTERVAL_MS
    const min = getAppSettings().taskFallbackIntervalMin
    return Math.max(1, Number.isFinite(min) ? min : 10) * 60_000
  }

  shouldAnalyze(_frameNumber: number, timeSinceLastAnalysisMs: number): boolean {
    return intervalElapsed(timeSinceLastAnalysisMs, this.effectiveIntervalMs(this.latestFrameApp))
  }

  /** Cadence/fallback path. Records the latest frame, applies the whitelist/window
   *  gate, then runs the pipeline. Always returns null (side effects inside). */
  async analyze(frame: RewindFrame): Promise<AssistantResult | null> {
    this.latestFrame = frame
    this.latestFrameApp = frame.app
    if (!shouldExtractForApp(frame.app, frame.windowTitle ?? '', getAppSettings().taskExcludedApps)) {
      return null
    }
    await this.runPipeline(frame)
    return null
  }

  // Present to satisfy the protocol; all side effects happen inside analyze().
  handleResult(): void {
    /* intentionally empty — tasks are staged inside the pipeline, like Insight */
  }

  /**
   * PRIMARY trigger: the user left a context. Extract from the DEPARTING frame
   * (Mac's `.contextSwitch`). The coordinator fires this fire-and-forget and does
   * NOT apply isEnabled/shouldAnalyze here (those live on the cadence path), so we
   * self-gate on isEnabled. `newWindowTitle` may be null (the new context failed
   * the privacy gate) — irrelevant, since we prompt on the departing frame.
   */
  async onContextSwitch(
    departingFrame: RewindFrame | null,
    newApp: string,
    _newWindowTitle: string | null
  ): Promise<void> {
    // Keep the cadence interval current even when this switch doesn't extract.
    this.latestFrameApp = newApp
    if (!this.isEnabled()) return

    const frame = departingFrame ?? this.latestFrame
    if (!frame) return
    if (!shouldExtractForApp(frame.app, frame.windowTitle ?? '', getAppSettings().taskExcludedApps)) {
      return
    }
    await this.runPipeline(frame)
  }

  stop(): void {
    this.stopped = true
  }

  // --- Internals --------------------------------------------------------------

  private analyzedKey(frame: RewindFrame): string {
    return `${frame.app}::${frame.windowTitle ?? ''}`
  }

  private dedupeTtlMs(app: string): number {
    return isMessagingApp(app) ? MESSAGING_INTERVAL_MS : DEDUPE_TTL_MS
  }

  /**
   * The shared extraction pipeline for both triggers. Re-entrancy-locked (so the
   * two triggers can't overlap), per-window deduped (so a hot window isn't re-run
   * every 3s coordinator tick), session/epoch/seq guarded. Runs the tool loop,
   * then stages each returned task that clears the confidence gate.
   */
  private async runPipeline(frame: RewindFrame, opts?: { bypassDedupe?: boolean }): Promise<void> {
    if (this.running) return // a context-switch run and an analyze run can't overlap
    this.running = true
    try {
      const key = this.analyzedKey(frame)
      const now = Date.now()
      if (!opts?.bypassDedupe) {
        const last = this.analyzedWindows.get(key) ?? -Infinity
        if (now - last < this.dedupeTtlMs(frame.app)) return // same window, within TTL
      }
      this.analyzedWindows.set(key, now)

      const mySeq = ++this.seq
      console.log(`[tasks] analyzing frame app=${frame.app}`)

      const session = getBackendSession()
      if (!session) {
        console.log('[tasks] no backend session yet — skipping analysis')
        return
      }
      // Pin the epoch BEFORE the long Gemini loop; create.ts re-checks it right
      // before every write, so a task formed under this session is never written
      // into the next user's data if the user signs out mid-analysis.
      const sessionEpoch = getSessionEpoch()

      const imageBase64 = await readFrameImageBase64(frame)
      if (!imageBase64) {
        console.log('[tasks] frame image missing — skipping')
        return
      }

      let results: ExtractedTask[]
      try {
        results = await runExtractionLoop({
          session,
          app: frame.app,
          today: formatToday(),
          isMessaging: isPromptMessagingApp(frame.app),
          imageBase64
        })
      } catch (e) {
        // Transport already retried + ran the fallback model; a throw here means no
        // tasks this cycle. Log the name only (never the body) and move on.
        console.warn('[tasks] extraction error:', e instanceof Error ? e.name : 'Error')
        return
      }

      if (results.length === 0) {
        console.log('[tasks] no task extracted')
        return
      }

      // Stale-result guard: a newer run committed while this one was in the loop
      // (the dev analyzeNow path can overlap a coordinator run in principle).
      if (mySeq <= this.lastCommittedSeq) {
        console.log('[tasks] discarding stale extraction')
        return
      }
      this.lastCommittedSeq = mySeq

      // Confidence gate (spec §5 step 1) + stage each task. The user's threshold is
      // applied here AND passed to create.ts so the two gates agree (create's own
      // default is 0.75; a user who lowered the bar must not be double-filtered).
      const minConfidence = getAppSettings().taskMinConfidence
      let staged = 0
      for (const task of results) {
        if (task.confidence < minConfidence) continue
        // Bail the whole batch if the session departed mid-loop — don't write a
        // departed user's tasks (create.ts also re-checks, belt-and-suspenders).
        if (getSessionEpoch() !== sessionEpoch) return
        await createStagedTaskFromExtraction(task, frame, sessionEpoch, undefined, minConfidence)
        staged++
      }
      console.log(`[tasks] staged ${staged}/${results.length} extracted task(s)`)
    } finally {
      this.running = false
    }
  }

  /** Dev/QA hook: force one extraction of a given frame, bypassing ONLY the cadence
   *  + per-window dedupe. Every privacy/safety gate the coordinator applies in
   *  production is still enforced: the frame privacy gate, the whitelist/window
   *  gate, and the session/epoch guard inside runPipeline. */
  async analyzeNowForDev(frame: RewindFrame): Promise<void> {
    if (!mayAnalyzeFrame(frame)) {
      console.log('[tasks] analyzeNow skipped — privacy gate')
      return
    }
    if (!shouldExtractForApp(frame.app, frame.windowTitle ?? '', getAppSettings().taskExcludedApps)) {
      console.log('[tasks] analyzeNow skipped — not a whitelisted app/window')
      return
    }
    await this.runPipeline(frame, { bypassDedupe: true })
  }
}

// --- Runtime singleton -------------------------------------------------------

let singleton: TaskAssistant | null = null

/** The one Task assistant. Created on first use so tests can construct their own. */
export function getTaskAssistant(): TaskAssistant {
  if (!singleton) singleton = new TaskAssistant()
  return singleton
}

/** Test-only: drop the singleton. */
export function _resetTaskAssistant(): void {
  singleton = null
}
