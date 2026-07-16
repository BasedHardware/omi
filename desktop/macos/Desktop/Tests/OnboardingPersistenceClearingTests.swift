import XCTest

@testable import Omi_Computer

/// Regression coverage for onboarding state leaking across accounts on the
/// same Mac: sign-out and onboarding-reset each kept a hand-maintained key
/// list, so newly added keys (furthest step, how-did-you-hear, goal draft)
/// were cleared at neither site. Both sites now iterate the shared
/// `OnboardingFlow.persistedStateKeys` via `clearPersistedState`.
final class OnboardingPersistenceClearingTests: XCTestCase {
  func testClearPersistedStateRemovesEverySharedKey() throws {
    let suiteName = "OnboardingPersistenceClearingTests-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    for key in OnboardingFlow.persistedStateKeys {
      defaults.set("leaked-from-previous-account", forKey: key)
    }

    OnboardingFlow.clearPersistedState(in: defaults)

    for key in OnboardingFlow.persistedStateKeys {
      XCTAssertNil(defaults.object(forKey: key), "\(key) must be cleared by clearPersistedState")
    }
  }

  func testSharedListCoversAccountScopedOnboardingKeys() {
    // The three keys that leaked, plus onboardingStep as the canonical member.
    let required = [
      "onboardingStep",
      "onboardingFurthestStep",
      "onboardingHowDidYouHearSource",
      "onboardingGoalDraft",
    ]
    for key in required {
      XCTAssertTrue(
        OnboardingFlow.persistedStateKeys.contains(key),
        "\(key) is account-scoped and must be in the shared clearing list")
    }
  }
}
