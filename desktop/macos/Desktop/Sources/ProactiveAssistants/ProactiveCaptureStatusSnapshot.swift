import Foundation

/// Coarse capture state exposed only to the non-production automation bridge.
///
/// This type deliberately has no app, window, title, path, screenshot, or exact
/// idle-duration fields. Keep additions privacy-safe and bucketed.
struct ProactiveCaptureStatusSnapshot: Codable, Equatable, Sendable {
  let isMonitoring: Bool
  let hasScreenRecordingPermission: Bool
  let screenAnalysisEnabled: Bool
  let contextBucketsEnabled: Bool
  let captureHealth: String
  let captureGate: String
  let systemIdleBucket: String
  let currentAppExcluded: Bool?

  var automationDetail: [String: String] {
    [
      "is_monitoring": isMonitoring ? "true" : "false",
      "has_screen_recording_permission": hasScreenRecordingPermission ? "true" : "false",
      "screen_analysis_enabled": screenAnalysisEnabled ? "true" : "false",
      "context_buckets_enabled": contextBucketsEnabled ? "true" : "false",
      "capture_health": captureHealth,
      "capture_gate": captureGate,
      "system_idle_bucket": systemIdleBucket,
      "current_app_excluded": currentAppExcluded.map { $0 ? "true" : "false" } ?? "unknown",
    ]
  }
}
