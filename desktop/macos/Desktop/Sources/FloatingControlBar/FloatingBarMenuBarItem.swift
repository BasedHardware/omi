import AppKit

/// The status-bar menu's "Show Floating Bar" / "Hide Floating Bar" item.
///
/// The notch's Hide control persists `isEnabled = false`, which removes the bar entirely; before
/// this item the only ways back were Push-to-Talk (which not everyone uses) and a Settings switch
/// several clicks deep. The menu bar icon is always there, so the way back lives in its menu,
/// driving the same preference and the same `show()` / `hide()` the Settings switch uses.
enum FloatingBarMenuBarItem {
  static func title(isEnabled: Bool) -> String {
    isEnabled ? "Hide Floating Bar" : "Show Floating Bar"
  }

  /// A new menu item bound to the shared controller. Its title is re-read every time the menu
  /// opens (`validateMenuItem`), so a change made from Settings or the notch shows up.
  @MainActor
  static func make() -> NSMenuItem {
    let item = NSMenuItem(
      title: title(isEnabled: FloatingControlBarManager.shared.isEnabled),
      action: #selector(FloatingBarMenuBarItemController.toggle(_:)),
      keyEquivalent: "")
    item.target = FloatingBarMenuBarItemController.shared
    return item
  }
}

/// The menu item's target. `NSMenuItem.target` is weak, so the controller is a process-lifetime
/// singleton.
@MainActor
final class FloatingBarMenuBarItemController: NSObject, NSMenuItemValidation {
  static let shared = FloatingBarMenuBarItemController()

  /// Seams for tests; production reads and drives `FloatingControlBarManager`.
  var isEnabled: () -> Bool = { FloatingControlBarManager.shared.isEnabled }
  var setEnabled: (Bool) -> Void = { enabled in
    AnalyticsManager.shared.menuBarActionClicked(action: enabled ? "floating_bar_show" : "floating_bar_hide")
    if enabled {
      FloatingControlBarManager.shared.show()
    } else {
      FloatingControlBarManager.shared.hide()
    }
  }

  @objc func toggle(_ sender: NSMenuItem) {
    let show = !isEnabled()
    log("FloatingBarMenuBarItem: \(show ? "show" : "hide") from status-bar menu")
    setEnabled(show)
    sender.title = FloatingBarMenuBarItem.title(isEnabled: isEnabled())
  }

  func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
    menuItem.title = FloatingBarMenuBarItem.title(isEnabled: isEnabled())
    return true
  }
}
