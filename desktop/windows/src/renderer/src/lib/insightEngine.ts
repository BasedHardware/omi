// src/renderer/src/lib/insightEngine.ts
import { generate } from './geminiClient'
import { isPrivateWindow, isDeniedContext, redactFrameFields } from './screenRedact'
import { summarizeActivity } from './insightActivity'
import { buildInsightPrompt, parseInsightResponse, INSIGHT_RESPONSE_SCHEMA } from './insightPrompt'
import { selectInsight } from './insightGate'
import type { RewindFrame } from '../../../shared/types'

const MODEL = (import.meta.env.VITE_GEMINI_MODEL as string) || 'gemini-2.5-flash'
const LOOKBACK_MS = 60 * 60 * 1000
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

// One extraction pass. Best-effort: never throws. Returns true if an insight was shown.
export async function runInsightOnce(): Promise<boolean> {
  if (running) return false
  running = true
  try {
    const settings = await window.omi.insightGetSettings()
    if (!settings.enabled) return false
    // Only runs when Rewind is actually capturing (no frames otherwise).
    const rewind = await window.omi.rewindGetSettings()
    if (!rewind.captureEnabled) return false

    const now = Date.now()
    const frames = await window.omi.rewindFrames(now - LOOKBACK_MS, now)
    const allowed = filter(frames)
    if (allowed.length === 0) {
      await window.omi.insightSetSettings({ lastRunAt: now })
      return false
    }

    const redacted = allowed.map(redactFrameFields)
    const summary = summarizeActivity(redacted, SUMMARY_BUDGET)
    if (!summary) {
      await window.omi.insightSetSettings({ lastRunAt: now })
      return false
    }

    const recent = await window.omi.insightRecent(RECENT_FOR_DEDUPE)
    const recentHeadlines = recent.map((r) => r.headline)

    const raw = await generate({
      model: MODEL,
      parts: [{ text: buildInsightPrompt(summary, recentHeadlines) }],
      responseSchema: INSIGHT_RESPONSE_SCHEMA as unknown as Record<string, unknown>
    })
    const insight = selectInsight(parseInsightResponse(raw), { threshold: THRESHOLD, recentHeadlines })

    await window.omi.insightSetSettings({ lastRunAt: now })
    if (!insight) return false
    await window.omi.insightAdd(insight)
    window.omi.insightShow(insight)
    return true
  } catch (e) {
    console.warn('[insight] run failed', e)
    return false
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
