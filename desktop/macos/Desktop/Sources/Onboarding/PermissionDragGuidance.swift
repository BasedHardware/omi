import AppKit

@MainActor
enum PermissionDragGuidance {
  private static var lastPresentedAt: Date?

  /// Remove the drag card immediately — the permission was granted or the user
  /// skipped, so the floating icon should not linger.
  static func dismiss() {
    lastPresentedAt = nil
    CloudConnectorGuidanceOverlay.shared.dismiss()
  }

  static func presentDragToGrantHelper() async {
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
      if let frame = CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame() {
        anchor = frame
        break
      }
      try? await Task.sleep(nanoseconds: 200_000_000)
    }

    // The overlay owns the System Settings lifecycle from here: it re-anchors over
    // the window as it moves and dismisses the card when the user closes it.
    CloudConnectorGuidanceOverlay.shared.presentDragToGrantCard(
      appIcon: icon, appName: appName, appURL: appURL, near: anchor)
  }
}
