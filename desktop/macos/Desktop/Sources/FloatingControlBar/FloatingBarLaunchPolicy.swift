import CoreGraphics

/// Product-level launch policy for the floating bar.
///
/// Invariant: normal signed-in Desktop launch must show the floating bar whenever
/// the user has it enabled, even on notched displays. Deferred reveal is reserved
/// for explicit opt-in contexts (onboarding/demo/minimal mode) where hiding until
/// first Push-to-Talk is the intended UX.
enum FloatingBarLaunchContext {
  case normalSignedInDesktop
  case onboardingOrDemo
  case explicitMinimalMode
}

enum FloatingBarLaunchPresentation: Equatable {
  case hidden
  case showImmediately
  case deferUntilFirstPushToTalk
}

/// A temporary snooze silences passive floating-bar presentation, but it must
/// never swallow a direct request to talk. Settings-hidden and snoozed bars
/// therefore share the same Push-to-Talk reveal behavior.
enum FloatingBarPresentationRequest {
  case explicitUserAction
  case background
}

enum FloatingBarPresentationPolicy {
  static func shouldPresent(
    request: FloatingBarPresentationRequest,
    isSnoozed: Bool
  ) -> Bool {
    switch request {
    case .explicitUserAction:
      true
    case .background:
      !isSnoozed
    }
  }
}

struct FloatingBarLaunchPolicy {
  static func presentation(
    isEnabled: Bool,
    context: FloatingBarLaunchContext,
    displayHasNotch: Bool
  ) -> FloatingBarLaunchPresentation {
    guard isEnabled else { return .hidden }

    switch context {
    case .normalSignedInDesktop:
      return .showImmediately
    case .onboardingOrDemo, .explicitMinimalMode:
      return displayHasNotch ? .deferUntilFirstPushToTalk : .showImmediately
    }
  }
}

/// When AppKit or an onboarding demo has ordered the notch out, decide whether
/// the user's durable bar should come back. Disabled and snoozed bars stay
/// hidden. A session that has never presented the bar (deferred until first
/// Push-to-Talk) also stays hidden — Space switches must not promote it.
enum FloatingBarDurableVisibilityPolicy {
  static func shouldRestoreWhenAppKitOrderedOut(
    isEnabled: Bool,
    isSnoozed: Bool,
    hasBeenPresentedThisSession: Bool
  ) -> Bool {
    isEnabled && !isSnoozed && hasBeenPresentedThisSession
  }

  /// After a demo retracts with `.preserve`, restore the saved bar without
  /// writing a hide. Disabled and snoozed preferences stay hidden.
  static func shouldRestoreAfterOnboardingDemo(
    isEnabled: Bool,
    isSnoozed: Bool
  ) -> Bool {
    isEnabled && !isSnoozed
  }
}

/// Where the notch may land after a Space / display reassignment.
///
/// The main Omi shell is often the key window on another display. Using that
/// screen to recenter or to flip island vs pill parks a notch-sized panel in
/// the middle of the laptop — or draws pill chrome inside the camera housing.
enum FloatingBarPlacementScreenPolicy {
  /// Recentering an already-created bar. Never follow the key window.
  static func screenForRecentering<Screen>(
    barScreen: Screen?,
    cursorScreen: Screen?,
    mainScreen: Screen?,
    firstScreen: Screen?
  ) -> Screen? {
    barScreen ?? cursorScreen ?? mainScreen ?? firstScreen
  }

  /// A visible panel with no `NSWindow.screen` yet is mid reassignment.
  /// Falling back to the key window can flip `usesNotchIsland` off and leave
  /// pill chrome inside a notch-sized frame under the camera housing.
  static func shouldHoldIslandModeWhileScreenIsReassigning(
    isVisible: Bool,
    barScreenMissing: Bool
  ) -> Bool {
    isVisible && barScreenMissing
  }

  /// A visible panel with no `NSWindow.screen` is mid-reassignment. Cursor or
  /// main-display fallbacks park the island on the wrong monitor.
  static func shouldSkipVisibleBarLayoutUntilScreenReturns(
    isVisible: Bool,
    barScreenMissing: Bool
  ) -> Bool {
    isVisible && barScreenMissing
  }

  /// Space changes must rebuild the frame when island mode flips, not only
  /// when the bar is currently in notch mode. An early return after mutating
  /// the SwiftUI flag is what hid the idle chrome in the camera housing.
  /// Skip while `NSWindow.screen` is still nil — guessing from the cursor or
  /// main display is what parked the island on the wrong monitor.
  static func shouldReconcileFrameAfterSpaceChange(
    isVisible: Bool,
    showingAIConversation: Bool,
    islandModeChanged: Bool,
    frameChanged: Bool,
    barScreenMissing: Bool
  ) -> Bool {
    guard isVisible, !showingAIConversation, !barScreenMissing else { return false }
    return islandModeChanged || frameChanged
  }
}

/// Scale of the idle island. Retract animates to `retractedProgress`; anything
/// that cancels that animation without `orderOut` must land back on
/// `revealedProgress` or the chrome stays scaled into the camera housing.
enum FloatingBarNotchRevealPolicy {
  static let retractedProgress: CGFloat = 0.01
  static let revealedProgress: CGFloat = 1

  /// A retract whose `orderOut` never ran left the window on-screen at the
  /// collapsed scale. Restore full scale only when nothing else is still
  /// retracting or revealing it.
  static func shouldRestoreProgressAfterCancelledRetract(
    windowStillVisible: Bool,
    retractStillInFlight: Bool,
    revealStillInFlight: Bool
  ) -> Bool {
    windowStillVisible && !retractStillInFlight && !revealStillInFlight
  }
}
