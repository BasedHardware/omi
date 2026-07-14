import type { ChatUsageQuota } from './omiApi.generated'
import { fetchChatQuota } from './billing'

// The bar's pre-send chat-quota gate — a port of macOS FloatingBarUsageLimiter
// (Desktop/Sources/FloatingControlBar/FloatingBarUsageLimiter.swift). The bar
// could previously talk past the user's monthly limit: the main window probes
// the quota after a send (UsageLimitTriggerHost), but the bar's send path had no
// gate at all, so a free user over their limit could keep asking from the bar.
//
// Contract (backend /v1/users/me/usage-quota, ChatUsageQuota):
//  - `allowed: false` is the server's verdict — always blocked.
//  - `allowed: true` + a `questions` limit — Mac ALSO blocks locally once
//    used + optimisticDelta >= limit, so back-to-back sends between two server
//    syncs can't slip past the cap. There is no local estimate for `cost_usd`
//    (Architect/Pro) plans, so those trust the server snapshot alone.
//  - No BYOK branch: the backend returns allowed=true / limit=null for BYOK
//    users before anything else (users.py), so trusting `allowed` is enough
//    (Mac's client-side APIKeyService check is a fast path Windows has no UI for).
//
// FAIL-OPEN by design: no snapshot (cold start, network blip, fetch error) =>
// not limited. Mac does the same (`guard let quota = serverQuota else { return
// false }` — "allow the query, the server will enforce"), and the server is the
// real enforcer either way. A network blip must never lock a paying user out of
// their assistant.
//
// Hot path stays network-free: the snapshot is cached and refreshed on mount +
// on every bar reveal. A send only awaits the network in the cold-start case
// where no snapshot exists yet (Mac's lazy pre-query sync,
// FloatingControlBarWindow.swift:4239-4256), and concurrent syncs are deduped.

export type ChatQuotaGate = {
  /** Refresh the snapshot from the server (resets the optimistic delta). Never
   *  throws — a failed sync leaves the previous snapshot in place. */
  sync: () => Promise<void>
  /** Pre-send verdict. Awaits ONE quota fetch only when no snapshot exists yet. */
  check: () => Promise<QuotaVerdict>
  /** Count a query sent since the last server sync (call after a send goes out). */
  recordQuery: () => void
  /** Test/seam: apply a snapshot directly. */
  applyQuota: (quota: ChatUsageQuota) => void
  isLimitReached: () => boolean
}

export type QuotaVerdict = { blocked: false } | { blocked: true; message: string }

/** Mac's FloatingBarUsageLimiter.limitDescription. */
export function limitDescription(quota: ChatUsageQuota | null): string {
  const limit = quota?.limit
  if (!quota || limit == null) return 'your monthly free message limit'
  if (quota.unit === 'cost_usd') {
    return `your $${limit.toFixed(0)} ${quota.plan} monthly spend limit`
  }
  return `${Math.round(limit)} ${quota.plan} messages this month`
}

/** The blocked-send copy, verbatim from Mac's floating bar (typed bubble AND the
 *  spoken line — FloatingControlBarWindow.swift:4262 / :4453). */
export function limitMessage(quota: ChatUsageQuota | null): string {
  return `You've reached ${limitDescription(quota)}. Upgrade to keep chatting without restrictions.`
}

/** Mac's FloatingBarUsageLimiter.isLimitReached, minus the BYOK fast path (see
 *  the header: the backend already exempts BYOK server-side). */
export function isLimitReached(quota: ChatUsageQuota | null, optimisticDelta: number): boolean {
  if (!quota) return false
  if (quota.allowed === false) return true
  if (quota.unit !== 'questions' || quota.limit == null) return false
  return (quota.used ?? 0) + optimisticDelta >= quota.limit
}

export function createChatQuotaGate(
  fetchQuota: () => Promise<ChatUsageQuota> = fetchChatQuota
): ChatQuotaGate {
  let quota: ChatUsageQuota | null = null
  let optimisticDelta = 0
  // Dedupe concurrent syncs (a reveal-refresh racing a cold-start send fetch).
  let inFlight: Promise<void> | null = null

  const applyQuota = (next: ChatUsageQuota): void => {
    quota = next
    optimisticDelta = 0
  }

  const sync = (): Promise<void> => {
    if (inFlight) return inFlight
    inFlight = fetchQuota()
      .then(applyQuota)
      .catch(() => {
        // Silent + fail-open: a quota probe must never surface an error or block
        // the user (same posture as maybeTriggerChatQuotaPopup in usageLimit.ts).
      })
      .finally(() => {
        inFlight = null
      })
    return inFlight
  }

  return {
    sync,
    applyQuota,
    isLimitReached: () => isLimitReached(quota, optimisticDelta),
    recordQuery: () => {
      optimisticDelta += 1
    },
    check: async () => {
      // Cold start only: force one sync so a user already over the cap can't get
      // a free send in before the first snapshot lands. Warm sends never hit the
      // network here.
      if (!quota) await sync()
      if (!isLimitReached(quota, optimisticDelta)) return { blocked: false }
      return { blocked: true, message: limitMessage(quota) }
    }
  }
}
