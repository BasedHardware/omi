import XCTest

@testable import Omi_Computer

/// Regression coverage: during Second Brain onboarding the live voice/screen demo
/// runs through the real floating bar, which dispatches its query with an EXPLICIT
/// `mainChatSurfaceReference()`. Surface selection used to honor a caller-supplied
/// surface before checking `isOnboarding`, so the demo turn ("what's on my screen
/// right now?") landed on the real default chat (and the backend) and reappeared in
/// the Chat tab after onboarding. Onboarding isolation must win over an explicit
/// surface so the turn routes to the throwaway `.onboarding()` surface instead.
final class OnboardingQuerySurfaceIsolationTests: XCTestCase {

  func testOnboardingIsolationBeatsAnExplicitSurface() {
    // The exact bug: a floating-bar send passes an explicit surfaceRef while onboarding.
    XCTAssertEqual(
      ChatProvider.querySurfaceChoice(hasSurfaceRef: true, isOnboarding: true, isFloating: true),
      .onboarding,
      "Onboarding must route to the isolated surface even when the caller supplies one")
    XCTAssertEqual(
      ChatProvider.querySurfaceChoice(hasSurfaceRef: true, isOnboarding: true, isFloating: false),
      .onboarding)
  }

  func testNonOnboardingHonorsExplicitSurface() {
    XCTAssertEqual(
      ChatProvider.querySurfaceChoice(hasSurfaceRef: true, isOnboarding: false, isFloating: true),
      .explicit,
      "Outside onboarding an explicit surface still wins over the floating default")
  }

  func testFloatingWithoutSurfaceUsesFloatingMain() {
    XCTAssertEqual(
      ChatProvider.querySurfaceChoice(hasSurfaceRef: false, isOnboarding: false, isFloating: true),
      .floatingMain)
  }

  func testDefaultWhenNothingSpecial() {
    XCTAssertEqual(
      ChatProvider.querySurfaceChoice(hasSurfaceRef: false, isOnboarding: false, isFloating: false),
      .defaultMain)
  }
}
