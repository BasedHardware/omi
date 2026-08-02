import XCTest

@testable import Omi_Computer

final class ChatScrollLiveEdgeTests: XCTestCase {
  func testReaderScrollAwayFromLiveEdgeIsNotTreatedAsFollowing() {
    XCTAssertFalse(
      ChatScrollLiveEdge.isAtBottom(visibleMaxY: 950, documentHeight: 1_000),
      "A reader who scrolls up by 50 points must not be pulled down by streaming output."
    )
  }

  func testExactLiveEdgeResumesFollowing() {
    XCTAssertTrue(ChatScrollLiveEdge.isAtBottom(visibleMaxY: 1_000, documentHeight: 1_000))
  }

  func testStaleLiveEdgeSampleCannotResumeFollowingDuringGesture() {
    XCTAssertFalse(
      ChatScrollLiveEdge.canResumeFollowing(isAtBottom: true, userIsScrolling: true),
      "A passive live-edge sample must not take ownership from an active user gesture."
    )
    XCTAssertTrue(
      ChatScrollLiveEdge.canResumeFollowing(isAtBottom: true, userIsScrolling: false)
    )
    XCTAssertFalse(
      ChatScrollLiveEdge.canResumeFollowing(isAtBottom: false, userIsScrolling: false)
    )
  }

  func testExplicitJumpSettlesAfterTheNextLayoutTurn() {
    XCTAssertEqual(ChatScrollLiveEdge.explicitJumpSettlingDelay, 0.05)
  }

  func testInitialRestoreSettlesAcrossMultipleLayoutTurns() {
    XCTAssertEqual(ChatScrollLiveEdge.initialRestoreSettlingDelays, [0.05, 0.2, 0.5])
  }
}
