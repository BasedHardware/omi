import Foundation

/// Skip-vs-denied projection for the sidebar's permission rows.
///
/// "Onboarded but not granted" is not the same state as denied: a user who pressed
/// "Skip for now" made a deliberate choice, and pulsing their sidebar red as if macOS
/// had refused something asks them to fix a decision they just made. Microphone and
/// Notifications read the real TCC answer (`.denied`), but Screen Recording and
/// Accessibility have no public denied/notDetermined distinction — for those, the
/// durable onboarding intent is the only honest signal:
///
/// - Screen Recording: denied only while the capture **intent** is on and the grant
///   is missing (the user wants Rewind and macOS hasn't delivered). A skip turns the
///   intent off, so it stops reading as denied.
/// - Accessibility: denied unless onboarding recorded a skip. Absent marker (legacy
///   completions, pre-marker installs) keeps the previous missing-as-denied read.
enum SBOnboardingPermissionIntentPolicy {
  static func screenRecordingDenied(
    hasCompletedOnboarding: Bool,
    screenAnalysisIntentEnabled: Bool,
    permissionGranted: Bool
  ) -> Bool {
    hasCompletedOnboarding && screenAnalysisIntentEnabled && !permissionGranted
  }

  static func accessibilityDenied(
    hasCompletedOnboarding: Bool,
    accessibilityUsable: Bool,
    skippedInOnboarding: Bool
  ) -> Bool {
    hasCompletedOnboarding && !accessibilityUsable && !skippedInOnboarding
  }
}
