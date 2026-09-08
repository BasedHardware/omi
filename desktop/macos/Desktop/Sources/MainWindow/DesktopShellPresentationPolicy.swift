/// The notch is not a text surface. Typed conversation lives in the main window on every shell, so
/// backing out of an agent chat with nothing else to show in the notch lands in the main chat
/// rather than an empty composer. This used to be a per-shell flag (chat-first only); the legacy
/// shell kept a typed composer in the notch until it was removed outright.
@MainActor
enum FloatingPrimaryTextInputRouting {
  static func shouldRouteAgentExitToMainApp(hasMainConversation: Bool) -> Bool {
    !hasMainConversation
  }
}
