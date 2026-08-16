/**
 * Pure delivery-budget policy — port of macOS ContextDeliveryAuthority's gate
 * and budget math (CDA:31-157). No IO: the ledger runs these inside its
 * reservation transaction and the engine re-runs the free gate at every stage.
 *
 * Windows deviations, deliberate: there is no desktop paywall state in the
 * main process (paywalled is always false until one exists) and no plan
 * multiplier source (multiplier 1); both are parameters so the contract holds
 * when those signals arrive.
 */

export interface DeliveryGateInput {
  masterEnabled: boolean
  frequencyLevel: number
  paywalled: boolean
  cooldownMs: number
  dailyLimit: number
  lastGlobalPresentationAt: number | null
}

export type DeliveryGateReason =
  | 'allowed'
  | 'masterDisabled'
  | 'frequencyDisabled'
  | 'snoozed'
  | 'paywalled'
  | 'cooldown'
  | 'dailyBudget'
  | 'duplicate'

export const ADVANCEABLE_DELIVERY_STATES = [
  'attempted',
  'model_completed',
  'policy_approved'
] as const
export const DAILY_WINDOW_MS = 24 * 60 * 60 * 1000
export const DELIVERY_ROW_EXPIRY_MS = 30 * 24 * 60 * 60 * 1000
export const ABANDONED_DELIVERY_TIMEOUT_MS = 15 * 60 * 1000
export const RECENT_DELIVERY_PROMPT_CAP = 15
export const RECENT_DELIVERY_SUMMARY_CHAR_LIMIT = 320
export const RECENT_DELIVERY_MEMORY_LOOKBACK_MS = 6 * 60 * 60 * 1000

const DAILY_LIMIT_BASE = [0, 10, 20, 40, 60, 100]

/** In order: master toggle, frequency Off, paywall. `.snoozed` exists in the
 *  reason vocabulary but no code path produces it (mac parity: bar snooze
 *  never gates the director). */
export function freeGate(input: DeliveryGateInput): DeliveryGateReason {
  if (!input.masterEnabled) return 'masterDisabled'
  if (input.frequencyLevel === 0) return 'frequencyDisabled'
  if (input.paywalled) return 'paywalled'
  return 'allowed'
}

export function cooldownMsForLevel(level: number): number {
  switch (level) {
    case 1:
      return 3600 * 1000
    case 2:
      return 1800 * 1000
    case 3:
      return 600 * 1000
    case 4:
      return 180 * 1000
    default:
      return 0
  }
}

export function dailyLimitForLevel(level: number, planMultiplier = 1): number {
  const clamped = Math.min(5, Math.max(0, Math.trunc(level)))
  return DAILY_LIMIT_BASE[clamped] * Math.max(1, planMultiplier)
}
