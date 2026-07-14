// The shared notification throttle for proactive assistants. Port of macOS
// `NotificationService`'s frequency model — Windows had no equivalent, only
// ad-hoc per-feature gating.
//
// Why two clocks: what the user experiences is the SUM of every assistant's
// notifications, so the budget is GLOBAL — the first assistant to speak spends
// it for everyone. The per-assistant clock is a second, redundant guard carried
// over from Mac: since `record()` stamps both clocks with the same instant, the
// per-assistant check can never fail once the global one passes. Keep it for
// parity (and so a future per-assistant rate could slot in), but do NOT read it
// as per-assistant fairness — there is none, and claiming otherwise would be a
// lie about the code.
//
// Suppression order (first match wins): snooze → master toggle → frequency.
// Snooze is never bypassable — the user asked for silence, and a "functional"
// notification is not an exception to that. The master toggle and the frequency
// gate ARE bypassable via `respectFrequency: false`, which exists for functional,
// non-proactive notifications (permission repair, support replies) that are
// answers to something the user did, not interruptions we chose to make.
//
// The decision logic is pure and clock-injected; only `notifyProactive` below
// touches real state and real delivery.
import { getAppSettings } from '../../appSettings'
import { deliverInsight } from '../../ipc/insight'
import type { InsightPayload } from '../../../shared/types'

const MINUTE = 60_000

/** Level → minimum interval between notifications.
 *  `Infinity` = off (never), `null` = no throttle at all. */
const LEVEL_INTERVALS_MS: readonly (number | null)[] = [
  Infinity, //  0 — Off (default)
  60 * MINUTE, //  1 — Minimal
  30 * MINUTE, //  2 — Low
  10 * MINUTE, //  3 — Balanced
  3 * MINUTE, //  4 — High
  null //  5 — Maximum
]

/** Minimum gap for a frequency level. Out-of-range levels read as Off rather
 *  than as "no throttle" — a bad value must never make us louder. */
export function minIntervalMs(level: number): number | null {
  if (!Number.isInteger(level) || level < 0 || level >= LEVEL_INTERVALS_MS.length) return Infinity
  return LEVEL_INTERVALS_MS[level]
}

export type SuppressionReason = 'snoozed' | 'notifications_off' | 'frequency'
export type ThrottleDecision = { allowed: true } | { allowed: false; reason: SuppressionReason }

export type ThrottleInput = {
  assistantId: string
  now: number
  /** 0–5; see LEVEL_INTERVALS_MS. */
  frequencyLevel: number
  /** The master toggle (`AppSettings.notificationsEnabled`). */
  notificationsEnabled: boolean
  /** Epoch ms the snooze expires, or null when not snoozed. */
  snoozedUntil: number | null
  /** false = functional notification: skips the master + frequency gates (never snooze). */
  respectFrequency: boolean
}

/** The two clocks. Mutated only by `record`. */
export class NotificationThrottle {
  private lastGlobalAt: number | null = null
  private readonly lastByAssistant = new Map<string, number>()

  /** Pure: does not mutate. */
  decide(input: ThrottleInput): ThrottleDecision {
    if (input.snoozedUntil !== null && input.now < input.snoozedUntil)
      return { allowed: false, reason: 'snoozed' }
    if (!input.respectFrequency) return { allowed: true }
    if (!input.notificationsEnabled) return { allowed: false, reason: 'notifications_off' }

    const interval = minIntervalMs(input.frequencyLevel)
    if (interval === null) return { allowed: true } // Maximum — no throttle
    if (interval === Infinity) return { allowed: false, reason: 'frequency' } // Off

    if (this.lastGlobalAt !== null && input.now - this.lastGlobalAt < interval)
      return { allowed: false, reason: 'frequency' }
    const last = this.lastByAssistant.get(input.assistantId)
    if (last !== undefined && input.now - last < interval)
      return { allowed: false, reason: 'frequency' }
    return { allowed: true }
  }

  /** Spend the budget: both clocks advance together (which is exactly why the
   *  per-assistant clock is redundant — see the header). */
  record(assistantId: string, now: number): void {
    this.lastGlobalAt = now
    this.lastByAssistant.set(assistantId, now)
  }

  /** Decide, and on an allow spend the budget. A bypassing (functional)
   *  notification does NOT spend it — it was never a proactive interruption. */
  tryAllow(input: ThrottleInput): ThrottleDecision {
    const decision = this.decide(input)
    if (decision.allowed && input.respectFrequency) this.record(input.assistantId, input.now)
    return decision
  }
}

// --- Runtime singleton -------------------------------------------------------

const throttle = new NotificationThrottle()

// Snooze lives here (in memory, like Mac's FloatingControlBarManager.isSnoozed)
// rather than in AppSettings: it is a transient "not right now", not a
// preference, and it should not survive a restart.
let snoozedUntil: number | null = null

/** Silence every proactive notification until `untilMs`. Pass null to clear. */
export function setNotificationSnooze(untilMs: number | null): void {
  snoozedUntil = untilMs
}

export function isNotificationSnoozed(now: number = Date.now()): boolean {
  return snoozedUntil !== null && now < snoozedUntil
}

/** Deliver an assistant's notification through the throttle and the app's one
 *  existing toast path. Returns whether it was shown. */
export function notifyProactive(
  assistantId: string,
  payload: InsightPayload,
  opts: { respectFrequency?: boolean; now?: number } = {}
): boolean {
  const settings = getAppSettings()
  const now = opts.now ?? Date.now()
  const decision = throttle.tryAllow({
    assistantId,
    now,
    frequencyLevel: settings.notificationFrequency,
    notificationsEnabled: settings.notificationsEnabled,
    snoozedUntil,
    respectFrequency: opts.respectFrequency !== false
  })
  if (!decision.allowed) {
    console.log(`[assistants] notification from ${assistantId} suppressed: ${decision.reason}`)
    return false
  }
  deliverInsight(payload)
  return true
}
