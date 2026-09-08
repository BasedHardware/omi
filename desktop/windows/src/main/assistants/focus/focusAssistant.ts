// The Focus assistant — the first real proactive assistant on Windows. It reads
// a screen frame the coordinator hands it, asks Gemini "focused or distracted?"
// grounded in the user's goals/tasks/memories/profile, records the verdict, and
// on a TRANSITION fires the halo and (if opted in) a notification.
//
// The whole pipeline lives in `analyze()`, which returns null — mirroring Mac,
// where `handleResult` is a no-op and `processFrame` does everything. The
// coordinator serializes Focus to one in-flight analysis, so there is no need
// for Mac's internal 3-way task pool: a verdict is fully applied before the next
// frame is offered. (A stale-result guard still protects the dev `analyzeNow`
// path, which can run a pipeline outside the coordinator.)
//
// The pure decisions (skip gating, the transition state machine, the prompt, the
// parse) are all in sibling modules and unit-tested; this file is the wiring —
// the DB, the network, the clock, the glow window — that those modules keep out
// of their own tests.
import { getAppSettings } from '../../appSettings'
import { showGlow } from '../../glow/glowWindow'
import { mayAnalyzeFrame } from '../core/privacy'
import { readFrameImageBase64 } from '../core/frameImage'
import { notifyProactive } from '../core/notify'
import { getBackendSession, getSessionEpoch } from '../core/session'
import type { AssistantResult, ProactiveAssistant } from '../core/coordinator'
import type { FocusSessionStatus, RewindFrame } from '../../../shared/types'
import { analyzeScreenshot } from './gemini'
import { loadFocusContext } from './context'
import { buildFocusPrompt } from './prompt'
import { getFocusSystemPrompt } from './promptStore'
import { persistFocusSession } from './persist'
import { decideTransition, errorBackoffMs, shouldSkipAnalysis, type SkipInput } from './gating'
import type { ScreenAnalysis } from './models'

const IDENTIFIER = 'focus'

// Windows lock screen / secure desktop / screensaver hosts. Capture already
// drops lock-screen frames (rewind/captureDecision), so this is defence in
// depth — never judge (or bill for) the sign-in screen.
const HARD_SKIP = new Set(['lockapp', 'lockapp.exe', 'logonui', 'logonui.exe'])

export class FocusAssistant implements ProactiveAssistant {
  readonly identifier = IDENTIFIER
  readonly displayName = 'Focus'

  // --- Verdict state (all owned here; the pure gaters take it as input) -------
  private lastStatus: FocusSessionStatus | null = null
  private lastNotifiedState: FocusSessionStatus | null = null
  private lastAnalyzedApp: string | null = null
  private lastAnalyzedWindowTitle: string | null = null
  private cooldownEndsAt: number | null = null
  private backoffEndsAt: number | null = null
  private consecutiveErrors = 0
  /** Oldest-first, capped at MAX_HISTORY by prompt.formatHistory's slice — but we
   *  keep the cap here too so the array itself doesn't grow unbounded. */
  private history: ScreenAnalysis[] = []
  /** Monotonic run id; a result whose run is older than the last COMMITTED run is
   *  discarded (Mac's stale-frame guard). */
  private seq = 0
  private lastCommittedSeq = -1
  /** Floor for a run to still be valid: clearPendingWork raises it to the current
   *  seq so any run started before a context switch is discarded even if nothing
   *  newer committed. */
  private minValidSeq = 0
  private stopped = false

  /** Master gate: Mac's rule that a disabled notification setting stops screen
   *  analysis ENTIRELY — "no notification setting, no Gemini call at all" — not
   *  merely a silent verdict. */
  isEnabled(): boolean {
    if (this.stopped) return false
    const s = getAppSettings()
    return s.focusEnabled && s.focusNotificationsEnabled
  }

  /** Mac's Focus opts into delay-window frames only while it believes the user is
   *  distracted, so a refocus is caught promptly instead of waiting out the full
   *  post-switch quiet window. When focused/cold it waits, like Mac. */
  needsFrameDuringDelay(): boolean {
    return this.lastNotifiedState === 'distracted'
  }

  clearPendingWork(): void {
    // The context changed under us; the run in flight is now for a stale context.
    // We can't cancel the awaited pipeline, but bumping seq AND raising the
    // minValidSeq floor to it means its result is discarded rather than applied to
    // the new context. Deliberate deviation from Mac: Mac raises its equivalent of
    // seq but never the floor its guard checks, so this discard is dead on Mac — a
    // stale verdict there can still glow/notify against the NEW window. That is a
    // real UX bug; here the floor makes the discard actually fire.
    this.seq++
    this.minValidSeq = this.seq
  }

