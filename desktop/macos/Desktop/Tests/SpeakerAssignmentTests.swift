import XCTest

@testable import Omi_Computer

/// Speaker assignment regressions from the Beta "Couldn't assign this speaker"
/// report: the backend bulk-assign 404s for conversations that have not synced
/// yet (pending local sessions), and the client treated that as a hard failure
/// even though the finalization sync uploads every segment's person_id anyway.
final class SpeakerAssignmentTests: XCTestCase {

  /// 404 — the conversation is not on the backend yet — is the ONLY status that
  /// may keep the assignment local and report success.
  @MainActor
  func testOnlyMissingConversationFallsBackToLocalAssignment() {
    XCTAssertTrue(AppState.SpeakerAssignmentFallbackPolicy.keepsAssignmentLocally(statusCode: 404))
    for status in [400, 401, 403, 409, 422, 500, 502, 503] {
      XCTAssertFalse(
        AppState.SpeakerAssignmentFallbackPolicy.keepsAssignmentLocally(statusCode: status),
        "\(status) means the backend HAS the conversation and rejected the change — it must surface")
    }
  }

  /// The wire targets the detail sheet sends: backend ids when known, positional
  /// #index: fallbacks otherwise — the contract the backend's
  /// _resolve_bulk_segment_indices accepts for completed conversations.
  @MainActor
  func testAssignmentMetadataPrefersBackendIdsAndFallsBackToIndices() {
    let segments = [
      TranscriptSegment(
        id: "local-a", backendId: "backend-a", text: "a", speaker: "SPEAKER_01", isUser: false,
        personId: nil, start: 0, end: 1, translations: []),
      TranscriptSegment(
        id: "local-b", backendId: nil, text: "b", speaker: "SPEAKER_01", isUser: false,
        personId: nil, start: 1, end: 2, translations: []),
    ]
    let meta = ConversationDetailView.assignmentMetadata(for: [0, 1], in: segments)
    XCTAssertEqual(meta.targets, ["backend-a", "#index:1"])
    XCTAssertEqual(meta.backendIds, ["backend-a"])
    XCTAssertEqual(meta.fallbackOrders, [1])
  }

  /// The local half must consume BOTH target kinds the wire carries — backend
  /// ids and positional #index:N — because unsynced/legacy segments only have
  /// the positional form. Dropping them was the "assignment succeeded but did
  /// not survive reload" defect.
  func testTargetParsingSplitsIdsAndPositionalFallbacks() {
    let parsed = AppState.SpeakerAssignmentTargets.parse(
      ["backend-a", "#index:1", "#index:12", "not-an-index", "#index:x"])
    XCTAssertEqual(parsed.ids, ["backend-a", "not-an-index", "#index:x"])
    XCTAssertEqual(parsed.orders, [1, 12])
  }
}

/// The 404 fallback's durable half, exercised through the REAL SQLite write and
/// reload path (a per-test RewindDatabase, same seam as the finalization state
/// machine tests). The write must report whether it landed: when it returns 0
/// nothing durable holds the user's decision, and `assignSpeakerToSegments`
/// must not report success — the `try?` that swallowed this was the reviewed
/// defect.
final class SpeakerAssignmentPersistenceTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "speaker-assignment-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default
        .urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir {
      try? FileManager.default.removeItem(at: userDir)
    }
    try await super.tearDown()
  }

  func testPositionalAssignmentPersistsThroughSQLiteAndSurvivesReload() async throws {
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    for i in 0..<3 {
      try await TranscriptionStorage.shared.appendSegment(
        sessionId: sessionId, speaker: i, text: "segment \(i)",
        startTime: Double(i), endTime: Double(i) + 1)
    }
    try await TranscriptionStorage.shared.finishSession(id: sessionId)
    _ = try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId, backendId: "backend-conv-speaker")

    // The positional #index:N form the wire carries for segments without
    // backend ids — parsed to fallbackSegmentOrders by the production caller.
    let updated = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
      "backend-conv-speaker",
      segmentIds: [],
      fallbackSegmentOrders: [1],
      isUser: false,
      personId: "person-dana"
    )
    XCTAssertEqual(updated, 1, "exactly the targeted segment row must report as updated")

    // Reload path: close and reopen storage, then read back what a restart sees.
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()

    let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertEqual(segments.count, 3)
    XCTAssertNil(segments[0].personId)
    XCTAssertEqual(segments[1].personId, "person-dana", "the assignment must survive a storage reload")
    XCTAssertNil(segments[2].personId)
  }

  func testAssignmentAgainstUnknownConversationReportsNothingPersisted() async throws {
    let updated = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
      "no-such-conversation",
      segmentIds: ["seg-a"],
      fallbackSegmentOrders: [0],
      isUser: false,
      personId: "person-dana"
    )
    XCTAssertEqual(
      updated, 0,
      "no local session means nothing persisted — the caller must surface failure, not success")
  }
}
