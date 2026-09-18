import Foundation

/// Processing-row telemetry. The 2/10-minute thresholds on the row are a
/// guess until these two events give them a measured distribution.
extension AnalyticsManager {
  /// Elapsed time from recording end to a terminal status, observed by the
  /// client. This is the number the processing-row thresholds are tuned from.
  func conversationProcessingCompleted(conversationId: String, elapsedSeconds: Int, outcome: String) {
    PostHogManager.shared.conversationProcessingCompleted(
      conversationId: conversationId, elapsedSeconds: elapsedSeconds, outcome: outcome)
  }

  /// Fired once per conversation when the row crosses the stalled threshold.
  func conversationProcessingStalled(conversationId: String, elapsedSeconds: Int) {
    PostHogManager.shared.conversationProcessingStalled(
      conversationId: conversationId, elapsedSeconds: elapsedSeconds)
  }
}
