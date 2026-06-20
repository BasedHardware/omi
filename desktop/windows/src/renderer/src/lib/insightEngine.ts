// src/renderer/src/lib/insightEngine.ts
import { generate } from './geminiClient'
import { isPrivateWindow, isDeniedContext, redactFrameFields } from './screenRedact'
import { summarizeActivity } from './insightActivity'
import { buildInsightPrompt, parseInsightResponse, INSIGHT_RESPONSE_SCHEMA } from './insightPrompt'
import { selectInsight } from './insightGate'
import type { RewindFrame } from '../../../shared/types'

const MODEL = (import.meta.env.VITE_GEMINI_MODEL as string) || 'gemini-2.5-flash'
const LOOKBACK_MS = 60 * 60 * 1000
// A forced (test) run looks back only a short window so the summary is dominated
// by the CURRENT screen — a scheduled run's 60-min history would let the model
// surface something from minutes ago, which reads as "the insight is a bit old".
const FORCE_LOOKBACK_MS = 90 * 1000
const SUMMARY_BUDGET = 12_000
const THRESHOLD = 0.85 // matches macOS Insight minConfidence (stricter → fewer, better toasts)
const RECENT_FOR_DEDUPE = 30

let running = false
let started = false
let timer: ReturnType<typeof setTimeout> | null = null

function filter(frames: RewindFrame[]): RewindFrame[] {
  return frames.filter(
    (f) =>
      !isPrivateWindow(f.windowTitle) &&
      !isDeniedContext({ app: f.app, windowTitle: f.windowTitle, processName: f.processName })
  )
}

/** Outcome of a single insight pass — lets a caller (e.g. the Settings "test"
 *  button) report WHY nothing was shown instead of a bare false. */
export type InsightRunResult =
  | { shown: true }
  | { shown: false; reason: 'busy' | 'disabled' | 'capture-off' | 'no-activity' | 'no-insight' | 'error' }

// One extraction pass. Best-effort: never throws.
//
// `force` is for the Settings "test" button: it makes the pass surface a real
// insight built from the CURRENT screen activity on demand — bypassing the
// feature toggle, the confidence threshold, and the recent-headline dedupe (all
// of which can legitimately suppress a scheduled run). It still honours capture
// being on (no frames otherwise) and the privacy redaction/filter. Forced runs
// don't touch `lastRunAt`, so testing never disturbs the normal cadence.
export async function runInsightOnce(opts: { force?: boolean } = {}): Promise<InsightRunResult> {
  const force = !!opts.force
  if (running) return { shown: false, reason: 'busy' }
  running = true
  try {
    const settings = await window.omi.insightGetSettings()
    if (!settings.enabled && !force) return { shown: false, reason: 'disabled' }
    // Only runs when Rewind is actually capturing (no frames otherwise).
    const rewind = await window.omi.rewindGetSettings()
    if (!rewind.captureEnabled) return { shown: false, reason: 'capture-off' }

    const now = Date.now()
    const frames = await window.omi.rewindFrames(now - (force ? FORCE_LOOKBACK_MS : LOOKBACK_MS), now)
    const redacted = filter(frames).map(redactFrameFields)
    let summary = summarizeActivity(redacted, SUMMARY_BUDGET)

    if (force) {
      // Anchor the forced test on the LIVE current screen (kept hot by the capture
      // pipeline), appended last so it reads as "now". This guarantees the insight
      // reflects what's on screen at this moment even if the very latest frame
      // hasn't been OCR'd into the DB yet — the cause of a "slightly old" test result.
      const live = (await window.omi.screenReadText().catch(() => '')).trim()
      if (live) {
        const liveBlock = `## Current screen (now)\n${live}`
        const room = SUMMARY_BUDGET - liveBlock.length - 2
        summary = summary && room > 0 ? `${summary.slice(0, room)}\n\n${liveBlock}` : liveBlock.slice(0, SUMMARY_BUDGET)
      }
    }

    if (!summary) {
      if (!force) await window.omi.insightSetSettings({ lastRunAt: now })
      return { shown: false, reason: 'no-activity' }
    }

    const recent = await window.omi.insightRecent(RECENT_FOR_DEDUPE)
    const recentHeadlines = recent.map((r) => r.headline)

    const raw = await generate({
      model: MODEL,
      parts: [{ text: buildInsightPrompt(summary, recentHeadlines, { force }) }],
      responseSchema: INSIGHT_RESPONSE_SCHEMA as unknown as Record<string, unknown>
    })
    // Forced test: take the top candidate regardless of confidence/dedupe so the
    // user always sees the real insight generated from their current screen.
    const insight = selectInsight(parseInsightResponse(raw), {
      threshold: force ? 0 : THRESHOLD,
      recentHeadlines: force ? [] : recentHeadlines
    })

    if (!force) await window.omi.insightSetSettings({ lastRunAt: now })
    if (!insight) return { shown: false, reason: 'no-insight' }
    await window.omi.insightAdd(insight)
    window.omi.insightShow(insight)
    return { shown: true }
  } catch (e) {
    console.warn('[insight] run failed', e)
    return { shown: false, reason: 'error' }
  } finally {
    running = false
  }
}

// Start the engine once (idempotent). A self-rescheduling timeout re-reads the
// configured interval each cycle, so a Settings change takes effect without a
// restart. `started` is set SYNCHRONOUSLY (before any await) so StrictMode's
// double-mount / Home remounts can't start a second loop. runInsightOnce is
// gated on settings internally, so ticks while disabled are cheap no-ops.
export function maybeStartInsightEngine(): void {
  if (started) return
  started = true
  const schedule = (delayMs: number): void => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      await runInsightOnce()
      const s = await window.omi.insightGetSettings().catch(() => null)
      const intervalMs = Math.max(1, s?.intervalMin ?? 15) * 60 * 1000
      schedule(intervalMs)
    }, delayMs)
  }
  schedule(60_000) // first pass ~1 min after launch
}
