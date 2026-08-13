import Foundation

extension ProactiveAssistantsPlugin {
  /// Read-only, privacy-safe state for named-bundle QA. This intentionally exposes only
  /// coarse buckets and fixed gate labels: callers must be able to tell whether capture
  /// can run without receiving the active app, window title, exact idle duration, or any
  /// screenshot content.
  func automationCaptureStatusSnapshot() -> ProactiveCaptureStatusSnapshot {
    ProactiveCaptureStatusSnapshot(
      isMonitoring: isMonitoring,
      hasScreenRecordingPermission: ScreenCaptureService.checkPermission(),
      screenAnalysisEnabled: AssistantSettings.shared.screenAnalysisEnabled,
      contextBucketsEnabled: ContextBucketsFeature.isEnabled,
      captureHealth: screenCaptureHealth.rawValue,
      captureGate: automationCaptureGateLabel,
      systemIdleBucket: Self.automationSystemIdleBucket(for: systemIdleSeconds()),
      currentAppExcluded: currentApp.map { RewindSettings.shared.isAppExcluded($0) }
    )
  }

  /// Stable, non-sensitive representation of the last capture gate. The nested optional
  /// distinguishes "no tick has run yet" from an observed flowing tick.
  private var automationCaptureGateLabel: String {
    switch lastCaptureGateReason {
    case .none:
      return "unknown"
    case .some(.none):
      return "flowing"
    case .some(.some(let reason)):
      switch reason {
      case "idle", "excluded_app", "waiting_for_user_window", "no_window_id", "external_capture_yield",
        "special_system_mode":
        return reason
      default:
        return "other"
      }
    }
  }

  static func automationSystemIdleBucket(for seconds: TimeInterval) -> String {
    guard seconds.isFinite, seconds >= 0 else { return "unknown" }
    switch seconds {
    case ..<3:
      return "active"
    case ..<15:
      return "recent"
    case ..<60:
      return "settling"
    default:
      return "idle"
    }
  }
}
