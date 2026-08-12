import { beforeEach, describe, expect, it, vi } from 'vitest'

const trackOnboardingStepCompleted = vi.hoisted(() => vi.fn())
vi.mock('./analytics', () => ({ trackOnboardingStepCompleted }))

import { createOnboardingStepRecorder } from './onboardingStepTelemetry'

beforeEach(() => vi.clearAllMocks())

describe('createOnboardingStepRecorder', () => {
  it('records the accepted outcome once and rejects a racing duplicate', () => {
    const record = createOnboardingStepRecorder()

    record.beginStep(7)
    expect(record.record(7, 'Microphone', true)).toBe(true)
    expect(record.record(7, 'Microphone', false)).toBe(false)

    expect(trackOnboardingStepCompleted).toHaveBeenCalledExactlyOnceWith(7, 'Microphone', true)
  })

  it('permits a new terminal outcome after navigating away and back', () => {
    const record = createOnboardingStepRecorder()

    record.beginStep(1)
    expect(record.record(1, 'Language', false)).toBe(true)
    record.beginStep(2)
    record.beginStep(1)
    expect(record.record(1, 'Language', false)).toBe(true)

    expect(trackOnboardingStepCompleted).toHaveBeenCalledTimes(2)
  })
})
