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
/// via a priority ladder:
/// open > listening > thinking > responding > hint > notification > idle.
enum NotchPresentation: Equatable {
  case open(NotchTab)
  case listening
  case thinking
  case responding
  case hint(String)
  case notification(UUID)
  case idle

  /// Whether the black body should cast its open-state shadow / glow. The two
  /// expanded voice states (listening, responding) grow out of the notch like
  /// an opened panel; thinking is the compact pill between them.
  var isExpandedSurface: Bool {
    switch self {
    case .open, .listening, .responding, .notification: return true
    case .thinking, .hint, .idle: return false
    }
  }

  /// The priority ladder: a user-opened panel always wins, then the voice turn
  /// runs listening -> thinking -> responding, then passive surfaces. Thinking
  /// beats responding so the "awaiting the answer" pill shows until the reply
  /// actually starts. Pure so the ordering is unit-testable.
  static func derive(
    isOpen: Bool,
    tab: NotchTab,
    isVoiceListening: Bool,
    isThinking: Bool,
    isResponding: Bool,
    hintText: String,
    notificationID: UUID?
  ) -> NotchPresentation {
    if isOpen { return .open(tab) }
    if isVoiceListening { return .listening }
    if isThinking { return .thinking }
    if isResponding { return .responding }
    if !hintText.isEmpty { return .hint(hintText) }
    if let notificationID { return .notification(notificationID) }
    return .idle
  }
}
