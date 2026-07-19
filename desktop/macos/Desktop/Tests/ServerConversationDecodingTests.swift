import XCTest

@testable import Omi_Computer

final class ServerConversationDecodingTests: XCTestCase {
  private func decodeConversation(_ extraFields: String) throws -> ServerConversation {
    let json = """
      {
        "id": "conversation-1",
        "created_at": "2026-06-25T10:00:00Z",
        "started_at": "2026-06-25T10:00:00Z",
        "finished_at": "2026-06-25T10:01:00Z",
        "structured": {
          "title": "Test conversation",
          "overview": "Overview",
          "emoji": "🧪",
          "category": "other",
          "action_items": [],
          "events": []
        },
        "status": "completed",
        "source": "desktop",
        "discarded": false,
        "deleted": false,
        "starred": false,
        "deferred": false
        \(extraFields)
      }
      """
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ServerConversation.self, from: Data(json.utf8))
  }

  private func decodeSearchResult(_ itemFields: String) throws -> ConversationSearchResult {
    let json = """
      {
        "items": [
          {
            "id": "conversation-1",
            "created_at": "2026-06-25T10:00:00+00:00",
            "started_at": null,
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
            "discarded": false,
            "starred": false,
            "deferred": false
            \(itemFields)
          }
        ],
        "current_page": 1,
        "total_pages": 1,
        "per_page": 50
      }
      """
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ConversationSearchResult.self, from: Data(json.utf8))
  }

  func testOmittedTranscriptSegmentsAreMarkedOmitted() throws {
    let conversation = try decodeConversation("")

    XCTAssertTrue(conversation.transcriptSegments.isEmpty)
    XCTAssertFalse(conversation.transcriptSegmentsIncluded)
    XCTAssertEqual(conversation.transcriptPresenceState, .omittedFromResponse)
    XCTAssertTrue(conversation.shouldFetchDetailForTranscript)
  }

  func testExplicitEmptyTranscriptIsIncludedEmpty() throws {
    let conversation = try decodeConversation(",\n\"transcript_segments\": []")

    XCTAssertTrue(conversation.transcriptSegmentsIncluded)
    XCTAssertTrue(conversation.transcriptSegments.isEmpty)
    XCTAssertEqual(conversation.transcriptPresenceState, .includedEmpty)
    XCTAssertFalse(conversation.shouldFetchDetailForTranscript)
  }

  func testLockedOmittedTranscriptIsRedactedAndDoesNotFetchDetail() throws {
    let conversation = try decodeConversation(",\n\"is_locked\": true")

    XCTAssertFalse(conversation.transcriptSegmentsIncluded)
    XCTAssertTrue(conversation.transcriptSegments.isEmpty)
    XCTAssertEqual(conversation.transcriptPresenceState, .lockedOrRedacted)
    XCTAssertFalse(conversation.shouldFetchDetailForTranscript)
  }

  func testLockedExplicitEmptyTranscriptIsRedacted() throws {
    let conversation = try decodeConversation(",\n\"is_locked\": true,\n\"transcript_segments\": []")

    XCTAssertTrue(conversation.transcriptSegmentsIncluded)
    XCTAssertTrue(conversation.transcriptSegments.isEmpty)
    XCTAssertEqual(conversation.transcriptPresenceState, .lockedOrRedacted)
    XCTAssertFalse(conversation.shouldFetchDetailForTranscript)
  }

  func testIncludedTranscriptIsIncludedNonEmpty() throws {
    let conversation = try decodeConversation(
      ",\n\"transcript_segments\": [{\"id\": \"segment-1\", \"text\": \"hello\", \"speaker\": \"speaker_0\", \"is_user\": true, \"start\": 0, \"end\": 1}]"
    )

    XCTAssertTrue(conversation.transcriptSegmentsIncluded)
    XCTAssertEqual(conversation.transcriptSegments.count, 1)
    XCTAssertEqual(conversation.transcriptPresenceState, .includedNonEmpty)
    XCTAssertFalse(conversation.shouldFetchDetailForTranscript)
  }

  func testNullTranscriptSegmentsArePresentButEmpty() throws {
    let conversation = try decodeConversation(",\n\"transcript_segments\": null")

    XCTAssertTrue(conversation.transcriptSegmentsIncluded)
    XCTAssertTrue(conversation.transcriptSegments.isEmpty)
    XCTAssertEqual(conversation.transcriptPresenceState, .includedEmpty)
    XCTAssertFalse(conversation.shouldFetchDetailForTranscript)
  }

  func testConversationSearchResultDecodesCanonicalListRowWithOmittedTranscript() throws {
    let result = try decodeSearchResult("")

    XCTAssertEqual(result.items.count, 1)
    XCTAssertEqual(result.items[0].title, "Search hit")
    XCTAssertFalse(result.items[0].transcriptSegmentsIncluded)
    XCTAssertEqual(result.items[0].transcriptPresenceState, .omittedFromResponse)
    XCTAssertTrue(result.items[0].shouldFetchDetailForTranscript)
  }

  func testConversationSearchResultRejectsRawPartialTypesenseTranscriptShape() throws {
    XCTAssertThrowsError(
      try decodeSearchResult(
        ",\n\"transcript_segments\": [{\"person_id\": \"person-1\"}]"
      )
    )
  }

  func testLockStateParticipatesInConversationEquality() throws {
    let unlocked = try decodeConversation(",\n\"is_locked\": false,\n\"transcript_segments\": []")
    let locked = try decodeConversation(",\n\"is_locked\": true,\n\"transcript_segments\": []")

    XCTAssertNotEqual(unlocked, locked)
  }
}
