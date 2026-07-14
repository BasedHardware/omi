// Throttle contract: the frequency table, the two clocks sharing one budget, and
// the suppression order (snooze is the one gate nothing may bypass).
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  getAppSettings: vi.fn(() => ({ notificationsEnabled: true, notificationFrequency: 3 })),
  deliverInsight: vi.fn()
}))
vi.mock('../../appSettings', () => ({ getAppSettings: h.getAppSettings }))
vi.mock('../../ipc/insight', () => ({ deliverInsight: h.deliverInsight }))

import {
  NotificationThrottle,
  isNotificationSnoozed,
  minIntervalMs,
  notifyProactive,
  setNotificationSnooze,
  type ThrottleInput
} from './notify'
import type { InsightPayload } from '../../../shared/types'

const MIN = 60_000
const T0 = 1_700_000_000_000

const input = (over: Partial<ThrottleInput> = {}): ThrottleInput => ({
  assistantId: 'focus',
  now: T0,
  frequencyLevel: 3, // Balanced — 10 min
  notificationsEnabled: true,
  snoozedUntil: null,
  respectFrequency: true,
  ...over
})

const payload: InsightPayload = {
  headline: 'Back to it',
  advice: 'You drifted off the doc.',
  reasoning: 'Screen shows social media.',
  category: 'other',
  sourceApp: 'Chrome',
  confidence: 0.9
}

describe('minIntervalMs (frequency table)', () => {
  it('maps the six levels exactly as Mac does', () => {
    expect(minIntervalMs(0)).toBe(Infinity) // Off
    expect(minIntervalMs(1)).toBe(60 * MIN)
    expect(minIntervalMs(2)).toBe(30 * MIN)
    expect(minIntervalMs(3)).toBe(10 * MIN)
    expect(minIntervalMs(4)).toBe(3 * MIN)
    expect(minIntervalMs(5)).toBeNull() // Maximum — no throttle
  })

  it('reads a junk level as Off, never as no-throttle', () => {
    expect(minIntervalMs(-1)).toBe(Infinity)
    expect(minIntervalMs(6)).toBe(Infinity)
    expect(minIntervalMs(2.5)).toBe(Infinity)
  })
})

describe('NotificationThrottle.tryAllow', () => {
  it('level 0 (Off, the default) suppresses everything proactive', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ frequencyLevel: 0 }))).toEqual({
      allowed: false,
      reason: 'frequency'
    })
  })

  it('level 5 (Maximum) never throttles', () => {
    const t = new NotificationThrottle()
    for (let i = 0; i < 5; i++)
      expect(t.tryAllow(input({ frequencyLevel: 5, now: T0 + i })).allowed).toBe(true)
  })

  it('holds an assistant off until its interval has elapsed', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input()).allowed).toBe(true)
    expect(t.tryAllow(input({ now: T0 + 9 * MIN }))).toEqual({
      allowed: false,
      reason: 'frequency'
    })
    expect(t.tryAllow(input({ now: T0 + 10 * MIN })).allowed).toBe(true)
  })

  it('spends ONE shared budget: a chatty assistant cannot starve another', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ assistantId: 'focus' })).allowed).toBe(true)
    // The global clock is what gates 'task' here — its own clock is still clean.
    expect(t.tryAllow(input({ assistantId: 'task', now: T0 + 1 * MIN }))).toEqual({
      allowed: false,
      reason: 'frequency'
    })
    expect(t.tryAllow(input({ assistantId: 'task', now: T0 + 10 * MIN })).allowed).toBe(true)
    // ...and 'task' spending the budget now gates 'focus' in turn.
    expect(t.tryAllow(input({ assistantId: 'focus', now: T0 + 11 * MIN }))).toEqual({
      allowed: false,
      reason: 'frequency'
    })
  })

  it('per-assistant clock gates even when the global one has elapsed', () => {
    // Level 1 (60m). 'focus' sends at T0; another assistant sends at T0+60m,
    // which moves the global clock but must not entitle 'focus' to a second send
    // before ITS own 60m are up.
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ frequencyLevel: 1, assistantId: 'focus' })).allowed).toBe(true)
    expect(
      t.tryAllow(input({ frequencyLevel: 1, assistantId: 'task', now: T0 + 60 * MIN })).allowed
    ).toBe(true)
    expect(
      t.tryAllow(input({ frequencyLevel: 1, assistantId: 'focus', now: T0 + 61 * MIN }))
    ).toEqual({ allowed: false, reason: 'frequency' })
  })

  it('a suppressed attempt does not move either clock', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input()).allowed).toBe(true)
    t.tryAllow(input({ now: T0 + 5 * MIN })) // suppressed
    // If the suppressed attempt had stamped the clock, this would be blocked.
    expect(t.tryAllow(input({ now: T0 + 10 * MIN })).allowed).toBe(true)
  })
})

describe('suppression order: snooze → master → frequency', () => {
  it('snooze wins over everything, including a functional bypass', () => {
    const t = new NotificationThrottle()
    expect(
      t.tryAllow(
        input({ snoozedUntil: T0 + MIN, respectFrequency: false, notificationsEnabled: false })
      )
    ).toEqual({ allowed: false, reason: 'snoozed' })
  })

  it('an expired snooze stops suppressing', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ snoozedUntil: T0, now: T0 })).allowed).toBe(true)
  })

  it('the master toggle suppresses a proactive notification', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ notificationsEnabled: false }))).toEqual({
      allowed: false,
      reason: 'notifications_off'
    })
  })

  it('respectFrequency:false bypasses the master + frequency gates', () => {
    const t = new NotificationThrottle()
    expect(
      t.tryAllow(input({ notificationsEnabled: false, frequencyLevel: 0, respectFrequency: false }))
        .allowed
    ).toBe(true)
  })

  it('a functional (bypassing) notification does not spend the proactive budget', () => {
    const t = new NotificationThrottle()
    expect(t.tryAllow(input({ respectFrequency: false })).allowed).toBe(true)
    expect(t.tryAllow(input({ now: T0 + 1 })).allowed).toBe(true) // still entitled
  })
})

describe('notifyProactive (delivery)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setNotificationSnooze(null)
    h.getAppSettings.mockReturnValue({ notificationsEnabled: true, notificationFrequency: 5 })
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  it('delivers through the existing toast path when allowed', () => {
    expect(notifyProactive('focus', payload, { now: T0 })).toBe(true)
    expect(h.deliverInsight).toHaveBeenCalledWith(payload)
  })

  it('does not deliver while snoozed', () => {
    setNotificationSnooze(T0 + 10 * MIN)
    expect(isNotificationSnoozed(T0)).toBe(true)
    expect(notifyProactive('focus', payload, { now: T0 })).toBe(false)
    expect(h.deliverInsight).not.toHaveBeenCalled()
  })

  it('does not deliver at the default Off frequency', () => {
    h.getAppSettings.mockReturnValue({ notificationsEnabled: true, notificationFrequency: 0 })
    expect(notifyProactive('focus', payload, { now: T0 })).toBe(false)
    expect(h.deliverInsight).not.toHaveBeenCalled()
  })
})
