// Decision + commit for the one-time "Background & privacy" interstitial. The app
// is becoming a tray-resident, launch-at-login, always-listening companion;
// existing users (who onboarded before that shift) must acknowledge it once. New
// users consent inline during onboarding, so the interstitial is gated on having
// already completed onboarding.
import { setPreferences, type Preferences } from './preferences'

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

/**
 * Commit the user's background/privacy choices. Shared by the onboarding step
 * (BackgroundPrivacyStep) and the existing-user interstitial
 * (BackgroundConsentInterstitial) so both persist consent identically: stamp
 * backgroundConsentAt (so the interstitial never re-fires for a user who just
 * consented), record recordingConsentedAt only when listening stays on, and
 * apply the launch-at-login choice to the OS (best-effort — never blocks).
 */
export function persistBackgroundConsent(opts: {
  listening: boolean
  launchAtLogin: boolean
}): void {
  const { listening, launchAtLogin } = opts
  setPreferences({
    continuousRecording: listening,
    backgroundConsentAt: Date.now(),
    ...(listening ? { recordingConsentedAt: Date.now() } : {})
  })
  void window.omi?.setLaunchAtLogin?.(launchAtLogin)
}
