import { trackOnboardingCompleted } from './analytics'
import { completeOnboarding, isOnboardingComplete, setPendingRoute } from './preferences'

/** The one successful terminal for Windows onboarding. */
export function finishOnboardingToChat(): void {
  if (isOnboardingComplete()) return
  setPendingRoute('/chat')
  completeOnboarding()
  trackOnboardingCompleted()
}
