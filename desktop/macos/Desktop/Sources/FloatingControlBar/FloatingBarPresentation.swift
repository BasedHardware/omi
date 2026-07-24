import Foundation

/// Shared reveal implementation for persistent settings, temporary snoozes,
/// and direct Push-to-Talk presentation.
extension FloatingControlBarManager {
  /// Applies the saved launch preference without overriding a temporary
  /// notification snooze. Push-to-Talk and Settings call `show()` instead.
  func showForLaunch() {
    present(.background, persistEnabledPreference: false)
  }

  func present(
    _ request: FloatingBarPresentationRequest,
    persistEnabledPreference: Bool
  ) {
    log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
    if persistEnabledPreference {
      isEnabled = true
    }
    guard FloatingBarPresentationPolicy.shouldPresent(request: request, isSnoozed: isSnoozed) else {
      return
    }
    // Reveal on every hidden→present transition (not just once per session):
    // the island should always grow out of the notch instead of popping in.
    let shouldPlayNotchReveal =
      window?.usesNotchIslandForCurrentScreen == true
      && (window?.isVisible != true || !hasRevealedNotchThisSession)
    hasRevealedNotchThisSession = true
    window?.normalizeForTemporaryShow()
    window?.makeKeyAndOrderFront(nil)
    if shouldPlayNotchReveal {
      window?.playNotchRevealAnimation()
    }
    log("FloatingControlBarManager: show() done, frame=\(window?.frame ?? .zero)")

    // Auto-focus input if AI conversation is open.
    if let window, window.state.showingAIConversation && !window.state.showingAIResponse {
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
        window.focusInputField()
      }
    }
  }
}
