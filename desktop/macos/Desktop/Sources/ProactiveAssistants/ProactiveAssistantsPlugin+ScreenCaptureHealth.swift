import Foundation

extension ProactiveAssistantsPlugin {
  func setScreenCaptureHealth(_ health: ScreenCaptureHealth) {
    guard health != screenCaptureHealth else { return }

    let previous = screenCaptureHealth
    updateScreenCaptureHealthState(health)

    switch (previous, health) {
    case (.active, .temporarilyUnavailable):
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "other",
        from: "screen_capture",
        to: "capture_paused",
        reason: "capability_mismatch",
        outcome: .degraded,
        extra: [
          "failure_class": "screen_capture_target_unavailable",
          "recovery_action": "wait_for_captureable_target",
          "recovery_result": "degraded",
        ]
      )
    case (.active, .recovering), (.temporarilyUnavailable, .recovering):
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "other",
        from: "screen_capture",
        to: "recovery_poll",
        reason: "other",
        outcome: .degraded,
        extra: [
          "failure_class": "screen_capture_engine_failure",
          "recovery_action": "retry_capture",
          "recovery_result": "degraded",
        ]
      )
    case (.temporarilyUnavailable, .active), (.recovering, .active):
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "other",
        from: "capture_paused",
        to: "screen_capture",
        reason: "capability_mismatch",
        outcome: .recovered,
        extra: [
          "failure_class": "screen_capture_recovered",
          "recovery_action": "resume_capture",
          "recovery_result": "recovered",
        ]
      )
    default:
      break
    }

    NotificationCenter.default.post(
      name: .assistantMonitoringStateDidChange,
      object: nil,
      userInfo: [
        "isMonitoring": isMonitoring,
        "screenCaptureHealth": health.rawValue,
      ]
    )
  }
}
