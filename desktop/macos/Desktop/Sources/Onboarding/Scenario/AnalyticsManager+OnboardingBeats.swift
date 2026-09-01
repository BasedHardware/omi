import Foundation

// MARK: - Scenario onboarding analytics

extension AnalyticsManager {
  /// One event per beat exit. Bounded dimensions only: beat name, index, elapsed time, and the
  /// permission outcome; never page titles, note text, or transcripts.
  func onboardingBeatCompleted(
    beat: String,
    index: Int,
    elapsedMs: Int,
    skipped: Bool,
    permission: String?,
    granted: Bool?,
    detection: String?
  ) {
    PostHogManager.shared.onboardingBeatCompleted(
      beat: beat,
      index: index,
      elapsedMs: elapsedMs,
      skipped: skipped,
      permission: permission,
      granted: granted,
      detection: detection
    )
  }
}
