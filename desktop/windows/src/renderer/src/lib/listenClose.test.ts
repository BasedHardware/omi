import { describe, it, expect } from 'vitest'
import {
  TRIAL_EXPIRED_MESSAGE,
  ACCOUNT_REJECTED_MESSAGE,
  isTrialExpiredClose,
  isAccountRejectedClose,
  isCompleteMessage,
  closeMessage,
  isQuotaExhaustedEvent
} from './listenClose'

describe('isTrialExpiredClose', () => {
  it('detects the 1008 trial_expired close', () => {
    expect(isTrialExpiredClose(1008, 'trial_expired')).toBe(true)
    expect(isTrialExpiredClose(1008, 'Trial_Expired')).toBe(true)
  })

  it('ignores other 1008 reasons and other codes', () => {
    expect(isTrialExpiredClose(1008, 'Bad uid')).toBe(false)
    expect(isTrialExpiredClose(1008, 'Bad user')).toBe(false)
    expect(isTrialExpiredClose(1008, '')).toBe(false)
    expect(isTrialExpiredClose(1000, 'trial_expired')).toBe(false)
    expect(isTrialExpiredClose(1006, '')).toBe(false)
  })

  it('tolerates a missing reason', () => {
    expect(isTrialExpiredClose(1008, undefined as unknown as string)).toBe(false)
  })
})

describe('isAccountRejectedClose', () => {
  it('detects the 1008 Bad uid / Bad user closes', () => {
    expect(isAccountRejectedClose(1008, 'Bad uid')).toBe(true)
    expect(isAccountRejectedClose(1008, 'Bad user')).toBe(true)
    expect(isAccountRejectedClose(1008, '  bad USER ')).toBe(true)
  })

  it('ignores other reasons and codes', () => {
    expect(isAccountRejectedClose(1008, 'trial_expired')).toBe(false)
    expect(isAccountRejectedClose(1008, 'Bad something')).toBe(false)
    expect(isAccountRejectedClose(1000, 'Bad user')).toBe(false)
  })
})

describe('closeMessage', () => {
  it('returns the clear trial message for a trial_expired close', () => {
    expect(closeMessage(1008, 'trial_expired')).toBe(TRIAL_EXPIRED_MESSAGE)
  })

  it('returns the account message for Bad uid / Bad user closes', () => {
    expect(closeMessage(1008, 'Bad uid')).toBe(ACCOUNT_REJECTED_MESSAGE)
    expect(closeMessage(1008, 'Bad user')).toBe(ACCOUNT_REJECTED_MESSAGE)
  })

  it('surfaces the code AND backend reason for other closes (diagnosable)', () => {
    expect(closeMessage(1011, 'internal')).toBe('Omi /v4/listen closed (1011): internal')
    expect(closeMessage(1008, 'something new')).toBe('Omi /v4/listen closed (1008): something new')
  })

  it('omits an empty reason cleanly', () => {
    expect(closeMessage(1006, '')).toBe('Omi /v4/listen closed (1006)')
    expect(closeMessage(1005, '   ')).toBe('Omi /v4/listen closed (1005)')
  })
})

describe('isCompleteMessage', () => {
  it('recognizes the ready-to-show messages', () => {
    expect(isCompleteMessage(TRIAL_EXPIRED_MESSAGE)).toBe(true)
    expect(isCompleteMessage(ACCOUNT_REJECTED_MESSAGE)).toBe(true)
  })

  it('does not match diagnostic strings', () => {
    expect(isCompleteMessage('Omi /v4/listen closed (1011): internal')).toBe(false)
    expect(isCompleteMessage('anything else')).toBe(false)
  })
})

describe('isQuotaExhaustedEvent', () => {
  it('treats a depleted freemium event as exhausted', () => {
    expect(
      isQuotaExhaustedEvent({ type: 'freemium_threshold_reached', raw: { remaining_seconds: 0 } })
    ).toBe(true)
  })

  it('treats a missing remaining field as exhausted (fail safe)', () => {
    expect(isQuotaExhaustedEvent({ type: 'freemium_threshold_reached', raw: {} })).toBe(true)
  })

  it('does NOT treat an early-warning (remaining > 0) event as exhausted', () => {
    expect(
      isQuotaExhaustedEvent({ type: 'freemium_threshold_reached', raw: { remaining_seconds: 120 } })
    ).toBe(false)
  })

  it('ignores unrelated events', () => {
    expect(isQuotaExhaustedEvent({ type: 'memory_creating', raw: {} })).toBe(false)
  })
})

describe('trial signals converge (no clobber)', () => {
  // The freemium event and the 1008 close must yield the SAME message so the
  // "latest wins" error sink can't replace the friendly message with a generic one.
  it('event path and close path produce identical text', () => {
    const fromEvent = TRIAL_EXPIRED_MESSAGE
    const fromClose = closeMessage(1008, 'trial_expired')
    expect(fromClose).toBe(fromEvent)
  })
})
