import Foundation
import XCTest

@testable import Omi_Computer

final class ConversationSearchResultFilterTests: XCTestCase {
  func testApplyUsesTheSameAndPredicateAsTheListQuery() throws {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
    let conversations = [
      try decodeConversation(
        id: "keep",
        createdAt: "2026-06-25T10:00:00Z",
        startedAt: "2026-06-25T10:01:00Z",
        starred: true,
        folderId: "work"
      ),
      try decodeConversation(
        id: "wrong-folder",
        createdAt: "2026-06-25T10:00:00Z",
        startedAt: "2026-06-25T10:01:00Z",
        starred: true,
        folderId: "personal"
      ),
      try decodeConversation(
        id: "wrong-date",
        createdAt: "2026-06-24T10:00:00Z",
        startedAt: "2026-06-24T10:01:00Z",
        starred: true,
        folderId: "work"
      ),
      try decodeConversation(
        id: "not-starred",
        createdAt: "2026-06-25T10:00:00Z",
        startedAt: "2026-06-25T10:01:00Z",
        starred: false,
        folderId: "work"
      ),
    ]

    let selectedDate = try XCTUnwrap(
      ISO8601DateFormatter().date(from: "2026-06-25T00:00:00Z")
    )
    let filtered = ConversationSearchResultFilter.apply(
      conversations,
      starredOnly: true,
      date: selectedDate,
      folderId: "work",
      calendar: calendar
    )

    XCTAssertEqual(filtered.map(\.id), ["keep"])
  }

  func testApplyPreservesAllTextSearchHitsWhenNoRefinementsAreActive() throws {
    let conversations = [
      try decodeConversation(
        id: "first",
        createdAt: "2026-06-25T10:00:00Z",
        startedAt: nil,
        starred: false,
        folderId: nil
      ),
      try decodeConversation(
        id: "second",
        createdAt: "2026-06-24T10:00:00Z",
        startedAt: nil,
        starred: true,
        folderId: "work"
      ),
    ]

    let filtered = ConversationSearchResultFilter.apply(
      conversations,
      starredOnly: false,
      date: nil,
      folderId: nil
    )

    XCTAssertEqual(filtered, conversations)
  }

  private func decodeConversation(
    id: String,
    createdAt: String,
    startedAt: String?,
    starred: Bool,
    folderId: String?
  ) throws -> ServerConversation {
    let startedAtJSON = startedAt.map { "\"\($0)\"" } ?? "null"
    let folderIdJSON = folderId.map { "\"\($0)\"" } ?? "null"
    let json = """
      {
        "id": "\(id)",
        "created_at": "\(createdAt)",
        "started_at": \(startedAtJSON),
        "finished_at": null,
        "structured": {
          "title": "Search hit",
          "overview": "Overview",
          "emoji": "💬",
          "category": "other",
          "action_items": [],
          "events": []
        },
        "status": "completed",
        "source": "desktop",
        "discarded": false,
        "deleted": false,
        "starred": \(starred),
        "folder_id": \(folderIdJSON),
        "deferred": false
      }
      """
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ServerConversation.self, from: Data(json.utf8))
  }
}
