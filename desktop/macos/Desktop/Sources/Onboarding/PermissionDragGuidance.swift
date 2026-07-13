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

    // The overlay owns the System Settings lifecycle from here: it re-anchors over
    // the window once it appears and dismisses the card when the user closes it.
    CloudConnectorGuidanceOverlay.shared.presentDragToGrantCard(
      appIcon: icon, appName: appName, appURL: appURL,
      near: CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame())
  }
}
