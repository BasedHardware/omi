import XCTest

@testable import Omi_Computer

/// Regression coverage for onboarding state leaking across accounts on the
/// same Mac: sign-out and onboarding-reset each kept a hand-maintained key
/// list, so keys present at only one site (e.g. hasSeenRewindIntro,
/// hasTriggeredAccessibility, the onboarding-chat exploration state) were
/// cleared at neither on the other path. A user who deleted their account and
/// re-onboarded saw the previous run's answers still filled in. Both sites now
/// iterate the shared `OnboardingFlow.persistedStateKeys` via
/// `clearPersistedState` and call `OnboardingChatPersistence.clear()`.
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
    // The keys sign-out historically missed, plus onboardingStep as the
    // canonical member.
    let required = [
      "onboardingStep",
      "hasSeenRewindIntro",
      "hasTriggeredAccessibility",
      "hasTriggeredBluetooth",
      // Second Brain onboarding keys — the redesign added these but left them out
      // of the shared list, leaking the prior user's resume step + role to the
      // next account on the same Mac.
      "sbOnboardingResumeStep",
      "onboardingRole",
    ]
    for key in required {
      XCTAssertTrue(
        OnboardingFlow.persistedStateKeys.contains(key),
        "\(key) is account-scoped and must be in the shared clearing list")
    }
  }

  /// An earlier version of this fix was silently reverted when a merge
  /// resolved AuthService.swift toward a wholesale reformat that still carried
  /// the old hand-rolled key list — and the suite stayed green because it only
  /// tested clearPersistedState in isolation. Behavioral coverage of signOut()
  /// would need a live Firebase session, so pin the call sites statically.
  func testSignOutClearsOnboardingStateViaSharedList() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // -> Tests/
      .deletingLastPathComponent()  // -> Desktop/
      .appendingPathComponent("Sources/AuthService.swift")
    // A merge reintroducing a hand-rolled removeObject list regresses silently.
    // omi-test-quality: source-inspection -- static contract: signOut() must use the shared clearing helpers
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    let signOutStart = try XCTUnwrap(source.range(of: "func signOut() async throws {"))
    let tail = source[signOutStart.lowerBound...]
    XCTAssertNotNil(
      tail.range(of: "OnboardingFlow.clearPersistedState()"),
      "signOut() must clear onboarding keys via the shared OnboardingFlow.persistedStateKeys list")
    XCTAssertNotNil(
      tail.range(of: "OnboardingChatPersistence.clear()"),
      "signOut() must clear onboarding chat/exploration state via OnboardingChatPersistence.clear()")
    XCTAssertNil(
      tail.range(of: "removeObject(forKey: \"onboardingStep\")"),
      "signOut() must not keep a hand-rolled onboarding key list alongside the shared helper")
  }

  /// Same static contract for the onboarding-reset site.
  func testResetOnboardingClearsStateViaSharedList() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()  // -> Tests/
      .deletingLastPathComponent()  // -> Desktop/
      .appendingPathComponent("Sources/AppState/AppState+SystemActions.swift")
    // omi-test-quality: source-inspection -- static contract: reset must use the shared clearing helpers
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    let resetStart = try XCTUnwrap(source.range(of: "func resetOnboardingAndRestart() {"))
    let tail = source[resetStart.lowerBound...]
    XCTAssertNotNil(
      tail.range(of: "OnboardingFlow.clearPersistedState()"),
      "resetOnboardingAndRestart() must clear onboarding keys via the shared list")
    XCTAssertNotNil(
      tail.range(of: "OnboardingChatPersistence.clear()"),
      "resetOnboardingAndRestart() must clear onboarding chat/exploration state")
    XCTAssertNil(
      tail.range(of: "removeObject(forKey: \"onboardingStep\")"),
      "resetOnboardingAndRestart() must not keep a hand-rolled onboarding key list")
    XCTAssertNil(
      tail.range(of: "deleteKnowledgeGraph"),
      "resetting onboarding must not delete the user's server knowledge graph")
    XCTAssertNil(
      tail.range(of: "KnowledgeGraphStorage.shared.clearAll"),
      "resetting onboarding must not clear the user's local knowledge graph")
  }
}
