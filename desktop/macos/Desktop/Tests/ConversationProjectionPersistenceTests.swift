@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ConversationProjectionPersistenceTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "projection-rendering")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testMigrationPreservesLegacyRowsWithNullAttribution() throws {
    let queue = try DatabaseQueue()
    try queue.write { db in
      try db.execute(sql: "CREATE TABLE transcription_sessions (id INTEGER PRIMARY KEY, title TEXT)")
      try db.execute(sql: "INSERT INTO transcription_sessions (id, title) VALUES (1, 'Legacy title')")
    }
    var migrator = DatabaseMigrator()
    RewindDatabase.registerConversationLocalSummaryMigration(on: &migrator)
    try migrator.migrate(queue)
    try queue.read { db in
      XCTAssertEqual(try String.fetchOne(db, sql: "SELECT title FROM transcription_sessions"), "Legacy title")
      XCTAssertNil(try String.fetchOne(db, sql: "SELECT localSummaryJson FROM transcription_sessions"))
    }
  }

  func testMinimumThenProjectionThenCloudAndOlderResponsesStayCoherent() async throws {
    let minimum = try ProjectionRenderingFixture.decode { $0.removeValue(forKey: "client_processing") }
    let sessionId = try await TranscriptionStorage.shared.syncServerConversation(minimum)
    let projected = try ProjectionRenderingFixture.decode { $0["updated_at"] = "2026-09-18T00:02:00Z" }
    try await TranscriptionStorage.shared.syncServerConversation(projected)
    var cached = try await TranscriptionStorage.shared.getCachedConversation(id: projected.id)
    XCTAssertEqual(cached?.structured, projected.structured)
    XCTAssertEqual(cached?.localSummary, projected.localSummary)
    let row = try await TranscriptionStorage.shared.getSession(id: sessionId)
    XCTAssertNil(row?.clientProcessingJson, "rendering must not create an upload/retry payload")

    try await TranscriptionStorage.shared.syncServerConversation(minimum)
    cached = try await TranscriptionStorage.shared.getCachedConversation(id: projected.id)
    XCTAssertEqual(cached?.structured, projected.structured)

    let cloud = try ProjectionRenderingFixture.decode {
      $0["updated_at"] = "2026-09-18T00:03:00Z"
      $0["structured"] = ["title": "Cloud", "overview": "Cloud overview"]
    }
    try await TranscriptionStorage.shared.syncServerConversation(cloud)
    try await TranscriptionStorage.shared.syncServerConversation(projected)
    let unversioned = try ProjectionRenderingFixture.decode { $0.removeValue(forKey: "updated_at") }
    try await TranscriptionStorage.shared.syncServerConversation(unversioned)
    cached = try await TranscriptionStorage.shared.getCachedConversation(id: projected.id)
    XCTAssertEqual(cached?.structured, cloud.structured)
    XCTAssertNil(cached?.localSummary)
  }

  func testNewerTranscriptInvalidatesCachedProjection() async throws {
    let projected = try ProjectionRenderingFixture.decode()
    try await TranscriptionStorage.shared.syncServerConversation(projected)
    let changed = try ProjectionRenderingFixture.decode {
      $0["updated_at"] = "2026-09-18T00:04:00Z"
      $0["transcript_segments"] = []
    }
    try await TranscriptionStorage.shared.syncServerConversation(changed)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: changed.id)
    XCTAssertEqual(cached?.title, "I agree")
    XCTAssertNil(cached?.localSummary)
  }

  func testNewListProjectionDoesNotDisplayPreviousRevisionsTranscript() async throws {
    let current = try ProjectionRenderingFixture.decode()
    try await TranscriptionStorage.shared.syncServerConversation(current)
    let nextList = try ProjectionRenderingFixture.decode {
      $0["updated_at"] = "2026-09-18T00:04:00Z"
      $0.removeValue(forKey: "transcript_segments")
      var projection = ProjectionRenderingFixture.object($0, "client_processing")
      projection["transcript_sha256"] = String(repeating: "a", count: 64)
      $0["client_processing"] = projection
    }
    try await TranscriptionStorage.shared.syncServerConversation(nextList)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: current.id)
    XCTAssertEqual(cached?.structured, nextList.structured)
    XCTAssertEqual(cached?.transcriptSegments.isEmpty, true)
    XCTAssertEqual(cached?.transcriptSegmentsIncluded, false)
  }

  func testOlderCloudCannotFillEmptyFieldsOfNewerProjection() async throws {
    let projected = try ProjectionRenderingFixture.decode {
      var projection = ProjectionRenderingFixture.object($0, "client_processing")
      projection["structure"] = ["title": "Local", "overview": "", "category": "other"]
      projection["action_items"] = []
      $0["client_processing"] = projection
    }
    try await TranscriptionStorage.shared.syncServerConversation(projected)
    let olderCloud = try ProjectionRenderingFixture.decode {
      $0["updated_at"] = "2026-09-18T00:00:00Z"
      $0["structured"] = ["title": "Cloud", "overview": "Older cloud text", "category": "work"]
    }
    try await TranscriptionStorage.shared.syncServerConversation(olderCloud)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: projected.id)
    XCTAssertEqual(cached?.structured, projected.structured)
    XCTAssertEqual(cached?.localSummary, projected.localSummary)
  }
}
