import AppKit
import SwiftUI

private final class MainWindowSendableBox<Value>: @unchecked Sendable {
  var value: Value
  init(_ value: Value) { self.value = value }
}

/// Activating the app's real main window from the notch (settings gear,
/// notification click-through). Waits for the window-key event instead of
/// guessing fixed delays, so navigate receivers are mounted before posts fire.
@MainActor
enum MainWindowReveal {
  /// Open the main window and navigate to the Floating Bar settings section.
  static func openSettings() {
    activate()
    runWhenMainWindowKey {
      NotificationCenter.default.post(name: .navigateToFloatingBarSettings, object: nil)
    }
  }

  static func activate() {
    NSApp.activate()
    if reveal() { return }
    // No existing window — open one and reveal it the moment it becomes key.
    AppDelegate.openMainWindow?()
    runWhenMainWindowKey {
      NSApp.activate()
      reveal()
    }
  }

  /// True for the app's real main window (not a panel or menu-bar popover).
  private static func isRealMainWindow(_ window: NSWindow) -> Bool {
    !(window is NSPanel)
      && window.frame.width > 300
      && window.frame.height > 200
      && !window.title.hasPrefix("Item-")
  }

  /// Run `action` once the main window is key — immediately if one already is,
  /// otherwise on the next didBecomeKeyNotification for a real main window.
  static func runWhenMainWindowKey(_ action: @escaping () -> Void) {
    let actionBox = MainWindowSendableBox(action)
    if let key = NSApp.keyWindow, isRealMainWindow(key) {
      // One runloop hop so a freshly-keyed window's content (e.g. the
      // navigate receiver) is mounted before we act.
      DispatchQueue.main.async { actionBox.value() }
      return
    }
    let tokenBox = MainWindowSendableBox<NSObjectProtocol?>(nil)
    let removeObserver: @Sendable () -> Void = {
      if let token = tokenBox.value { NotificationCenter.default.removeObserver(token) }
    }
    tokenBox.value = NotificationCenter.default.addObserver(
      forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main
    ) { note in
      let noteBox = MainWindowSendableBox(note)
      MainActor.assumeIsolated {
        guard let window = noteBox.value.object as? NSWindow, isRealMainWindow(window) else {
          return
        }
        removeObserver()
        DispatchQueue.main.async { actionBox.value() }
      }
    }
    // Safety net: drop the observer after a bounded delay so it can't linger
    // if no real main window ever becomes key.
    Timer.scheduledTimer(withTimeInterval: 10, repeats: false) { _ in removeObserver() }
  }

  @discardableResult
  private static func reveal() -> Bool {
    guard
      let window = NSApp.windows.first(where: { isRealMainWindow($0) && !$0.isMiniaturized })
        ?? NSApp.windows.first(where: { isRealMainWindow($0) })
    else {
      return false
    }
    window.deminiaturize(nil)
    window.makeKeyAndOrderFront(nil)
    window.orderFrontRegardless()
    return true
  }
}
