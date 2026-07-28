// The Insight assistant — Mac's two-phase tool-calling "Advice" pipeline on
// Windows. It is the coordinator's peer to Focus, but far simpler in cadence: a
// fixed extraction interval, no cooldown, no error backoff, no transition state
// machine, and — the hard, unambiguous difference from Focus — NO glow. Insight
// only ever fires a (throttled) notification.
//
// analyze() runs the whole pipeline and returns null (side effects inside), like
// Focus and Mac. The coordinator serializes Insight to one in-flight analysis; a
// monotonic seq guard additionally protects the dev analyzeNow path from writing
// a stale result over a newer coordinator run.
//
// Titles, OCR, SQL results and profile text are NEVER logged — only app names,
// verdict counts, and confidence percentages.
import { getInsightSettings } from '../../insight/state'
import { notificationsActive, notifyProactive } from '../core/notify'
import { readFrameImageBase64 } from '../core/frameImage'
import { getBackendSession, getSessionEpoch } from '../core/session'
import { runReadonlySelect, rewindFramesByIds } from '../../ipc/db'
import type { AssistantResult, ProactiveAssistant } from '../core/coordinator'
import type { RewindFrame } from '../../../shared/types'
import { runTwoPhasePipeline, type PipelineResult } from './gemini'
import { executeSql, loadScreenshotBase64 } from './sql'
import { getInsightAnalysisPrompt } from './promptStore'
import { getUserLanguage, loadInsightContext, MAX_LOOKBACK_MS } from './context'
import { buildPhase1Prompt, buildPhase2Prompt, buildSystemPrompt } from './prompt'
import { insightFrameAllowed, intervalElapsed, MIN_CONFIDENCE, passesConfidence } from './gating'
import { persistInsight, toPayload } from './persist'

const IDENTIFIER = 'insight'

export class InsightAssistant implements ProactiveAssistant {
  readonly identifier = IDENTIFIER
  readonly displayName = 'Insight'

  /** When the last extraction ran — the lookback window anchors to this. */
  private lastAnalysisAtMs = 0
  /** Monotonic run id; a result whose run is older than the last committed run is
   *  discarded (guards the dev analyzeNow path vs a coordinator run). */
  private seq = 0
  private lastCommittedSeq = -1
  private stopped = false

  /** Master gate. On Windows `enabled` is the Insight feature toggle
   *  (InsightSettings). DEVIATION from Mac's `isEnabled && notificationsEnabled`:
   *  because Insight has NO glow, a run whose notification can't be delivered
   *  produces zero visible output — pure wasted spend. So we additionally require
   *  that a notification WOULD actually be deliverable (master on AND frequency > 0
   *  AND not snoozed), reusing notify.ts's own suppression reads. NOT gated on the
   *  per-interval rate limit — that is "not yet", not "silenced". Net effect: at
   *  the default Off frequency the pipeline never runs ($0); raising the frequency
   *  turns it on. (Focus is untouched: it glows, so it keeps running when toasts
   *  are off.) */
  isEnabled(): boolean {
    if (this.stopped) return false
    return getInsightSettings().enabled && notificationsActive(this.identifier)
  }

  /** Insight's only cadence control: the fixed extraction interval. DEVIATION: the
   *  live interval is the existing Windows InsightSettings.intervalMin picker (so
   *  that Settings control keeps working), not Mac's raw 600s default. */
  private effectiveIntervalMs(): number {
    const min = getInsightSettings().intervalMin
    return Math.max(1, Number.isFinite(min) ? min : 15) * 60_000
  }

  shouldAnalyze(_frameNumber: number, timeSinceLastAnalysisMs: number): boolean {
    return intervalElapsed(timeSinceLastAnalysisMs, this.effectiveIntervalMs())
  }

  /** The whole pipeline; always returns null (side effects inside). */
  async analyze(frame: RewindFrame): Promise<AssistantResult | null> {
    // The three-way denylist (builtin ∪ private ∪ user list). The coordinator
    // already applied builtin+private; the USER leg is Insight's own and must be
    // checked here (Mac checks the full three-way before enqueue).
    if (!insightFrameAllowed(frame, getInsightSettings().denylist ?? [])) return null
    await this.runPipeline(frame)
    return null
  }

