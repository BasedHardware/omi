// Renderer-side license state: persisted in localStorage, with the pure tier
// math living in shared/license.ts. Mirrors the preferences.ts subscribe pattern
// so settings UI can react live.
import {
  type LicenseState,
  type Tier,
  type ProFeature,
  computeTier,
  isProActive,
  hasFeature,
  trialDaysRemaining,
  canStartTrial,
  isValidProKey
} from '../../../shared/license'

const KEY = 'cortex-license-v1'

function load(): LicenseState {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as LicenseState) : {}
  } catch {
    return {}
  }
}

let current: LicenseState = load()
const listeners = new Set<(s: LicenseState) => void>()

function persist(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}

export function getLicense(): LicenseState {
  return current
}

export function getTier(): Tier {
  return computeTier(current)
}

export function proActive(): boolean {
  return isProActive(current)
}

export function featureEnabled(feature: ProFeature): boolean {
  return hasFeature(current, feature)
}

export function daysLeftInTrial(): number {
  return trialDaysRemaining(current)
}

export function canTrial(): boolean {
  return canStartTrial(current)
}

/** Begin the one-time Pro trial. No-op if already trialing or Pro. */
export function startTrial(): boolean {
  if (!canStartTrial(current)) return false
  current = { ...current, trialStartedAt: Date.now() }
  persist()
  return true
}

/** Redeem a Pro key. Returns false (and persists nothing) if the format is invalid. */
export function redeemProKey(key: string): boolean {
  if (!isValidProKey(key)) return false
  current = { ...current, proKey: key.trim().toUpperCase() }
  persist()
  return true
}

export function clearLicense(): void {
  current = {}
  persist()
}

export function onLicenseChange(cb: (s: LicenseState) => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}
