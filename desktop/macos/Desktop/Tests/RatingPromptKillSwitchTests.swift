import XCTest

@testable import Omi_Computer

/// The remote kill switch must not wait for the user's next question: a flag
/// payload arriving AFTER the prompt is on screen (late preload, or a
/// mid-session reload delivering the disable) hides it immediately.
@MainActor
final class RatingPromptKillSwitchTests: XCTestCase {
  override func tearDown() async throws {
    let manager = RatingPromptManager.shared
    manager.remoteDisableCheck = {
      PostHogManager.shared.isFeatureEnabled(RatingPromptPolicy.killSwitchFlag)
    }
    manager.resetForTesting()
  }

  func testLateLoadedDisableFlagHidesAVisiblePrompt() async {
    let manager = RatingPromptManager.shared
    manager.resetForTesting()
    for _ in 0..<3 { manager.recordQuestionAsked() }
    XCTAssertTrue(manager.isVisible)

    // Drive the REAL boundary: the exact Notification.Name the PostHog SDK
    // posts after a flag payload lands (PostHogRemoteConfig ->
    // NotificationCenter.post(PostHogSDK.didReceiveFeatureFlags)) — the same
    // compile-checked symbol the manager's observer subscribes to.
    manager.remoteDisableCheck = { true }
    NotificationCenter.default.post(name: PostHogManager.featureFlagsDidLoad, object: nil)
    // The observer hops through a MainActor Task; bounded yields let it run
    // without a wall-clock wait.
    for _ in 0..<100 where manager.isVisible {
      await Task.yield()
    }
    XCTAssertFalse(manager.isVisible)
  }

  func testFlagPayloadWithoutTheDisableKeepsThePromptVisible() {
    let manager = RatingPromptManager.shared
    manager.resetForTesting()
    for _ in 0..<3 { manager.recordQuestionAsked() }

    manager.remoteDisableCheck = { false }
    manager.flagsDidUpdate()
    XCTAssertTrue(manager.isVisible)
  }
}