  // Present to satisfy the protocol; all side effects happen inside analyze().
  handleResult(): void {
    /* intentionally empty */
  }

  stop(): void {
    this.stopped = true
  }

  // --- Internals --------------------------------------------------------------

  private async runPipeline(frame: RewindFrame): Promise<void> {
    const mySeq = ++this.seq
    console.log(`[insight] analyzing frame app=${frame.app}`)

    const session = getBackendSession()
    if (!session) {
      console.log('[insight] no backend session yet — skipping analysis')
      return
    }
    // Pin the epoch BEFORE the long pipeline. persist re-checks it right before
    // each write/sync so an insight formed under this session is never written
    // into the next user's data if the user signs out mid-analysis.
    const sessionEpoch = getSessionEpoch()

    const now = new Date()
    const nowMs = now.getTime()
    const lookbackStartMs = Math.max(this.lastAnalysisAtMs, nowMs - MAX_LOOKBACK_MS)
    this.lastAnalysisAtMs = nowMs

    // The user denylist gates EVERYTHING sent to Gemini, not just the trigger
    // frame: it is excluded from the Phase-1 activity summary AND from execute_sql
    // (so the model physically cannot retrieve a denylisted app's rows).
    const denylist = getInsightSettings().denylist ?? []

    let result: PipelineResult
    try {
      const language = await getUserLanguage(nowMs)
      const systemPrompt = buildSystemPrompt(getInsightAnalysisPrompt(), language)
      const phase1Prompt = buildPhase1Prompt(
        loadInsightContext({ frame, now, lookbackStartMs, denylist })
      )

      result = await runTwoPhasePipeline({
        session,
        systemPrompt,
        phase1Prompt,
        buildPhase2Prompt,
        execSql: (query) => executeSql(query, runReadonlySelect, denylist),
        loadScreenshot: (id) =>
          loadScreenshotBase64(id, {
            getFramesByIds: rewindFramesByIds,
            readImageBase64: readFrameImageBase64
          })
      })
    } catch (e) {
      // Errors are just logged (no backoff — Mac); the next interval retries.
      console.warn('[insight] pipeline error:', e instanceof Error ? e.name : 'Error')
      return
    }

    const insight = result.insight
    if (!insight) {
      console.log(`[insight] no insight (sql=${result.sqlCount})`)
      return
    }

    // Confidence filter (Mac's 0.85 default), applied before any side effect.
    if (!passesConfidence(insight.confidence)) {
      console.log(
        `[insight] filtered: ${Math.round(insight.confidence * 100)}% < ${Math.round(
          MIN_CONFIDENCE * 100
        )}%`
      )
      return
    }

    // Stale-result guard: a newer run already committed while this one was in the
    // pipeline (the dev analyzeNow path can overlap a coordinator run).
    if (mySeq <= this.lastCommittedSeq) {
      console.log('[insight] discarding stale insight')
      return
    }
    this.lastCommittedSeq = mySeq

    // Dual-write (epoch-guarded inside). Only notify when the write actually
    // landed — a session change drops it rather than notifying the new user with
    // the departed session's insight.
    const rowId = persistInsight(insight, sessionEpoch)
    if (rowId == null) return

    console.log(
      `[insight] delivered category=${insight.category} conf=${Math.round(insight.confidence * 100)}%`
    )
    // Through the shared throttle (default frequency Off → silent until the user
    // opts in). Insight NEVER glows.
    notifyProactive(this.identifier, toPayload(insight))
  }

  /** Dev/QA hook: force one extraction of a given frame, bypassing ONLY the
   *  interval cadence. The privacy + user-denylist gate and the session/epoch
   *  guard inside runPipeline still apply. */
  async analyzeNowForDev(frame: RewindFrame): Promise<void> {
    if (!insightFrameAllowed(frame, getInsightSettings().denylist ?? [])) {
      console.log('[insight] analyzeNow skipped — denylist/privacy gate')
      return
    }
    await this.runPipeline(frame)
  }
}

// --- Runtime singleton -------------------------------------------------------

let singleton: InsightAssistant | null = null

/** The one Insight assistant. */
export function getInsightAssistant(): InsightAssistant {
  if (!singleton) singleton = new InsightAssistant()
  return singleton
}

/** Test-only: drop the singleton. */
export function _resetInsightAssistant(): void {
  singleton = null
}
