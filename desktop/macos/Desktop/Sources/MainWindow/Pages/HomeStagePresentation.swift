import SwiftUI

enum HomeStageMode: Equatable {
  case hub
  case chat
  case connect

  /// Whether the user-facing collapse catchers (click-outside + Esc) mount.
  /// Only a panel that can collapse to a *different* resting surface gets a
  /// catcher. The hub is the base surface, never an overlay: mounting a
  /// catcher over hub-with-history would invert the gesture and make a stray
  /// click or Esc *open* the chat.
  static func collapseCatcherActive(mode: HomeStageMode, resting: HomeStageMode) -> Bool {
    mode != resting && mode != .hub
  }

  var automationLabel: String {
    switch self {
    case .hub: return "hub"
    case .chat: return "chat"
    case .connect: return "connect"
    }
  }
}

enum HomeHistoryPresentationPolicy {
  static func restingMode(isLoading: Bool, messageCount: Int) -> HomeStageMode {
    !isLoading && messageCount > 0 ? .chat : .hub
  }
}

/// Shared stage motion for Home panels, including the initial history restore
/// where the useful hub leaves upward and the completed chat rises from below.
private struct HomeStageDropModifier: ViewModifier {
  let offsetY: CGFloat
  let scale: CGFloat
  let opacity: Double

  func body(content: Content) -> some View {
    content
      .offset(y: offsetY)
      .scaleEffect(scale, anchor: .top)
      .opacity(opacity)
  }
}

extension AnyTransition {
  static var homeDropFromTop: AnyTransition {
    .modifier(
      active: HomeStageDropModifier(offsetY: -46, scale: 0.97, opacity: 0),
      identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
    )
  }

  static var homeHubFade: AnyTransition {
    .modifier(
      active: HomeStageDropModifier(offsetY: 14, scale: 1, opacity: 0),
      identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
    )
  }

  static var homeHubStage: AnyTransition {
    .asymmetric(
      insertion: .modifier(
        active: HomeStageDropModifier(offsetY: 14, scale: 1, opacity: 0),
        identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
      ),
      removal: .modifier(
        active: HomeStageDropModifier(offsetY: -54, scale: 0.98, opacity: 0),
        identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
      )
    )
  }

  static var homeChatRise: AnyTransition {
    .asymmetric(
      insertion: .modifier(
        active: HomeStageDropModifier(offsetY: 54, scale: 0.98, opacity: 0),
        identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
      ),
      removal: .modifier(
        active: HomeStageDropModifier(offsetY: -28, scale: 0.98, opacity: 0),
        identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
      )
    )
  }

  static var homeSuggestionsFade: AnyTransition {
    .modifier(
      active: HomeStageDropModifier(offsetY: 10, scale: 1, opacity: 0),
      identity: HomeStageDropModifier(offsetY: 0, scale: 1, opacity: 1)
    )
  }
}
