import XCTest

@testable import Omi_Computer

final class ContextVisitCoordinatorTests: XCTestCase {
  func testStateMachineAdvancesAndTakesExactlyOnce() {
    var state = ContextVisitStateMachine()
    let fence = ContextVisitFence(
      visitID: 7, contextGeneration: 2, poolEpoch: 3, bucketID: "b",
      startedAt: Date(timeIntervalSince1970: 1))
    state.begin(fence)
    XCTAssertEqual(state.generation, 2)
    XCTAssertEqual(state.takeActive(), fence)
    XCTAssertNil(state.takeActive())
  }
}
