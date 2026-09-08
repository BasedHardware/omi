import XCTest

@testable import Omi_Computer

final class APIClientDatedActionItemsTests: XCTestCase {
  func testActionItemsListHardMaxMatchesBackendCap() {
    XCTAssertEqual(APIClient.actionItemsListHardMax, 2000)
  }

  func testNoDeadlineBoundaryOffsetRejectsOverflow() async {
    do {
      _ = try await APIClient.shared.getNoDeadlineActionItems(
        limit: 1,
        offset: 1,
        datedBoundaryOffset: Int.max,
        completed: false
      )
      XCTFail("Expected invalid offset overflow to throw")
    } catch {
      XCTAssertTrue(error is APIError)
    }
  }
}
