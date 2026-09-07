// @vitest-environment jsdom
// Regression guard for the AutoCreatedTasksStep wire-up in the onboarding wizard.
// Bugs caught by this suite: TOTAL_STEPS was 14 (step 14 was unreachable),
// handleGoal called finishToChat() instead of next(), GoalStep onSkip called
// finishToChat() instead of next(), and AutoCreatedTasksStep was never imported.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'

const h = vi.hoisted(() => ({
  completeOnboarding: vi.fn(),
  setPendingRoute: vi.fn(),
  setPreferences: vi.fn()
}))

vi.mock('../lib/preferences', () => ({
  getPreferences: vi.fn(() => ({ onboardingStep: 13 })),
  setPreferences: h.setPreferences,
  completeOnboarding: h.completeOnboarding,
  setPendingRoute: h.setPendingRoute
}))
vi.mock('../lib/onboardingProgress', () => ({
  clampOnboardingStep: vi.fn((s: number | undefined) => s ?? 0)
}))
vi.mock('../lib/userProfile', () => ({ syncLanguage: vi.fn(), setDisplayName: vi.fn() }))
vi.mock('../lib/languages', () => ({
  resolveLanguageCode: vi.fn((s: string) => s),
  languageLabel: vi.fn((s: string) => s)
}))
vi.mock('../lib/analytics', () => ({ trackHowDidYouHear: vi.fn() }))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
vi.mock('../lib/goals', () => ({ createGoal: vi.fn(async () => {}) }))
vi.mock('../lib/onboardingGraph', () => ({
  initOnboardingGraph: vi.fn(async () => {}),
  addUserNode: vi.fn(async () => {}),
  addLanguageNode: vi.fn(async () => {}),
  useOnboardingGraph: vi.fn(() => ({ nodes: [], edges: [] }))
}))
vi.mock('../components/graph/BrainGraph', () => ({ BrainGraph: () => null }))

// Stub every step — only GoalStep needs interaction for these tests.
vi.mock('../components/onboarding/NameStep', () => ({ NameStep: () => null }))
vi.mock('../components/onboarding/LanguageStep', () => ({ LanguageStep: () => null }))
vi.mock('../components/onboarding/HowDidYouHearStep', () => ({ HowDidYouHearStep: () => null }))
vi.mock('../components/onboarding/TrustStep', () => ({ TrustStep: () => null }))
vi.mock('../components/onboarding/BackgroundPrivacyStep', () => ({
  BackgroundPrivacyStep: () => null
}))
vi.mock('../components/onboarding/ScreenPermissionStep', () => ({
  ScreenPermissionStep: () => null
}))
vi.mock('../components/onboarding/BuildProfileStep', () => ({ BuildProfileStep: () => null }))
vi.mock('../components/onboarding/MicPermissionStep', () => ({ MicPermissionStep: () => null }))
vi.mock('../components/onboarding/AutomationPermissionStep', () => ({
  AutomationPermissionStep: () => null
}))
vi.mock('../components/onboarding/ShortcutSetupStep', () => ({ ShortcutSetupStep: () => null }))
vi.mock('../components/onboarding/VoiceIntroStep', () => ({ VoiceIntroStep: () => null }))
vi.mock('../components/onboarding/AskDemoStep', () => ({ AskDemoStep: () => null }))
vi.mock('../components/onboarding/DataSourcesStep', () => ({ DataSourcesStep: () => null }))
vi.mock('../components/onboarding/GoalStep', () => ({
  GoalStep: ({
    onContinue,
    onSkip
  }: {
    onContinue: (goal: string) => void
    onSkip: () => void
  }) => (
    <div data-testid="goal-step">
      <button data-testid="goal-continue" onClick={() => onContinue('learn faster')}>
        Continue
      </button>
      <button data-testid="goal-skip" onClick={onSkip}>
        Skip
      </button>
    </div>
  )
}))

import { Onboarding } from './Onboarding'

beforeEach(() => {
  h.completeOnboarding.mockClear()
  h.setPendingRoute.mockClear()
  h.setPreferences.mockClear()
})
afterEach(cleanup)

describe('Onboarding — AutoCreatedTasksStep wire-up (step 14)', () => {
  it('GoalStep onContinue advances to AutoCreatedTasksStep without completing onboarding', () => {
    render(<Onboarding />)
    expect(screen.getByTestId('goal-step'))
    fireEvent.click(screen.getByTestId('goal-continue'))

    // Must not complete onboarding — that happens only after the tasks step.
    expect(h.completeOnboarding).not.toHaveBeenCalled()
    expect(screen.getByText('Take me to my tasks'))  })

  it('GoalStep onSkip advances to AutoCreatedTasksStep without completing onboarding', () => {
    render(<Onboarding />)
    expect(screen.getByTestId('goal-step'))
    fireEvent.click(screen.getByTestId('goal-skip'))

    expect(h.completeOnboarding).not.toHaveBeenCalled()
    expect(screen.getByText('Take me to my tasks'))  })

  it('AutoCreatedTasksStep onFinish routes to /tasks and completes onboarding', () => {
    render(<Onboarding />)
    fireEvent.click(screen.getByTestId('goal-continue'))

    fireEvent.click(screen.getByText('Take me to my tasks'))

    expect(h.setPendingRoute).toHaveBeenCalledWith('/tasks')
    expect(h.completeOnboarding).toHaveBeenCalledTimes(1)
  })
})
