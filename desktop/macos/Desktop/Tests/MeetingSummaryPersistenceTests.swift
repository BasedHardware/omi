@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class MeetingSummaryPersistenceTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "meeting-summary-persistence")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testProductionSQLiteRoundTripPersistsSectionsEvidenceAndOtherStructuredFields() async throws {
    let maybeDatabase = await RewindDatabase.shared.getDatabaseQueue()
    let database = try XCTUnwrap(maybeDatabase)
    let columns = try await database.read { db in try db.columns(in: "transcription_sessions") }
    XCTAssertTrue(columns.contains(where: { $0.name == "sectionsJson" }))

    let firstSection = SummarySection(
      heading: "Decisions",
      bodyMarkdown: "- Ship the design.",
      sourceSegmentIDs: ["segment-1"]
    )
    let first = makeConversation(
      updatedAt: 1_700_000_100,
      title: "Meeting",
      overview: "## Decisions\n\n- Ship the design.",
      sections: [firstSection],
      transcriptText: "The design is approved."
    )
    let sessionID = try await TranscriptionStorage.shared.syncServerConversation(first)

    let maybeCachedFirst = try await TranscriptionStorage.shared.getCachedConversation(id: first.id)
    let cachedFirst = try XCTUnwrap(maybeCachedFirst)
    XCTAssertEqual(cachedFirst.structured.sections, [firstSection])
    XCTAssertEqual(cachedFirst.structured.emoji, "📌")
    XCTAssertEqual(cachedFirst.structured.category, "planning")
    XCTAssertEqual(cachedFirst.structured.actionItems.map(\.description), ["David sends the resolution"])
    XCTAssertEqual(cachedFirst.structured.events.map(\.title), ["Review design"])
    XCTAssertEqual(cachedFirst.transcriptSegments.map(\.text), ["The design is approved."])

    let refreshedSection = SummarySection(
      heading: "Follow-up",
      bodyMarkdown: "David sends the resolution.",
      sourceSegmentIDs: ["segment-1"]
    )
    let refreshed = makeConversation(
      updatedAt: 1_700_000_200,
      title: "Meeting refreshed",
      overview: "Updated overview.",
      sections: [refreshedSection],
      transcriptText: "The design is approved and David owns the follow-up."
    )
    let refreshedSessionID = try await TranscriptionStorage.shared.syncServerConversation(refreshed)
    XCTAssertEqual(refreshedSessionID, sessionID)

    let maybeCachedRefreshed = try await TranscriptionStorage.shared.getCachedConversation(id: refreshed.id)
    let cachedRefreshed = try XCTUnwrap(maybeCachedRefreshed)
    XCTAssertEqual(cachedRefreshed.structured.title, "Meeting refreshed")
    XCTAssertEqual(cachedRefreshed.overview, "Updated overview.")
    XCTAssertEqual(cachedRefreshed.structured.sections, [refreshedSection])
    XCTAssertEqual(cachedRefreshed.structured.emoji, "📌")
    XCTAssertEqual(cachedRefreshed.structured.category, "planning")
    XCTAssertEqual(cachedRefreshed.structured.actionItems.map(\.description), ["David sends the resolution"])
    XCTAssertEqual(cachedRefreshed.structured.events.map(\.title), ["Review design"])
    XCTAssertEqual(
      cachedRefreshed.transcriptSegments.map(\.text),
      ["The design is approved and David owns the follow-up."]
    )

    let maybeRecord = try await TranscriptionStorage.shared.getSession(id: sessionID)
    let record = try XCTUnwrap(maybeRecord)
    XCTAssertEqual(record.starred, true)
    XCTAssertEqual(record.folderId, "meeting-folder")
  }

  func testOlderResponseCannotResurrectSectionsClearedBySummaryEdit() async throws {
    let edited = makeConversation(
      updatedAt: 1_700_000_200, title: "Meeting", overview: "User corrected summary.",
      sections: [], transcriptText: "The design is approved."
    )
    try await TranscriptionStorage.shared.syncServerConversation(edited)
    let stale = makeConversation(
      updatedAt: 1_700_000_100, title: "Meeting", overview: "Old generated summary.",
      sections: [
        SummarySection(heading: "Old evidence", bodyMarkdown: "Obsolete note.", sourceSegmentIDs: ["segment-1"])
      ],
      transcriptText: "The design is approved."
    )
    try await TranscriptionStorage.shared.syncServerConversation(stale)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: edited.id)
    XCTAssertEqual(cached?.structured.sections, [])
    XCTAssertEqual(cached?.overview, "User corrected summary.")
  }

  private func makeConversation(
    updatedAt: TimeInterval,
    title: String,
    overview: String,
    sections: [SummarySection],
    transcriptText: String
  ) -> ServerConversation {
    let timestamp = Date(timeIntervalSince1970: 1_700_000_000)
    let actionItem = ActionItem(
      description: "David sends the resolution",
      completed: false,
      deleted: false,
      sourceSegmentIDs: ["segment-1"]
    )
    let event = Event(
      .init(
        created: false, description_: "Review the approved design", duration: 30,
        start: ISO8601DateFormatter().string(from: timestamp.addingTimeInterval(3_600)),
        title: "Review design"
      ))
    let segment = TranscriptSegment(
      id: "segment-1",
      backendId: "segment-1",
      text: transcriptText,
      speaker: "SPEAKER_00",
      isUser: false,
      personId: nil,
      start: 0,
      end: 4
    )
    return ServerConversation(
      id: "meeting-summary-persistence-conversation",
      createdAt: timestamp,
      updatedAt: Date(timeIntervalSince1970: updatedAt),
      startedAt: timestamp,
      finishedAt: timestamp.addingTimeInterval(60),
      structured: Structured(
        title: title,
        overview: overview,
        emoji: "📌",
        category: "planning",
        actionItems: [actionItem],
        events: [event],
        sections: sections
      ),
      transcriptSegments: [segment],
      transcriptSegmentsIncluded: true,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: true,
      folderId: "meeting-folder",
      inputDeviceName: nil
    )
  }
}
