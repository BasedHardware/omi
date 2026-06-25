import XCTest
@testable import Omi_Computer

final class APIClientConversationCountTests: XCTestCase {
  func testConversationCountEndpointIncludesVisibleFilters() throws {
    let formatter = ISO8601DateFormatter()
    let start = try XCTUnwrap(formatter.date(from: "2026-06-01T00:00:00Z"))
    let end = try XCTUnwrap(formatter.date(from: "2026-06-02T00:00:00Z"))

    let endpoint = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      startDate: start,
      endDate: end,
      folderId: "folder-a",
      starred: true
    )

    XCTAssertTrue(endpoint.hasPrefix("v1/conversations/count?"))
    XCTAssertTrue(endpoint.contains("include_discarded=false"))
    XCTAssertTrue(endpoint.contains("statuses=completed,processing"))
    XCTAssertTrue(endpoint.contains("start_date=2026-06-01T00:00:00Z"))
    XCTAssertTrue(endpoint.contains("end_date=2026-06-02T00:00:00Z"))
    XCTAssertTrue(endpoint.contains("folder_id=folder-a"))
    XCTAssertTrue(endpoint.contains("starred=true"))
  }

  func testConversationCountEndpointDistinguishesFilterCacheKeys() {
    let unfiltered = APIClient.conversationsCountEndpoint(includeDiscarded: false)
    let folderFiltered = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      folderId: "folder-a"
    )
    let starredFalse = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      starred: false
    )

    XCTAssertNotEqual(unfiltered, folderFiltered)
    XCTAssertNotEqual(unfiltered, starredFalse)
    XCTAssertTrue(starredFalse.contains("starred=false"))
  }
}
