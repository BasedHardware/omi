import { describe, it, expect } from 'vitest'
import {
  computeTier,
  isProActive,
  isTrialActive,
  trialDaysRemaining,
  canStartTrial,
  isValidProKey,
  hasFeature,
  TRIAL_DURATION_MS
} from './license'

const DAY = 24 * 60 * 60 * 1000
const NOW = 1_700_000_000_000

describe('license / open-core tiers', () => {
  it('defaults to the free tier', () => {
    expect(computeTier({}, NOW)).toBe('free')
    expect(isProActive({}, NOW)).toBe(false)
  })

  it('validates Pro key format', () => {
    expect(isValidProKey('CORTEX-PRO-AB12-CD34-EF56')).toBe(true)
    expect(isValidProKey('cortex-pro-ab12-cd34-ef56')).toBe(true) // case-insensitive
    expect(isValidProKey('CORTEX-PRO-XYZ')).toBe(false)
    expect(isValidProKey(undefined)).toBe(false)
  })

  it('a valid Pro key yields the pro tier and unlocks features', () => {
    const state = { proKey: 'CORTEX-PRO-AB12-CD34-EF56' }
    expect(computeTier(state, NOW)).toBe('pro')
    expect(hasFeature(state, 'cloud-sync', NOW)).toBe(true)
  })

  it('an active trial yields the trial tier', () => {
    const state = { trialStartedAt: NOW - 2 * DAY }
    expect(computeTier(state, NOW)).toBe('trial')
    expect(isTrialActive(state, NOW)).toBe(true)
    expect(trialDaysRemaining(state, NOW)).toBe(12)
  })

  it('an expired trial falls back to free', () => {
    const state = { trialStartedAt: NOW - (TRIAL_DURATION_MS + DAY) }
    expect(computeTier(state, NOW)).toBe('free')
    expect(isTrialActive(state, NOW)).toBe(false)
    expect(trialDaysRemaining(state, NOW)).toBe(0)
  })

  it('a Pro key overrides an expired trial', () => {
    const state = { proKey: 'CORTEX-PRO-AB12-CD34-EF56', trialStartedAt: NOW - 999 * DAY }
    expect(computeTier(state, NOW)).toBe('pro')
  })

  it('trial can only be started once', () => {
    expect(canStartTrial({})).toBe(true)
    expect(canStartTrial({ trialStartedAt: NOW })).toBe(false)
    expect(canStartTrial({ proKey: 'CORTEX-PRO-AB12-CD34-EF56' })).toBe(false)
  })
})
