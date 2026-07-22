// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'

// Multi-window lost-update regression (found live during Phase 2 verification):
// windows share the localStorage key but each keeps an in-memory cache, and the
// cross-window `storage` event refresh is asynchronous. setPreferences must
// merge onto the LIVE stored value — writing the cached blob resurrects stale
// state and drops other windows' recent writes.
const KEY = 'omi-windows-prefs-v1'

describe('setPreferences lost-update safety', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('preserves a field another window wrote after this module cached prefs', async () => {
    localStorage.setItem(KEY, JSON.stringify({ language: 'en', onboardingStep: 5 }))
    // Import AFTER seeding so the module cache reflects the seeded state.
    const prefs = await import('./preferences')

    // Simulate another window's direct write (no storage event in jsdom's own
    // window — exactly the async-gap scenario).
    const external = JSON.parse(localStorage.getItem(KEY)!)
    external.onboardingCompletedAt = 12345
    localStorage.setItem(KEY, JSON.stringify(external))

    // This window writes an unrelated field from its (stale) cache.
    prefs.setPreferences({ displayName: 'Chris' })

    const stored = JSON.parse(localStorage.getItem(KEY)!)
    expect(stored.displayName).toBe('Chris')
    // The external write must survive — the old whole-blob write dropped it.
    expect(stored.onboardingCompletedAt).toBe(12345)
    expect(stored.onboardingStep).toBe(5)
  })

  it('still applies undefined-valued patch keys as deletions', async () => {
    localStorage.setItem(KEY, JSON.stringify({ language: 'en', onboardingStep: 3 }))
    const prefs = await import('./preferences')
    prefs.setPreferences({ onboardingStep: undefined })
    const stored = JSON.parse(localStorage.getItem(KEY)!)
    expect('onboardingStep' in stored).toBe(false)
  })
})
