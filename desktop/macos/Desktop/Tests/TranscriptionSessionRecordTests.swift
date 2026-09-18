@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class TranscriptionSessionRecordTests: XCTestCase {
  func testConversationRoleDefaultsToAmbientForBackwardCompatibility() {
    let record = TranscriptionSessionRecord(source: "desktop")

    XCTAssertEqual(record.conversationRole, .ambient)
  }

  func testConversationRoleCanBePersistedAsMeeting() {
    let record = TranscriptionSessionRecord(source: "desktop", conversationRole: .meeting)

    XCTAssertEqual(record.conversationRole, .meeting)
  }

  func testBackendIdentityExistsWhenBackendIdIsPresent() {
    let record = TranscriptionSessionRecord(
      source: "desktop",
      backendId: "conversation-a",
      backendSynced: false
    )

    XCTAssertTrue(record.hasSyncedBackendIdentity)
  }

  func testBackendIdentityExistsWhenBackendSyncedIsTrue() {
    let record = TranscriptionSessionRecord(
      source: "desktop",
      backendId: nil,
      backendSynced: true
    )

    XCTAssertTrue(record.hasSyncedBackendIdentity)
  }

  func testCompletionAcceptsEmptyBackendIdentity() {
    let record = TranscriptionSessionRecord(
      source: "desktop",
      backendId: nil,
      backendSynced: false
    )

    XCTAssertTrue(record.canAcceptCompletion(backendId: "conversation-a"))
  }

  func testCompletionAcceptsSameBackendId() {
    let record = TranscriptionSessionRecord(
      source: "desktop",
      backendId: "conversation-a",
      backendSynced: true
    )

    XCTAssertTrue(record.canAcceptCompletion(backendId: "conversation-a"))
  }

  func testCompletionRejectsConflictingBackendId() {
    let record = TranscriptionSessionRecord(
      source: "desktop",
      backendId: "conversation-a",
      backendSynced: true
    )

    XCTAssertFalse(record.canAcceptCompletion(backendId: "conversation-b"))
  }

  func testLocalListConversationMarksEmptySegmentsAsOmitted() {
    let record = TranscriptionSessionRecord(source: "desktop", backendId: "conversation-a")

    let conversation = record.toServerConversation(segments: [])

    XCTAssertNotNil(conversation)
    XCTAssertFalse(conversation!.transcriptSegmentsIncluded)
    XCTAssertEqual(conversation!.transcriptPresenceState, .omittedFromResponse)
    XCTAssertTrue(conversation!.shouldFetchDetailForTranscript)
  }

  func testLocalConversationWithSegmentsMarksTranscriptIncluded() {
    let record = TranscriptionSessionRecord(source: "desktop", backendId: "conversation-a")
    let segment = TranscriptionSegmentRecord(
      sessionId: 1,
      speaker: 0,
      text: "hello",
      startTime: 0,
      endTime: 1,
      segmentOrder: 0
    )

    let conversation = record.toServerConversation(segments: [segment])

    XCTAssertNotNil(conversation)
    XCTAssertTrue(conversation!.transcriptSegmentsIncluded)
    XCTAssertEqual(conversation!.transcriptPresenceState, .includedNonEmpty)
    XCTAssertFalse(conversation!.shouldFetchDetailForTranscript)
  }

  func testSummarySectionsSurviveLocalRecordRoundTripAndRefresh() throws {
    let firstSection = SummarySection(
      heading: "Decisions",
      bodyMarkdown: "- Ship the design.",
      sourceSegmentIDs: ["segment-1"]
    )
    let first = summaryConversation(
      overview: "## Decisions\n\n- Ship the design.",
      sections: [firstSection]
    )

    var record = TranscriptionSessionRecord.from(first)
    let cached = try XCTUnwrap(record.toServerConversation(segments: []))
    XCTAssertEqual(cached.structured.sections, [firstSection])

    let refreshedSection = SummarySection(
      heading: "Follow-up",
      bodyMarkdown: "David sends the resolution.",
      sourceSegmentIDs: ["segment-2"]
    )
    let refreshed = summaryConversation(
      overview: "Updated overview.",
      sections: [refreshedSection]
    )
    record.updateFrom(refreshed)

    let refreshedCache = try XCTUnwrap(record.toServerConversation(segments: []))
    XCTAssertEqual(refreshedCache.overview, "Updated overview.")
    XCTAssertEqual(refreshedCache.structured.sections, [refreshedSection])
    XCTAssertEqual(record.sectionsJson?.isEmpty, false)
  }

  func testSummarySectionsMigrationAddsColumnToLegacySessionTable() throws {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.create(table: "transcription_sessions") { table in
        table.autoIncrementedPrimaryKey("id")
      }
    }

    var migrator = DatabaseMigrator()
    RewindDatabase.registerConversationSummarySectionsMigration(on: &migrator)
    try migrator.migrate(queue)

    let columns = try queue.read { db in try db.columns(in: "transcription_sessions") }
    XCTAssertTrue(columns.contains(where: { $0.name == "sectionsJson" }))
  }

  private func summaryConversation(overview: String, sections: [SummarySection]) -> ServerConversation {
    ServerConversation(
      id: "summary-conversation",
      createdAt: Date(timeIntervalSince1970: 1_700_000_000),
      updatedAt: Date(timeIntervalSince1970: 1_700_000_100),
      startedAt: Date(timeIntervalSince1970: 1_700_000_000),
      finishedAt: Date(timeIntervalSince1970: 1_700_000_060),
      structured: Structured(
        title: "Meeting",
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: [],
        sections: sections
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}
