enum ScreenRecordingPermissionPolicy {
  /// The UI permission badge mirrors macOS TCC, not capture-engine diagnostics.
  static func uiPermissionGranted(tccGranted: Bool) -> Bool {
    tccGranted
  }

  /// Capture-engine failures must never turn the permission row red. A denied
  /// TCC preflight already makes the permission state missing on its own.
  static func shouldMarkCaptureKitBroken(tccGranted: Bool) -> Bool {
    false
  }
}
