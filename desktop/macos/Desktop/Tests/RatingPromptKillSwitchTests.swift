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

  func testLateLoadedDisableFlagHidesAVisiblePrompt() {
    let manager = RatingPromptManager.shared
    manager.resetForTesting()
    for _ in 0..<3 { manager.recordQuestionAsked() }
    XCTAssertTrue(manager.isVisible)

    manager.remoteDisableCheck = { true }
    manager.flagsDidUpdate()
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
