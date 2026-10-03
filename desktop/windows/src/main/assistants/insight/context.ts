// The grounding behind Insight's Phase-1 prompt: the AI user profile (a local
// read), the SQL activity summary (a local aggregate), and the previous-insights
// dedupe list (a local read). The preferred-language directive comes from
// core/outputLanguage.
//
// NO goals/tasks/core-memories block — that is Focus-only (Mac's Insight has no
// such context). Every source is best-effort; nothing here throws.
import { getLatestProfileText } from '../aiUserProfile/service'
import { rewindActivityAggregate, recentInsights } from '../../ipc/db'
import type { RewindFrame } from '../../../shared/types'
import type { ActivityRow, InsightContextData } from './prompt'
import { MAX_INSIGHTS_IN_PROMPT } from './prompt'

/** Mac's `max(lastAnalysisTime, now - 3600s)` lookback cap. */
export const MAX_LOOKBACK_MS = 3_600_000

/** Assemble the Phase-1 context data. All local reads; the lookback window is
 *  [lookbackStartMs, now]. `denylist` (the user's Insight denylist) is threaded
 *  into the activity aggregate so a denylisted app's names/titles never appear in
 *  the prompt — even when Insight triggered on a different, allowed app. */
export function loadInsightContext(args: {
  frame: Pick<RewindFrame, 'app' | 'windowTitle'>
  now: Date
  lookbackStartMs: number
  denylist: string[]
}): InsightContextData {
  const nowMs = args.now.getTime()
  const activity: ActivityRow[] = rewindActivityAggregate(
    args.lookbackStartMs,
    nowMs,
    30,
    args.denylist
  ).map((r) => ({
    app: r.app,
    windowTitle: r.windowTitle,
    count: r.count,
    firstSeen: r.firstSeen,
    lastSeen: r.lastSeen
  }))
  const spanMinutes = Math.max(0, (nowMs - args.lookbackStartMs) / 60_000)
  const previousInsights = recentInsights(MAX_INSIGHTS_IN_PROMPT)
    .map((r) => r.advice)
    .filter((s) => s.trim().length > 0)

  return {
    currentApp: args.frame.app || 'Unknown',
    currentWindowTitle: args.frame.windowTitle || null,
    now: args.now,
    profileText: getLatestProfileText(),
    activity,
    activitySpanMinutes: spanMinutes,
    previousInsights
  }
}
