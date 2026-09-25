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

/** A pending reservation blocks every other proactive lane, so a slot that is
 *  never committed nor cancelled — a throw between `reserve` and delivery —
 *  would silence ALL proactive notifications for the rest of the process. A
 *  reservation therefore expires: once it is this old it no longer blocks and is
 *  pruned. This bounds the damage of a leak; it does not excuse one, and callers
 *  must still cancel on every failure path. */
const PENDING_SLOT_TTL_MS = 10 * MINUTE

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

export type NotificationDeliverySlot = {
  token: string
  assistantId: string
  now: number
}

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
  private readonly pending = new Map<string, NotificationDeliverySlot>()

  /** Drop reservations older than the TTL. An abandoned slot must never become a
   *  permanent gag on every assistant. */
  private prunePending(now: number): void {
    for (const [token, slot] of this.pending) {
      if (now - slot.now >= PENDING_SLOT_TTL_MS) this.pending.delete(token)
    }
  }

  /** Expires stale reservations first; beyond that it does not mutate — neither
   *  clock moves here. */
  decide(input: ThrottleInput): ThrottleDecision {
    this.prunePending(input.now)
    if (input.snoozedUntil !== null && input.now < input.snoozedUntil)
      return { allowed: false, reason: 'snoozed' }
    if (!input.respectFrequency) return { allowed: true }
    if (!input.notificationsEnabled) return { allowed: false, reason: 'notifications_off' }

    const interval = minIntervalMs(input.frequencyLevel)
    // Even maximum frequency has one exclusive in-flight display slot. This is
    // a delivery invariant, not a frequency budget: the first candidate must
    // either commit a visible toast or cancel before another may proceed.
    if (this.pending.size > 0) return { allowed: false, reason: 'frequency' }
    if (interval === null) return { allowed: true } // Maximum — no time throttle
    if (interval === Infinity) return { allowed: false, reason: 'frequency' } // Off

    if (this.lastGlobalAt !== null && input.now - this.lastGlobalAt < interval)
      return { allowed: false, reason: 'frequency' }
    for (const slot of this.pending.values()) {
      if (input.now - slot.now < interval) return { allowed: false, reason: 'frequency' }
    }
    const last = this.lastByAssistant.get(input.assistantId)
    if (last !== undefined && input.now - last < interval)
      return { allowed: false, reason: 'frequency' }
    const assistantPending = [...this.pending.values()].find(
      (slot) => slot.assistantId === input.assistantId && input.now - slot.now < interval
    )
    if (assistantPending) return { allowed: false, reason: 'frequency' }
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

  /** Reserve a display slot without spending either clock. The reservation is
   * intentionally local and short-lived; callers must commit only after they
   * have a user-visible payload, or cancel it on every failure path. */
  reserve(input: ThrottleInput): NotificationDeliverySlot | ThrottleDecision {
    const decision = this.decide(input)
    if (!decision.allowed) return decision
    if (!input.respectFrequency)
      return {
        token: `${input.assistantId}:${input.now}:${Math.random()}`,
        assistantId: input.assistantId,
        now: input.now
      }
    const slot: NotificationDeliverySlot = {
      token: `${input.assistantId}:${input.now}:${Math.random()}`,
      assistantId: input.assistantId,
      now: input.now
    }
    this.pending.set(slot.token, slot)
    return slot
  }

  commit(slot: NotificationDeliverySlot): boolean {
    const current = this.pending.get(slot.token)
    if (!current) return false
    this.pending.delete(slot.token)
    this.record(slot.assistantId, slot.now)
    return true
  }

  cancel(slot: NotificationDeliverySlot): boolean {
    return this.pending.delete(slot.token)
  }
}

// --- Runtime singleton -------------------------------------------------------

const throttle = new NotificationThrottle()

