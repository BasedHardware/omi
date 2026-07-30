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
