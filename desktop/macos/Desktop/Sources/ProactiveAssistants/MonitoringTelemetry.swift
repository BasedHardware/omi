import Foundation

/// Closed, privacy-safe telemetry contract for monitoring session duration.
///
/// `Monitoring Started` / `Monitoring Stopped` used to carry zero properties,
/// so a churn analysis could only proxy "ran Omi" against a start-event
/// count — it could not tell a 10-minute session from an 8-hour one. This
/// contract adds the session boundary needed to compute a real runtime dose:
/// wall-clock duration, active duration with sleep/screen-lock time removed,
/// and how the session ended.
///
/// Payloads carry bounded dimensions only: a UUID session id, numeric
/// durations, and closed enum strings (`MonitoringStopReason`,
/// `MonitoringDurationSource`). Never a window title, app name, bundle id,
/// URL, or file path. Mirrors the allow-list pattern in
/// `IntegrationNudgeTelemetry` / `IntegrationConnectTelemetry`.
enum MonitoringTelemetry {
  /// PostHog event names. Stable identifiers — do not rename.
  static let startedEventName = "Monitoring Started"
  static let stoppedEventName = "Monitoring Stopped"

  /// Keys permitted in any emitted payload. Anything else is dropped by the
  /// allow-list filter.
  static let allowedKeys: Set<String> = [
    "session_id",
    "duration_seconds",
    "active_seconds",
    "paused_seconds",
    "stop_reason",
    "duration_source",
    "recovered_after_seconds",
  ]

  static func startedPayload(sessionID: String) -> [String: Any] {
    allowListOnly(["session_id": sessionID])
  }

  static func stoppedPayload(summary: MonitoringSummary) -> [String: Any] {
    allowListOnly([
      "session_id": summary.sessionID,
      "duration_seconds": Int(summary.durationSeconds.rounded()),
      "active_seconds": Int(summary.activeSeconds.rounded()),
      "paused_seconds": Int(summary.pausedSeconds.rounded()),
      "stop_reason": summary.stopReason.rawValue,
      "duration_source": summary.durationSource.rawValue,
    ])
  }

  /// Recovery-only payload. The event is stamped "now" — recovery time, not
  /// the original session's stop time — so a session that ran and crashed
  /// Monday night reports its `Monitoring Stopped` on Tuesday, whenever Omi
  /// is next launched. That lag matters for day-bucketed queries.
  /// `recovered_after_seconds` tells the analyst how stale the underlying
  /// heartbeat was at recovery time.
  static func recoveredStoppedPayload(_ outcome: MonitoringSessionRecovery.Outcome) -> [String: Any] {
    allowListOnly([
      "session_id": outcome.sessionID,
      "duration_seconds": Int(outcome.durationSeconds.rounded()),
      "active_seconds": Int(outcome.activeSeconds.rounded()),
      "paused_seconds": Int(outcome.pausedSeconds.rounded()),
      "stop_reason": outcome.stopReason.rawValue,
      "duration_source": outcome.durationSource.rawValue,
      "recovered_after_seconds": Int(outcome.recoveredAfterSeconds.rounded()),
    ])
  }

  private static func allowListOnly(_ properties: [String: Any]) -> [String: Any] {
    properties.filter { allowedKeys.contains($0.key) }
  }
}