// Snooze lives here (in memory, like Mac's FloatingControlBarManager.isSnoozed)
// rather than in AppSettings: it is a transient "not right now", not a
// preference, and it should not survive a restart.
let snoozedUntil: number | null = null

// When authoritative Windows JIT is active, the legacy insight/context-bucket
// lane must not spend a second, untracked ambient notification budget. The
// callback is host-owned and fail-open while JIT authority is unknown so the
// existing assistant remains the rollback lane when the flag is off.
let jitLegacyAmbientGate: (() => boolean) | null = null

export function setJitLegacyAmbientGate(gate: (() => boolean) | null): void {
  jitLegacyAmbientGate = gate
}

/** Silence every proactive notification until `untilMs`. Pass null to clear. */
export function setNotificationSnooze(untilMs: number | null): void {
  snoozedUntil = untilMs
}

export function isNotificationSnoozed(now: number = Date.now()): boolean {
  return snoozedUntil !== null && now < snoozedUntil
}

/** Would a proactive notification from `assistantId` be deliverable at all right
 *  now, ignoring ONLY the per-interval rate-limit clocks? True iff the user has
 *  not silenced us: not snoozed AND the master toggle is on AND the frequency
 *  level is not Off (0/junk). It deliberately does NOT consult the rate clocks —
 *  being inside a rate window is "not yet", not "silenced".
 *
 *  This exists for a glow-less assistant (Insight): with no visible output other
 *  than a toast, running its ~12-call Gemini pipeline while notifications are
 *  silenced is pure wasted spend, so Insight gates its `isEnabled()` on this.
 *  Reuses the SAME snooze/master/frequency reads as `notifyProactive` so the two
 *  can never disagree about whether a toast could appear. `assistantId` is
 *  accepted for symmetry with `notifyProactive` and a future per-assistant master;
 *  today the gate is global. */
export function notificationsActive(assistantId: string, now: number = Date.now()): boolean {
  // JIT admission consumes the visit for the Insight pipeline, not only the
  // toast. When the rollout is effective, Insight.isEnabled() must go false so
  // Gemini is not purchased behind a suppressed notification.
  if (assistantId === 'insight' && jitLegacyAmbientGate?.()) return false
  const settings = getAppSettings()
  if (isNotificationSnoozed(now)) return false
  if (!settings.notificationsEnabled) return false
  return minIntervalMs(settings.notificationFrequency) !== Infinity
}

/** Deliver an assistant's notification through the throttle and the app's one
 *  existing toast path. Returns whether it was shown. */
export function notifyProactive(
  assistantId: string,
  payload: InsightPayload,
  opts: { respectFrequency?: boolean; now?: number } = {}
): boolean {
  if (assistantId === 'insight' && jitLegacyAmbientGate?.()) {
    console.log('[assistants] legacy insight suppressed while JIT authority is active')
    return false
  }
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

/** Acquire the real local toast budget before any JIT server reservation or
 * model call. A null result means snoozed, disabled, frequency-suppressed, or
 * already reserved by a concurrent proactive lane. */
export function reserveProactiveDeliverySlot(
  assistantId: string,
  now: number = Date.now()
): NotificationDeliverySlot | null {
  const settings = getAppSettings()
  const decision = throttle.reserve({
    assistantId,
    now,
    frequencyLevel: settings.notificationFrequency,
    notificationsEnabled: settings.notificationsEnabled,
    snoozedUntil,
    respectFrequency: true
  })
  return 'token' in decision ? decision : null
}

/** Commit the previously acquired local slot and send through the existing
 * insight surface. No caller should emit a JIT delivery receipt unless this
 * returns true. */
export function commitProactiveDeliverySlot(
  slot: NotificationDeliverySlot,
  payload: InsightPayload
): boolean {
  if (!throttle.commit(slot)) return false
  deliverInsight(payload)
  return true
}

export function cancelProactiveDeliverySlot(slot: NotificationDeliverySlot): void {
  throttle.cancel(slot)
}
