// The two decisions that must be exactly right: the skip gate (every branch, in
// order) and the transition state machine (especially: cold-start focused is
// silent).
import { describe, expect, it } from 'vitest'
import { decideTransition, errorBackoffMs, shouldSkipAnalysis, type SkipInput } from './gating'
import type { ScreenAnalysis } from './models'

function skipInput(over: Partial<SkipInput> = {}): SkipInput {
  return {
    now: 1_000_000,
    app: 'Chrome',
    windowTitle: 'Docs — work',
    lastAnalyzedApp: 'Chrome',
    lastAnalyzedWindowTitle: 'Docs — work',
    lastStatus: 'focused',
    cooldownEndsAt: null,
    backoffEndsAt: null,
    ...over
  }
}

const analysis = (over: Partial<ScreenAnalysis> = {}): ScreenAnalysis => ({
  status: 'distracted',
  appOrSite: 'YouTube',
  description: 'watching a video',
  message: 'Back to work?',
  ...over
})

describe('errorBackoffMs', () => {
  it('is 5s, 10s, 20s, 40s… capped at 5 minutes', () => {
    expect(errorBackoffMs(1)).toBe(5_000)
    expect(errorBackoffMs(2)).toBe(10_000)
    expect(errorBackoffMs(3)).toBe(20_000)
    expect(errorBackoffMs(4)).toBe(40_000)
    expect(errorBackoffMs(10)).toBe(300_000) // capped
    expect(errorBackoffMs(0)).toBe(5_000) // clamped up to at-least-one
  })
})

describe('shouldSkipAnalysis order', () => {
  it('error backoff wins even when there is no verdict yet (cold start)', () => {
    // The ordering that matters most: backoff is checked BEFORE the cold-start
    // guard, so an API outage does not retry every frame forever.
    const d = shouldSkipAnalysis(
      skipInput({ lastStatus: null, backoffEndsAt: 1_000_500, now: 1_000_000 })
    )
    expect(d).toEqual({ skip: true, reason: 'error_backoff' })
  })

  it('analyzes once the backoff has lapsed', () => {
    const d = shouldSkipAnalysis(
      skipInput({ lastStatus: null, backoffEndsAt: 999_000, now: 1_000_000 })
    )
    expect(d.skip).toBe(false)
  })

  it('cold start (no verdict) analyzes', () => {
    const d = shouldSkipAnalysis(skipInput({ lastStatus: null }))
    expect(d).toEqual({ skip: false, reason: 'cold_start' })
  })

  it('a context change ALWAYS analyzes, bypassing an active cooldown', () => {
    const d = shouldSkipAnalysis(
      skipInput({
        app: 'Chrome',
        windowTitle: 'YouTube', // different title → context changed
        lastStatus: 'distracted',
        cooldownEndsAt: 2_000_000 // cooldown far in the future
      })
    )
    expect(d).toEqual({ skip: false, reason: 'context_changed' })
  })

  it('a different app is a context change too', () => {
    const d = shouldSkipAnalysis(
      skipInput({ app: 'Slack', lastAnalyzedApp: 'Chrome', lastStatus: 'distracted' })
    )
    expect(d).toEqual({ skip: false, reason: 'context_changed' })
  })

  it('a cosmetic title change (a ticking timer) is NOT a context change', () => {
    // normalizeWindowTitle strips the "12:34" so same-context holds → cooldown or
    // focused-skip applies. Here focused + same context → skip.
    const d = shouldSkipAnalysis(
      skipInput({
        windowTitle: 'Meet — 12:34',
        lastAnalyzedWindowTitle: 'Meet — 00:05',
        lastStatus: 'focused'
      })
    )
    expect(d).toEqual({ skip: true, reason: 'focused_same_context' })
  })

  it('cooldown skips when the context has not changed', () => {
    const d = shouldSkipAnalysis(
      skipInput({ lastStatus: 'distracted', cooldownEndsAt: 2_000_000, now: 1_000_000 })
    )
    expect(d).toEqual({ skip: true, reason: 'cooldown' })
  })

  it('focused + same context skips (the steady state)', () => {
    const d = shouldSkipAnalysis(skipInput({ lastStatus: 'focused' }))
    expect(d).toEqual({ skip: true, reason: 'focused_same_context' })
  })

  it('distracted + same context + lapsed cooldown analyzes', () => {
    const d = shouldSkipAnalysis(
      skipInput({ lastStatus: 'distracted', cooldownEndsAt: 999_000, now: 1_000_000 })
    )
    expect(d).toEqual({ skip: false, reason: 'not_focused' })
  })
})

describe('decideTransition', () => {
  it('cold-start focused persists but is SILENT — no glow, no notification', () => {
    const a = decideTransition(null, analysis({ status: 'focused', message: 'Nice work' }))
    expect(a.persist).toBe(true)
    expect(a.glow).toBeNull()
    expect(a.notifyBody).toBeNull()
    expect(a.startCooldown).toBe(false)
    expect(a.notifiedState).toBe('focused')
  })

  it('→ distracted: red glow, cooldown, app-prefixed notification', () => {
    const a = decideTransition('focused', analysis({ message: 'Focus up' }))
    expect(a.persist).toBe(true)
    expect(a.glow).toBe('distracted')
    expect(a.notifyBody).toBe('YouTube - Focus up')
    expect(a.startCooldown).toBe(true)
    expect(a.notifiedState).toBe('distracted')
  })

  it('→ distracted with no coaching message: still glows, but says nothing', () => {
    const a = decideTransition('focused', analysis({ message: null }))
    expect(a.glow).toBe('distracted')
    expect(a.notifyBody).toBeNull()
    expect(a.startCooldown).toBe(true)
  })

  it('distracted while already distracted: nothing (dedup across parallel frames)', () => {
    const a = decideTransition('distracted', analysis())
    expect(a).toEqual({
      persist: false,
      glow: null,
      notifyBody: null,
      startCooldown: false,
      notifiedState: 'distracted'
    })
  })

  it('→ focused FROM distracted: green glow, message-only notification', () => {
    const a = decideTransition(
      'distracted',
      analysis({ status: 'focused', appOrSite: 'VS Code', message: 'Back on track' })
    )
    expect(a.persist).toBe(true)
    expect(a.glow).toBe('focused')
    expect(a.notifyBody).toBe('Back on track') // no app prefix on the refocus
    expect(a.startCooldown).toBe(false)
    expect(a.notifiedState).toBe('focused')
  })

  it('focused while already focused: nothing', () => {
    const a = decideTransition('focused', analysis({ status: 'focused' }))
    expect(a.persist).toBe(false)
    expect(a.glow).toBeNull()
    expect(a.notifyBody).toBeNull()
  })
})
