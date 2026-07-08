import XCTest
@testable import Omi_Computer

final class APIClientConversationCountTests: XCTestCase {
  func testCreateConversationFromSegmentsResponseDefaultsOptionalFields() throws {
    let response = try JSONDecoder().decode(
      APIClient.CreateConversationFromSegmentsResponse.self,
      from: Data(#"{"id":"conversation-1"}"#.utf8)
    )

    XCTAssertEqual(response.id, "conversation-1")
    XCTAssertEqual(response.status, "processing")
    XCTAssertFalse(response.discarded)
  }

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

  func testConversationFilterQueryItemsAreSharedByListAndCount() throws {
    let formatter = ISO8601DateFormatter()
    let start = try XCTUnwrap(formatter.date(from: "2026-06-01T00:00:00Z"))

    let queryItems = APIClient.conversationFilterQueryItems(
      statuses: [.completed],
      includeDiscarded: true,
      startDate: start,
      folderId: "folder-a",
      starred: false
    )

    XCTAssertEqual(queryItems, [
      "include_discarded=true",
      "statuses=completed",
      "start_date=2026-06-01T00:00:00Z",
      "folder_id=folder-a",
      "starred=false",
    ])
  }

  func testConversationMutationsInvalidateCountCache() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    let sourceURL = testFile
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/APIClient.swift")
    let source = try String(contentsOf: sourceURL)

    for method in [
      "deleteConversation(id:",
      "setConversationStarred(id:",
      "mergeConversations(ids:",
      "deleteFolder(id:",
      "moveConversationToFolder(conversationId:",
      "createConversationFromSegments(_ request:",
    ] {
      guard let methodRange = source.range(of: method) else {
        XCTFail("Missing method \(method)")
        continue
      }
      let suffix = source[methodRange.upperBound...]
      guard let nextMethodRange = suffix.range(of: "\n  ///") ?? suffix.range(of: "\n}") else {
        XCTFail("Could not find end of method \(method)")
        continue
      }
      let methodBody = suffix[..<nextMethodRange.lowerBound]
      XCTAssertTrue(
        methodBody.contains("invalidateConversationsCountCache()"),
        "\(method) should clear the filtered count cache after mutating conversations or folder membership")
    }
  }
}
