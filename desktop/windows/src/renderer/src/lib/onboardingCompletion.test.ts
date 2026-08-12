import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  setPendingRoute: vi.fn(),
  completeOnboarding: vi.fn(),
  isOnboardingComplete: vi.fn(() => false),
  trackOnboardingCompleted: vi.fn()
}))

vi.mock('./preferences', () => ({
  setPendingRoute: h.setPendingRoute,
  completeOnboarding: h.completeOnboarding,
  isOnboardingComplete: h.isOnboardingComplete
}))
vi.mock('./analytics', () => ({ trackOnboardingCompleted: h.trackOnboardingCompleted }))

import { finishOnboardingToChat } from './onboardingCompletion'

beforeEach(() => {
  vi.clearAllMocks()
  h.isOnboardingComplete.mockReturnValue(false)
})

describe('finishOnboardingToChat', () => {
  it('persists completion and records the shared macOS/Windows terminal event', () => {
    finishOnboardingToChat()

    expect(h.setPendingRoute).toHaveBeenCalledExactlyOnceWith('/chat')
    expect(h.completeOnboarding).toHaveBeenCalledOnce()
    expect(h.trackOnboardingCompleted).toHaveBeenCalledOnce()
  })

  it('does not duplicate the terminal transition after completion', () => {
    h.isOnboardingComplete.mockReturnValue(true)

    finishOnboardingToChat()

    expect(h.setPendingRoute).not.toHaveBeenCalled()
    expect(h.completeOnboarding).not.toHaveBeenCalled()
    expect(h.trackOnboardingCompleted).not.toHaveBeenCalled()
  })
})
