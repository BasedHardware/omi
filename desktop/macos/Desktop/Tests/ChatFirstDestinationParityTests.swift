import XCTest

@testable import Omi_Computer

final class ChatFirstDestinationParityTests: XCTestCase {
  func testBrainMapSelectionSurvivesTheMemoryRouteTransition() {
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: .brainMap),
      .brainMap
    )
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: .conversations),
      .memories
    )
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .conversations, current: .brainMap),
      .conversations
    )
    XCTAssertNil(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .tasks, current: .brainMap)
    )
  }

}
