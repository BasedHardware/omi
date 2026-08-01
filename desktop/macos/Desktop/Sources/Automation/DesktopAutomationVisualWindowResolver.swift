import AppKit

/// Resolves semantic visual-export targets without growing the central bridge transport.
@MainActor
enum DesktopAutomationVisualWindowResolver {
  static func resolve(target: String?) -> NSWindow? {
    switch target {
    case "floating":
      return NSApp.windows.first(where: { $0 is FloatingControlBarWindow && $0.isVisible })
    case "overlay":
      return CloudConnectorGuidanceOverlay.shared.automationWindow
    case "projection_harness":
      return ProjectionAutomationHarness.shared.visibleWindow
    case "task_thread":
      return NSApp.windows.first(where: {
        $0.title == "Omi — Task thread scenario" && $0.isVisible
      })
    default:
      return NSApp.windows.first(where: { window in
        window.title.lowercased().hasPrefix("omi") || window.isMainWindow || window.isKeyWindow
      })
    }
  }
}
