// Cortex licensing — open core with a Pro tier.
//
// Cortex is open source and fully usable for free. A Pro tier unlocks
// convenience/power features (cloud sync, higher automation limits, priority
// model routing). Users can start a one-time time-limited trial of Pro.
//
// This module is pure (no storage, no I/O) so the tier math is unit-testable.
// Persistence + subscriptions live in renderer `lib/license.ts`.

export type Tier = 'free' | 'trial' | 'pro'

export type LicenseState = {
  /** A redeemed Pro license key, if any. */
  proKey?: string
  /** Epoch ms when the user started their Pro trial. */
  trialStartedAt?: number
}

export const TRIAL_DURATION_MS = 14 * 24 * 60 * 60 * 1000 // 14 days

/** Pro-gated feature flags. Free tier gets everything else. */
export type ProFeature =
  | 'cloud-sync' // sync conversations/memories across devices
  | 'unlimited-automation' // remove the daily PC-control action cap
  | 'priority-models' // pinned/priority cloud model routing
  | 'team' // shared workspaces (future)

export const PRO_FEATURES: { id: ProFeature; label: string; description: string }[] = [
  {
    id: 'cloud-sync',
    label: 'Cloud sync',
    description: 'Encrypted sync of your conversations, memories and settings across devices.'
  },
  {
    id: 'unlimited-automation',
    label: 'Unlimited PC control',
    description: 'Remove the daily cap on agent actions that control your computer.'
  },
  {
    id: 'priority-models',
    label: 'Priority models',
    description: 'Pin premium cloud models and get priority routing.'
  },
  {
    id: 'team',
    label: 'Team workspaces',
    description: 'Shared memories and goals for your team (coming soon).'
  }
]

/** Free-tier daily limit on agent PC-control actions. Pro/trial = unlimited. */
export const FREE_AUTOMATION_DAILY_LIMIT = 25

const PRO_KEY_RE = /^CORTEX-PRO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/

/** Stub validation of a Pro key format. Real verification happens server-side. */
export function isValidProKey(key: string | undefined | null): boolean {
  return !!key && PRO_KEY_RE.test(key.trim().toUpperCase())
}

export function trialEndsAt(state: LicenseState): number | undefined {
  return typeof state.trialStartedAt === 'number'
    ? state.trialStartedAt + TRIAL_DURATION_MS
    : undefined
}

export function isTrialActive(state: LicenseState, now: number = Date.now()): boolean {
  const ends = trialEndsAt(state)
  return typeof ends === 'number' && now < ends
}

export function trialDaysRemaining(state: LicenseState, now: number = Date.now()): number {
  const ends = trialEndsAt(state)
  if (typeof ends !== 'number') return 0
  return Math.max(0, Math.ceil((ends - now) / (24 * 60 * 60 * 1000)))
}

/** Resolve the effective tier. A valid Pro key always wins over a trial. */
export function computeTier(state: LicenseState, now: number = Date.now()): Tier {
  if (isValidProKey(state.proKey)) return 'pro'
  if (isTrialActive(state, now)) return 'trial'
  return 'free'
}

export function isProActive(state: LicenseState, now: number = Date.now()): boolean {
  const tier = computeTier(state, now)
  return tier === 'pro' || tier === 'trial'
}

export function hasFeature(
  state: LicenseState,
  _feature: ProFeature,
  now: number = Date.now()
): boolean {
  // All Pro features are unlocked together for Pro/trial in this open-core model.
  return isProActive(state, now)
}

/** Whether the user is eligible to *start* a trial (one-time). */
export function canStartTrial(state: LicenseState): boolean {
  return typeof state.trialStartedAt !== 'number' && !isValidProKey(state.proKey)
}