  /** The whole pipeline. Returns null always (like Mac) — the verdict's side
   *  effects happen here, not via the coordinator's handleResult. */
  async analyze(frame: RewindFrame): Promise<AssistantResult | null> {
    if (!this.passesLocalGates(frame)) return null
    await this.runPipeline(frame)
    return null
  }

  // The coordinator only calls handleResult when analyze returns non-null; we
  // always return null (all side effects happen inside analyze, like Mac's
  // no-op handleResult + everything-in-processFrame). Present to satisfy the
  // required protocol member.
  handleResult(): void {
    /* intentionally empty — see above */
  }

  stop(): void {
    this.stopped = true
  }

  // --- Internals --------------------------------------------------------------

  /** loginwindow-equivalent + excluded-app + the smart skip gate. Everything
   *  here is synchronous and cheap; the expensive path (context + Gemini) only
   *  runs once these pass. */
  private passesLocalGates(frame: RewindFrame): boolean {
    const proc = (frame.processName || '').toLowerCase()
    const app = (frame.app || '').toLowerCase()
    if (HARD_SKIP.has(proc) || HARD_SKIP.has(app)) return false

    if (this.isExcludedApp(frame)) return false

    const now = Date.now()
    const input: SkipInput = {
      now,
      app: frame.app,
      windowTitle: frame.windowTitle,
      lastAnalyzedApp: this.lastAnalyzedApp,
      lastAnalyzedWindowTitle: this.lastAnalyzedWindowTitle,
      lastStatus: this.lastStatus,
      cooldownEndsAt: this.cooldownEndsAt,
      backoffEndsAt: this.backoffEndsAt
    }
    const decision = shouldSkipAnalysis(input)
    if (decision.skip) return false

    // Commit the analyzed context NOW (Mac: "immediately when queuing"), so the
    // next frame's skip check compares against this frame, not the previous one.
    this.lastAnalyzedApp = frame.app
    this.lastAnalyzedWindowTitle = frame.windowTitle
    return true
  }

  /** The user's excluded-apps check: true when this frame's app OR process name is
   *  in `focusExcludedApps`. Shared by the production gate and the dev path so both
   *  honour the same exclusion list. */
  private isExcludedApp(frame: RewindFrame): boolean {
    const app = (frame.app || '').toLowerCase()
    const proc = (frame.processName || '').toLowerCase()
    const excluded = getAppSettings().focusExcludedApps.map((a) => a.toLowerCase())
    return excluded.includes(app) || (!!proc && excluded.includes(proc))
  }

  private async runPipeline(frame: RewindFrame): Promise<void> {
    const mySeq = ++this.seq
    // Titles are never logged (a title can be "Chase — Log in"); app + status +
    // counts only.
    console.log(`[focus] analyzing frame app=${frame.app}`)

    const session = getBackendSession()
    if (!session) {
      // No relayed session yet — soft no-op, not an error (don't spend backoff).
      console.log('[focus] no backend session yet — skipping analysis')
      return
    }
    // Pin the epoch BEFORE the long Gemini call. persist re-checks it right
    // before the write, so a verdict formed under this session is discarded (not
    // written into the next user's data) if the user signs out mid-analysis.
    const sessionEpoch = getSessionEpoch()

    const imageBase64 = await readFrameImageBase64(frame)
    if (!imageBase64) {
      // The JPEG was swept out from under the row; nothing to judge, not an error.
      console.log('[focus] frame image missing — skipping')
      return
    }

    let analysis: ScreenAnalysis | null
    try {
      const context = await loadFocusContext(new Date())
      const prompt = buildFocusPrompt(context, this.history)
      analysis = await analyzeScreenshot(session, getFocusSystemPrompt(), prompt, imageBase64)
      // A real answer clears the error backoff.
      this.consecutiveErrors = 0
      this.backoffEndsAt = null
    } catch (e) {
      this.consecutiveErrors++
      this.backoffEndsAt = Date.now() + errorBackoffMs(this.consecutiveErrors)
      console.warn(
        `[focus] analysis error (consecutive=${this.consecutiveErrors}):`,
        e instanceof Error ? e.name : 'Error'
      )
      return
    }

    // Unparseable / empty answer: no verdict, but NOT an error (models.ts already
    // decided it can't be trusted). Leave state untouched.
    if (!analysis) {
      console.log('[focus] no usable verdict from model')
      return
    }

    // Stale-result guard: drop the verdict if a newer run already committed while
    // this one was in the Gemini call, OR if the context switched under us
    // (clearPendingWork raised minValidSeq above this run's seq).
    if (mySeq <= this.lastCommittedSeq || mySeq < this.minValidSeq) {
      console.log('[focus] discarding stale verdict')
      return
    }
    this.lastCommittedSeq = mySeq

    this.applyVerdict(analysis, frame, sessionEpoch)
  }

