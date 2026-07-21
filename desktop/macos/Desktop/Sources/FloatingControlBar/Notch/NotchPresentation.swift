import Foundation

/// Tabs available in the open notch panel. Chat is primary (chat-first); the
/// agents tab lists running/recent agent sessions.
enum NotchTab: String, CaseIterable, Identifiable, Equatable {
  case chat, agents

  var id: String { rawValue }

  var symbol: String {
    switch self {
    case .chat: return "message"
    case .agents: return "circle.hexagongrid"
    }
  }

  var label: String {
    switch self {
    case .chat: return "Chat"
    case .agents: return "Agents"
    }
  }
}

/// The single, authoritative description of what the notch is showing right
/// now. Both the panel size (`NotchViewModel.size(for:)`) and the rendered
/// content (`NotchView.bodyContent`) derive from this one value, so they can
/// never disagree. Derived from `NotchViewModel.state` plus live service state
/// via a priority ladder: open > listening > thinking > hint > notification > idle.
enum NotchPresentation: Equatable {
  case open(NotchTab)
  case listening
  case thinking
  case hint(String)
  case notification(UUID)
  case idle

  /// Whether the black body should cast its open-state shadow / glow.
  var isExpandedSurface: Bool {
    switch self {
    case .open, .notification: return true
    case .listening, .thinking, .hint, .idle: return false
    }
  }

  /// The priority ladder: a user-opened panel always wins, voice states beat
  /// passive surfaces, and a notification only shows on an otherwise idle
  /// notch. Pure so the ordering is unit-testable.
  static func derive(
    isOpen: Bool,
    tab: NotchTab,
    isVoiceListening: Bool,
    isThinking: Bool,
    hintText: String,
    notificationID: UUID?
  ) -> NotchPresentation {
    if isOpen { return .open(tab) }
    if isVoiceListening { return .listening }
    if isThinking { return .thinking }
    if !hintText.isEmpty { return .hint(hintText) }
    if let notificationID { return .notification(notificationID) }
    return .idle
  }
}
