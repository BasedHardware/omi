import Foundation

/// One-shot "open the main chat" request raised by surfaces outside the main
/// window (the floating bar's "Continue in Omi" affordances). Revealing the
/// window alone is not enough: the main window may be resting on any tab, so
/// the conversation the user asked to continue would be nowhere in sight.
///
/// Flow: the raiser calls `request()` (which also posts
/// `.openMainChatRequested`); `DesktopHomeView` switches to the Home tab on
/// the notification, and `DashboardPage` consumes the pending request when it
/// is (or becomes) visible and opens the chat panel.
@MainActor
final class MainChatNavigationRequestStore {
  static let shared = MainChatNavigationRequestStore()

  private(set) var isPending = false

  func request() {
    isPending = true
    NotificationCenter.default.post(name: .openMainChatRequested, object: nil)
  }

  /// Returns whether a request was pending, and clears it.
  func consume() -> Bool {
    defer { isPending = false }
    return isPending
  }
}

extension Notification.Name {
  static let openMainChatRequested = Notification.Name("openMainChatRequested")
}
