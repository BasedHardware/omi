// Pure decision for the one-time "Background & privacy" interstitial. The app is
// becoming a tray-resident, launch-at-login, always-listening companion; existing
// users (who onboarded before that shift) must acknowledge it once. New users
// consent inline during onboarding, so the interstitial is gated on having
// already completed onboarding. No DOM/Electron deps — unit-tested.
import type { Preferences } from './preferences'

/**
 * Show the interstitial only to an existing, onboarded user who hasn't yet
 * acknowledged the background/privacy posture. A user still in the wizard
 * (onboardingCompletedAt unset) consents inline instead, so this returns false
 * for them — they never see both surfaces.
 */
export function shouldShowBackgroundConsent(prefs: Preferences): boolean {
  return (
    typeof prefs.onboardingCompletedAt === 'number' && typeof prefs.backgroundConsentAt !== 'number'
  )
}
