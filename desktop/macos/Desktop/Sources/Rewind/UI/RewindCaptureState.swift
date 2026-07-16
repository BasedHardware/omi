/// Monitoring is transient runtime state. It must never overwrite a user's
/// persisted capture preference because recovery can restart monitoring.
struct RewindCaptureState: Equatable {
  let isMonitoring: Bool
  let captureEnabled: Bool

  static func afterMonitoringChange(captureEnabled: Bool, monitoring: Bool) -> Self {
    Self(isMonitoring: monitoring, captureEnabled: captureEnabled)
  }
}