  /** Update rolling state, then run the transition state machine and its side
   *  effects (persist / glow / notify / cooldown). */
  private applyVerdict(analysis: ScreenAnalysis, frame: RewindFrame, sessionEpoch: number): void {
    this.lastStatus = analysis.status
    this.history.push(analysis)
    if (this.history.length > 20) this.history.shift()

    console.log(`[focus] verdict=${analysis.status} app=${analysis.appOrSite}`)

    const action = decideTransition(this.lastNotifiedState, analysis)
    // Advance the notified state first (Mac updates it BEFORE side effects) so a
    // hypothetical overlapping run can't re-fire the same transition.
    this.lastNotifiedState = action.notifiedState

    if (action.persist) {
      persistFocusSession(
        analysis,
        {
          screenshotId: frame.id != null ? String(frame.id) : null,
          windowTitle: frame.windowTitle || null,
          createdAt: Date.now()
        },
        sessionEpoch
      )
    }

    if (action.startCooldown) {
      const minutes = getAppSettings().focusCooldownMinutes
      this.cooldownEndsAt = Date.now() + minutes * 60_000
    }

    if (action.glow) showGlow(action.glow)

    if (action.notifyBody) {
      // Through the shared throttle — default frequency 0 (Off) means this is
      // recorded/judged but silent until the user opts in. Body only; the throttle
      // owns snooze/master/frequency.
      notifyProactive(this.identifier, {
        headline: 'Focus',
        advice: action.notifyBody,
        reasoning: analysis.status === 'distracted' ? 'Distraction detected.' : 'Back on track.',
        category: 'other',
        sourceApp: analysis.appOrSite || 'Omi',
        confidence: 1
      })
    }
  }

  /** Dev/QA hook: force one analysis of a given frame, bypassing ONLY the smart
   *  skip gate (the cooldown/backoff/duplicate-context throttle). Every privacy-
   *  and safety-relevant gate the coordinator applies in production is still
   *  enforced here: the lock-screen hard skip, the frame privacy gate
   *  (`mayAnalyzeFrame` — incognito / bank / password-manager / login pages), the
   *  user's excluded-apps list, and the session/epoch check inside runPipeline.
   *  Used by the `focus:analyzeNow` IPC to exercise the pipeline without waiting
   *  for a natural context switch. */
  async analyzeNowForDev(frame: RewindFrame): Promise<void> {
    const proc = (frame.processName || '').toLowerCase()
    const app = (frame.app || '').toLowerCase()
    if (HARD_SKIP.has(proc) || HARD_SKIP.has(app)) {
      console.log('[focus] analyzeNow: hard-skipped frame')
      return
    }
    // The SAME privacy gate the coordinator runs before every production analyze,
    // so the dev path can never upload an incognito/bank/password-manager frame's
    // pixels to Gemini. Log carries no title/app detail.
    if (!mayAnalyzeFrame(frame)) {
      console.log('[focus] analyzeNow skipped — privacy gate')
      return
    }
    // The SAME user excluded-apps check passesLocalGates enforces.
    if (this.isExcludedApp(frame)) {
      console.log('[focus] analyzeNow skipped — excluded app')
      return
    }
    this.lastAnalyzedApp = frame.app
    this.lastAnalyzedWindowTitle = frame.windowTitle
    await this.runPipeline(frame)
  }
}

// --- Runtime singleton -------------------------------------------------------

let singleton: FocusAssistant | null = null

/** The one Focus assistant. Created on first use so tests can construct their own. */
export function getFocusAssistant(): FocusAssistant {
  if (!singleton) singleton = new FocusAssistant()
  return singleton
}

/** Test-only: drop the singleton. */
export function _resetFocusAssistant(): void {
  singleton = null
}
