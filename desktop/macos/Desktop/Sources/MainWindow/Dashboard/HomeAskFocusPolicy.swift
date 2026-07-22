import Foundation

/// Monotonic generation policy for the deferred Home ask-field focus.
///
/// `DashboardPage.openHomeChat(focusInput:)` schedules the ask-field focus
/// after a run-loop yield so it lands once the stage transition has rendered.
/// Without invalidation that deferred focus is stale the instant the user — or
/// the automation bridge — connects / collapses / closes before the yield
/// resumes, and a stale focus reopens chat through the focus observer
/// (home-stage S6 regression: expected hub, returned chat before the query
/// completed).
///
/// Each invalidation bumps the generation; a deferred focus applies only if its
/// token still matches the current generation *and* the stage is still chat.
/// This type is the production seam — pure and deterministic, unit-tested
/// without touching the run loop.
final class HomeAskFocusPolicy {
  /// Monotonic invalidation counter. Bumped by every connect / collapse / close.
  private(set) var generation: Int = 0

  /// Captured before scheduling a deferred focus; compared on resume.
  struct Token: Equatable {
    let generation: Int
  }

  /// Snapshot the current generation to pair with a deferred focus.
  func currentToken() -> Token { Token(generation: generation) }

  /// Invalidate every outstanding deferred focus. Returns the new generation.
  @discardableResult
  func invalidate() -> Int {
    generation += 1
    return generation
  }

  /// True only if `token` was captured against the still-current generation.
  func isCurrent(_ token: Token) -> Bool { token.generation == generation }
}
