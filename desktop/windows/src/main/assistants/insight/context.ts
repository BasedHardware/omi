// The grounding behind Insight's Phase-1 prompt: the AI user profile (a local
// read), the SQL activity summary (a local aggregate), and the previous-insights
// dedupe list (a local read). PLUS the user's preferred language, cached 1h, used
// only to append Mac's language directive to the system prompt.
//
// NO goals/tasks/core-memories block — that is Focus-only (Mac's Insight has no
// such context). Every source is best-effort; nothing here throws.
import { net } from 'electron'
import { getAbortSignal, getBackendSession } from '../core/session'
import { getLatestProfileText } from '../aiUserProfile/service'
import { rewindActivityAggregate, recentInsights } from '../../ipc/db'
import type { RewindFrame } from '../../../shared/types'
import type { ActivityRow, InsightContextData } from './prompt'
import { MAX_INSIGHTS_IN_PROMPT } from './prompt'

/** Mac's `max(lastAnalysisTime, now - 3600s)` lookback cap. */
export const MAX_LOOKBACK_MS = 3_600_000

const LANGUAGE_TTL_MS = 3_600_000
const LANGUAGE_TIMEOUT_MS = 15_000

let langCache: { at: number; language: string | null } | null = null

/** The user's preferred language, cached 1h. Fail-open to null (no directive) on
 *  no-session, non-OK, or any error — exactly Mac's fallback (empty/"en" → nil).
 *  A null return means "no language override", i.e. English default. */
export async function getUserLanguage(now: number = Date.now()): Promise<string | null> {
  if (langCache && now - langCache.at < LANGUAGE_TTL_MS) return langCache.language
  const session = getBackendSession()
  if (!session) return null
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), LANGUAGE_TIMEOUT_MS)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await net.fetch(`${session.apiBase}/v1/users/language`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.token}` },
      signal: ctrl.signal
    })
    if (!res.ok) return null
    const data = (await res.json()) as { language?: string | null }
    const lang =
      typeof data.language === 'string' && data.language.trim() ? data.language.trim() : null
    // Cache only a successful read; a failure retries next call rather than
    // caching "unknown" for an hour.
    langCache = { at: now, language: lang }
    return lang
  } catch {
    return null
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/** Assemble the Phase-1 context data. All local reads; the lookback window is
 *  [lookbackStartMs, now]. */
export function loadInsightContext(args: {
  frame: Pick<RewindFrame, 'app' | 'windowTitle'>
  now: Date
  lookbackStartMs: number
}): InsightContextData {
  const nowMs = args.now.getTime()
  const activity: ActivityRow[] = rewindActivityAggregate(args.lookbackStartMs, nowMs, 30).map(
    (r) => ({
      app: r.app,
      windowTitle: r.windowTitle,
      count: r.count,
      firstSeen: r.firstSeen,
      lastSeen: r.lastSeen
    })
  )
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

/** Test/teardown: drop the language cache. */
export function _resetInsightLanguageCache(): void {
  langCache = null
}
