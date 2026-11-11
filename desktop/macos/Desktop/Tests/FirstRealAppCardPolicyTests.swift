import XCTest

@testable import Omi_Computer

/// The first-real-app card is a *one-shot*: it fires once per fresh install and
/// never again, and it must never fire for someone who was already using Omi
/// when the feature shipped. Both failure directions are expensive — a repeat
/// makes the notch read as an ad, and a card telling a two-year user that Omi
/// can see their screen teaches them to ignore the surface — so every gate has
/// a test here, where there is no clock and no window server.
final class FirstRealAppCardPolicyTests: XCTestCase {
  private func decide(
    state: FirstRealAppCardState? = .pending,
    bundleIdentifier: String? = "com.apple.Safari",
    appName: String? = "Safari",
    omiBundleIdentifier: String? = "com.omi.computer-macos",
    isOnboardingComplete: Bool = true,
    isSignedIn: Bool = true
  ) -> FirstRealAppCardPolicy.Decision {
    FirstRealAppCardPolicy.decide(
      FirstRealAppCardPolicy.Input(
        state: state,
        frontmostBundleIdentifier: bundleIdentifier,
        frontmostAppName: appName,
        omiBundleIdentifier: omiBundleIdentifier,
        isOnboardingComplete: isOnboardingComplete,
        isSignedIn: isSignedIn
      )
    )
  }

  func testFiresForAFreshInstallOnARealApp() {
    XCTAssertEqual(decide(), .fire)
  }

  func testConsumedNeverFiresAgain() {
    XCTAssertEqual(decide(state: .consumed), .suppress(.alreadyConsumed))
  }

  /// Consumed outranks every other reason, so the steady state — every app
  /// switch for the rest of the install's life — settles on one comparison.
  func testConsumedOutranksEveryOtherSuppression() {
    XCTAssertEqual(
      decide(
        state: .consumed,
        bundleIdentifier: "com.omi.computer-macos",
        appName: nil,
        isOnboardingComplete: false,
        isSignedIn: false
      ),
      .suppress(.alreadyConsumed)
    )
  }

  func testNoRecordedVerdictDoesNotFire() {
    XCTAssertEqual(decide(state: nil), .suppress(.gateNotRun))
  }

  func testOnboardingStillRunningDoesNotFire() {
    XCTAssertEqual(decide(isOnboardingComplete: false), .suppress(.onboardingIncomplete))
  }

  /// The defect this whole feature exists to avoid: Omi describing its own
  /// window because it was frontmost when the user asked about "the screen".
  func testOmiItselfIsNotARealApp() {
    XCTAssertEqual(
      decide(bundleIdentifier: "com.omi.computer-macos", appName: "Omi"),
      .suppress(.omiFrontmost)
    )
  }

  func testSystemUIIsNotARealApp() {
    for identifier in FirstRealAppCardPolicy.excludedBundleIdentifiers {
      XCTAssertEqual(
        decide(bundleIdentifier: identifier, appName: "System"),
        .suppress(.systemUI),
        "\(identifier) should not count as an app the user opened"
      )
    }
  }

  /// System Settings owns the front during a permission grant, which is exactly
  /// where onboarding sends the user.
  func testSystemSettingsIsExcluded() {
    XCTAssertTrue(
      FirstRealAppCardPolicy.excludedBundleIdentifiers.contains("com.apple.systempreferences"))
    XCTAssertTrue(FirstRealAppCardPolicy.excludedBundleIdentifiers.contains("com.apple.loginwindow"))
    XCTAssertTrue(FirstRealAppCardPolicy.excludedBundleIdentifiers.contains("com.apple.dock"))
  }

  func testAnAppWithNoNameCannotBeNamedInTheCopy() {
    XCTAssertEqual(decide(appName: nil), .suppress(.unknownApp))
    XCTAssertEqual(decide(appName: ""), .suppress(.unknownApp))
    XCTAssertEqual(decide(bundleIdentifier: nil), .suppress(.unknownApp))
  }

  func testSignedOutDoesNotFire() {
    XCTAssertEqual(decide(isSignedIn: false), .suppress(.notSignedIn))
  }

  // MARK: - Install gate

  func testInstallGateRetiresTheCardForAnAlreadyOnboardedUser() {
    XCTAssertEqual(
      FirstRealAppCardPolicy.installGate(state: nil, hasCompletedOnboarding: true),
      .record(.consumed)
    )
  }

  func testInstallGateArmsAFreshInstall() {
    XCTAssertEqual(
      FirstRealAppCardPolicy.installGate(state: nil, hasCompletedOnboarding: false),
      .record(.pending)
    )
  }

  /// The gate is a true one-shot. Without the recorded `pending`, a fresh user
  /// who quit mid-onboarding would come back with onboarding complete and be
  /// mistaken for an existing user — silently losing the card forever.
  func testInstallGateNeverReconsidersARecordedVerdict() {
    XCTAssertEqual(
      FirstRealAppCardPolicy.installGate(state: .pending, hasCompletedOnboarding: true),
      .alreadyRecorded
    )
    XCTAssertEqual(
      FirstRealAppCardPolicy.installGate(state: .consumed, hasCompletedOnboarding: false),
      .alreadyRecorded
    )
  }

  // MARK: - Copy

  func testTitleNamesTheApp() {
    XCTAssertEqual(FirstRealAppCardPolicy.title(appName: "Figma"), "I can see Figma")
  }

  /// The body's job is push-to-talk discovery, so it must name the chord the
  /// user actually has — not a default the app assumes.
  func testBodyUsesTheRealChordTokens() {
    XCTAssertEqual(
      FirstRealAppCardPolicy.body(pttChordTokens: ["⌃", "⌥", "Space"]),
      "Hold ⌃ ⌥ Space and ask me anything about it — or tap to type."
    )
    XCTAssertEqual(
      FirstRealAppCardPolicy.body(pttChordTokens: ["Right ⌘"]),
      "Hold Right ⌘ and ask me anything about it — or tap to type."
    )
  }

  /// A user who cleared the chord must not be told to hold nothing.
  func testEmptyChordFallsBackToTapOnlyCopy() {
    XCTAssertEqual(
      FirstRealAppCardPolicy.body(pttChordTokens: []),
      "Tap to ask me anything about it."
    )
    XCTAssertEqual(
      FirstRealAppCardPolicy.body(pttChordTokens: ["", "  "]),
      "Tap to ask me anything about it."
    )
  }
}
