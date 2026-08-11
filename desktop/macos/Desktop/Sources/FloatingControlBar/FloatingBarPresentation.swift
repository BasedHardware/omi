import Foundation
import OmiTheme
import SwiftUI

/// Whether a presentation request is allowed to change the user's durable
/// Floating Bar preference. Onboarding may borrow the real bar for a demo, but
/// must leave that preference exactly as it found it.
enum FloatingBarPreferenceMutation: Equatable {
  case setEnabled(Bool)
  case preserve

  /// `nil` means the presentation is transient and must not write settings.
  var persistedEnabledValue: Bool? {
    switch self {
    case .setEnabled(let enabled): return enabled
    case .preserve: return nil
    }
  }
}

extension FloatingControlBarWindow {
  var shouldOrderOutAfterConversationClose: Bool {
    !FloatingControlBarManager.shared.isEnabled
      && state.currentNotification == nil
      && !state.showingAIConversation
  }

  /// Starts the token-fenced retraction after presentation eligibility has
  /// been established. Keeping this boundary independent of `isVisible`
  /// lets lifecycle tests exercise stale deadlines on headless CI runners.
  func beginNotchRetraction(then completion: @escaping () -> Void) {
    notchRetractionCancellation?.cancel()
    frameAnimationToken += 1
    notchRetractionGeneration &+= 1
    let generation = notchRetractionGeneration
    OmiMotion.withGated(.easeIn(duration: 0.18)) {
      state.notchRevealProgress = 0.01
    }
    notchRetractionCancellation = notchRetractionScheduler.schedule(after: 0.18) { [weak self] in
      guard let self, self.notchRetractionGeneration == generation else { return }
      completion()
      // Leave the island ready to render for show paths that skip the
      // reveal (e.g. showTemporarily) — the next reveal re-zeroes it.
      self.state.notchRevealProgress = 1
      self.notchRetractionCancellation = nil
    }
  }
}

/// Shared reveal implementation for persistent settings, temporary snoozes,
/// and direct Push-to-Talk presentation.
extension FloatingControlBarManager {
  /// Applies the saved launch preference without overriding a temporary
  /// notification snooze. Push-to-Talk and Settings call `show()` instead.
  func showForLaunch() {
    present(.background, preferenceMutation: .preserve)
  }

  /// Shows the real Floating Bar for an onboarding voice demo without changing
  /// the user's saved bar setting.
  func showForOnboardingDemo() {
    present(.explicitUserAction, preferenceMutation: .preserve)
  }

  /// Retracts an onboarding voice demo without changing the user's saved bar
  /// setting.
  func hideForOnboardingDemo() {
    retract(preferenceMutation: .preserve)
  }

  func present(
    _ request: FloatingBarPresentationRequest,
    preferenceMutation: FloatingBarPreferenceMutation
  ) {
    log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
    if let enabled = preferenceMutation.persistedEnabledValue {
      isEnabled = enabled
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
      if !window.focusInputField() {
        // SwiftUI may still be attaching the text view. Retry on its next
        // layout pass rather than relying on a fixed wall-clock delay.
        DispatchQueue.main.async { [weak window] in
          window?.focusInputField()
        }
      }
    }
  }

  func retract(preferenceMutation: FloatingBarPreferenceMutation) {
    if let enabled = preferenceMutation.persistedEnabledValue {
      isEnabled = enabled
    }
    if let window {
      window.retractIntoNotch { [weak window] in
        window?.orderOut(nil)
      }
    }
  }
}
