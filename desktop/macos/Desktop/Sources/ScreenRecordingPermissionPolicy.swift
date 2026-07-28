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

  /// A screen-recording grant only takes effect at process launch (the window
  /// server evaluates it once per connection). Granted now but not at launch
  /// means capture stays dead until the app relaunches — that is the only
  /// case where offering "Reopen Omi" is correct. In particular, an app that
  /// already relaunched after the grant must never be asked to reopen again.
  static func needsRelaunchToApply(grantedNow: Bool, grantedAtLaunch: Bool) -> Bool {
    grantedNow && !grantedAtLaunch
  }
}
