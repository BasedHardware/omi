import Foundation

extension ChatProvider {
  /// Which surface a query resolves to. Extracted as a pure decision (in its own
  /// file so the already-oversized `ChatProvider.swift` doesn't grow) so the
  /// onboarding-isolation precedence — the part that regressed — is unit-testable.
  enum QuerySurfaceChoice: Equatable { case onboarding, explicit, floatingMain, defaultMain }

  /// Onboarding isolation wins over any caller-supplied surface. The onboarding
  /// voice/screen demo runs through the real floating bar, which sends with an
  /// explicit `mainChatSurfaceReference()` — without this precedence that send
  /// would land on the real default chat (and the backend), leaking the demo turn
  /// into the Chat tab. `isOnboarding` is flipped false in complete()/skip() before
  /// any legitimate chat use, so this can't mis-route real traffic.
  nonisolated static func querySurfaceChoice(
    hasSurfaceRef: Bool, isOnboarding: Bool, isFloating: Bool
  ) -> QuerySurfaceChoice {
    if isOnboarding { return .onboarding }
    if hasSurfaceRef { return .explicit }
    if isFloating { return .floatingMain }
    return .defaultMain
  }
}
