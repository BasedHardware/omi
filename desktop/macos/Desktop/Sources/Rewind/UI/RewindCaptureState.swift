/// Monitoring is transient runtime state. It must never overwrite a user's
/// persisted capture preference because recovery can restart monitoring.
struct RewindCaptureState: Equatable {
  let isMonitoring: Bool
  let captureEnabled: Bool

  static func afterMonitoringChange(captureEnabled: Bool, monitoring: Bool) -> Self {
    Self(isMonitoring: monitoring, captureEnabled: captureEnabled)
  }

  /// Named development bundles previously seeded capture off so a fresh TCC
  /// identity could not begin storing frames after Screen Recording was granted.
  /// The capture engine now checks TCC without requesting it, so migrate that
  /// quiet default back to the product default exactly once.
  static func shouldRepairQuietBundleCaptureDefault(
    usesLazyDevPermissions: Bool,
    migrationApplied: Bool
  ) -> Bool {
    usesLazyDevPermissions && !migrationApplied
  }
}
