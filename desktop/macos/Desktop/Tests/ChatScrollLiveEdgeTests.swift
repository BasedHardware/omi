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
}
