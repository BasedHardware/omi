import AppKit

@MainActor
enum PermissionDragGuidance {
  private static var lastPresentedAt: Date?

  static func presentDragToGrantHelper() async {
    if let lastPresentedAt, Date().timeIntervalSince(lastPresentedAt) < 2 { return }
    lastPresentedAt = Date()

    let appURL = Bundle.main.bundleURL
    let appName =
      (Bundle.main.infoDictionary?["CFBundleName"] as? String)
      ?? (Bundle.main.infoDictionary?["CFBundleDisplayName"] as? String)
      ?? "Omi"
    let icon = NSApp.applicationIconImage ?? NSWorkspace.shared.icon(forFile: appURL.path)
    let initialAnchor = CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame()

    CloudConnectorGuidanceOverlay.shared.presentDragToGrantCard(
      appIcon: icon, appName: appName, appURL: appURL, near: initialAnchor)

    guard initialAnchor == nil else { return }
    for _ in 0..<15 {
      try? await Task.sleep(nanoseconds: 150_000_000)
      if let frame = CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame() {
        CloudConnectorGuidanceOverlay.shared.repositionDragCard(near: frame)
        return
      }
    }
  }
}
