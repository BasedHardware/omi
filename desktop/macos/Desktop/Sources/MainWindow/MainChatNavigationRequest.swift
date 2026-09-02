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
  /// Text to place in the composer, focused and **not sent**. Set by surfaces
  /// that want the user to glance at a suggested question before asking it
  /// (the first-real-app notch card, the daily summary's follow-up). Consumed
  /// by whichever shell's composer mounts or is already mounted.
  private(set) var pendingDraft: String?

  func request(draft: String? = nil) {
    isPending = true
    if let draft, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      pendingDraft = draft
    }
    NotificationCenter.default.post(name: .openMainChatRequested, object: nil)
  }

  /// Returns whether a request was pending, and clears it. The draft survives
  /// this call so a shell that consumes the navigation before its composer is
  /// mounted still finds the text when the composer appears.
  func consume() -> Bool {
    defer { isPending = false }
    return isPending
  }

  /// Returns the pending composer draft, and clears it. Exactly one composer
  /// takes it; a second caller gets `nil`.
  func consumeDraft() -> String? {
    defer { pendingDraft = nil }
    return pendingDraft
  }
}

extension Notification.Name {
  static let openMainChatRequested = Notification.Name("openMainChatRequested")
}
