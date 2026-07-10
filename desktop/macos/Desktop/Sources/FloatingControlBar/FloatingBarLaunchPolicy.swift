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
