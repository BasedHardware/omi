import XCTest

@testable import Omi_Computer

final class ChatFirstPromptMaterializationCoordinatorTests: XCTestCase {
  func testPolicyRequiresTranscriptReadinessAndDebouncesForegroundFlapping() {
    let now = Date(timeIntervalSinceReferenceDate: 10_000)

    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        transcriptFirstPageLoaded: false,
        isRunning: false,
        lastAttemptAt: nil,
        now: now
      )
    )
    XCTAssertTrue(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: nil,
        now: now
      )
    )
    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        transcriptFirstPageLoaded: true,
        isRunning: true,
        lastAttemptAt: now,
        now: now.addingTimeInterval(120)
      )
    )
    XCTAssertFalse(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: now,
        now: now.addingTimeInterval(59)
      )
    )
    XCTAssertTrue(
      ChatFirstPromptMaterializationPolicy.shouldStart(
        transcriptFirstPageLoaded: true,
        isRunning: false,
        lastAttemptAt: now,
        now: now.addingTimeInterval(60)
      )
    )
  }
}
