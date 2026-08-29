import AppKit

@MainActor
enum PermissionDragGuidance {
  enum Permission: Sendable {
    case accessibility
    case screenRecording
    case fullDiskAccess
  }

  private static var lastPresentedAt: Date?

  /// Open the Accessibility privacy pane and offer the draggable app card when
  /// the grant is genuinely absent. A named or re-signed bundle can need to be
  /// added again, while an already-working grant should never be requested twice.
  @discardableResult
  static func openAccessibilitySettings(
    isAuthorized: () -> Bool = { true },
    open: (URL) -> Bool = { NSWorkspace.shared.open($0) },
    suspendForPermissionPrompt: () -> Void = {
      ShellSummon.suspendForPermissionPrompt()
    },
    presentDragGuidance: () -> Void = {
      Task { await PermissionDragGuidance.presentDragToGrantHelper(for: .accessibility) }
    }
  ) -> Bool {
    guard
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    else { return false }

    guard isAuthorized() else { return false }
    suspendForPermissionPrompt()
    guard open(url) else { return false }
    presentDragGuidance()
    return true
  }

  /// Remove the drag card immediately — the permission was granted or the user
  /// skipped, so the floating icon should not linger.
  static func dismiss() {
    lastPresentedAt = nil
    CloudConnectorGuidanceOverlay.shared.dismiss()
  }

  static func presentDragToGrantHelper(
    for permission: Permission,
    settingsPID: pid_t? = nil
  ) async {
    guard shouldPresentDragGuidance(permissionGranted: await isGranted(permission)) else {
      dismiss()
      return
    }
    if let lastPresentedAt, Date().timeIntervalSince(lastPresentedAt) < 2 { return }
    lastPresentedAt = Date()

    let appURL = Bundle.main.bundleURL
    let appName =
      (Bundle.main.infoDictionary?["CFBundleName"] as? String)
      ?? (Bundle.main.infoDictionary?["CFBundleDisplayName"] as? String)
      ?? "Omi"
    let icon = NSApp.applicationIconImage ?? NSWorkspace.shared.icon(forFile: appURL.path)

    // System Settings launches asynchronously (100s of ms). Wait for its window to
    // exist before presenting, so the card anchors to the real window from its first
    // paint instead of flashing in the detached bottom-of-screen fallback and
    // pointing at nothing (the reported "drag card appeared before Settings, arrow
    // pointing straight up" bug). Mirrors the screen-recording instruction overlay.
    var anchor: CGRect?
    for _ in 0..<12 {  // ~2.4s
      if let frame = CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame(pid: settingsPID) {
        anchor = frame
        break
      }
      try? await Task.sleep(nanoseconds: 200_000_000)
    }
    guard let anchor else {
      lastPresentedAt = nil
      return
    }

    // A fast toggle can land while System Settings is still opening. Re-check
    // at the final presentation boundary so a now-granted permission never
    // leaves the user with a stale instruction to drag the app again.
    guard shouldPresentDragGuidance(permissionGranted: await isGranted(permission)) else {
      dismiss()
      return
    }

    // The overlay owns the System Settings lifecycle from here: it re-anchors over
    // the window as it moves and dismisses the card when the user closes it.
    CloudConnectorGuidanceOverlay.shared.presentDragToGrantCard(
      appIcon: icon, appName: appName, appURL: appURL, near: anchor)
  }

  static func shouldPresentDragGuidance(permissionGranted: Bool) -> Bool {
    !permissionGranted
  }

  static func accessibilityGrantIsUsable(_ signals: AccessibilityProbeSignals) -> Bool {
    let projection = AppState.accessibilityProjection(signals)
    return projection.hasPermission && !projection.isBroken
  }

  private static func isGranted(_ permission: Permission) async -> Bool {
    switch permission {
    case .accessibility:
      let targets = AppState.accessibilityProbeTargets()
      let signals = await Task.detached(priority: .userInitiated) {
        AppState.probeAccessibilitySignals(targets: targets)
      }.value
      return accessibilityGrantIsUsable(signals)
    case .screenRecording:
      return ScreenCaptureService.checkPermission()
    case .fullDiskAccess:
      return await Task.detached(priority: .userInitiated) {
        AppState.probeFullDiskAccessGranted()
      }.value
    }
  }
}
