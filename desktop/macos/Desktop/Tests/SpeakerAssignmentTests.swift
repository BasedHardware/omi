import XCTest

@testable import Omi_Computer

/// Speaker assignment regressions from the Beta "Couldn't assign this speaker"
/// report: the backend bulk-assign 404s for conversations that have not synced
/// yet (pending local sessions), and the client treated that as a hard failure
/// even though the finalization sync uploads every segment's person_id anyway.
final class SpeakerAssignmentTests: XCTestCase {

  @MainActor
  private func conversationForOptimisticTest() -> ServerConversation {
    ServerConversation(
      id: "optimistic-test", createdAt: Date(), startedAt: nil, finishedAt: nil,
      structured: Structured(title: "Test", overview: "", emoji: "", category: "other", actionItems: [], events: []),
      transcriptSegments: [
        TranscriptSegment(
          id: "local", backendId: "backend", text: "Hello", speaker: "SPEAKER_01",
          isUser: false, personId: nil, start: 0, end: 1, translations: [])
      ], transcriptSegmentsIncluded: true, geolocation: nil, photos: [], appsResults: [],
      source: nil, language: nil, status: .completed, discarded: false, deleted: false,
      isLocked: false, starred: false, folderId: nil, inputDeviceName: nil)
  }

  @MainActor
  func testOptimisticAssignmentAppliesToDetailAndListAndRollsBack() throws {
    let detail = conversationForOptimisticTest()
    let list = detail
    let detailApplied = AppState.assigningSpeaker(detail, targets: ["backend"], personId: "alice", isUser: false)
    let listApplied = AppState.assigningSpeaker(list, targets: ["backend"], personId: "alice", isUser: false)
    XCTAssertEqual(detailApplied.transcriptSegments[0].personId, "alice")
    XCTAssertEqual(listApplied.transcriptSegments[0].personId, "alice")
    let detailRestored = try XCTUnwrap(
      SpeakerAssignmentSnapshot.rollback(
        current: detailApplied, original: detail, targets: ["backend"],
        assignedPersonId: "alice", assignedIsUser: false, generation: 2, currentGeneration: 2))
    let listRestored = try XCTUnwrap(
      SpeakerAssignmentSnapshot.rollback(
        current: listApplied, original: list, targets: ["backend"],
        assignedPersonId: "alice", assignedIsUser: false, generation: 2, currentGeneration: 2))
    XCTAssertNil(detailRestored.transcriptSegments[0].personId)
    XCTAssertNil(listRestored.transcriptSegments[0].personId)
  }

  @MainActor
  func testStaleCompletionCannotRollbackNewEditOrReload() {
    let original = conversationForOptimisticTest()
    let newer = AppState.assigningSpeaker(original, targets: ["backend"], personId: "bob", isUser: false)
    XCTAssertNil(
      SpeakerAssignmentSnapshot.rollback(
        current: newer, original: original, targets: ["backend"],
        assignedPersonId: "alice", assignedIsUser: false, generation: 1, currentGeneration: 2))
    XCTAssertNil(
      SpeakerAssignmentSnapshot.rollback(
        current: newer, original: original, targets: ["backend"],
        assignedPersonId: "alice", assignedIsUser: false, generation: 2, currentGeneration: 2))
  }

  @MainActor
  func testNewPersonReconcilesTemporaryIdentityBeforePersistence() {
    let original = conversationForOptimisticTest()
    let temporary = AppState.assigningSpeaker(
      original, targets: ["#index:0"], personId: "optimistic-person:1", isUser: false)
    XCTAssertEqual(temporary.transcriptSegments[0].personId, "optimistic-person:1")
    let reconciled = AppState.assigningSpeaker(
      temporary, targets: ["#index:0"], personId: "real-person", isUser: false)
    XCTAssertEqual(reconciled.transcriptSegments[0].personId, "real-person")
    XCTAssertEqual(reconciled.transcriptSegments[0].text, original.transcriptSegments[0].text)
  }

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

  /// Unassign is `personId: nil, isUser: false` through the same write: it must clear both a named
  /// person and a "You" back to an anonymous speaker, and the clear must survive a reload.
  func testUnassignClearsPersonAndUserThroughSQLite() async throws {
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    for i in 0..<2 {
      try await TranscriptionStorage.shared.appendSegment(
        sessionId: sessionId, speaker: i, text: "segment \(i)",
        startTime: Double(i), endTime: Double(i) + 1)
    }
    try await TranscriptionStorage.shared.finishSession(id: sessionId)
    _ = try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId, backendId: "backend-conv-unassign")
    _ = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
      "backend-conv-unassign", segmentIds: [], fallbackSegmentOrders: [0], isUser: false, personId: "person-dana")
    _ = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
      "backend-conv-unassign", segmentIds: [], fallbackSegmentOrders: [1], isUser: true, personId: nil)

    let cleared = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
      "backend-conv-unassign", segmentIds: [], fallbackSegmentOrders: [0, 1], isUser: false, personId: nil)
    XCTAssertEqual(cleared, 2)

    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()

    let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertEqual(segments.map(\.personId), [nil, nil])
    XCTAssertEqual(segments.map(\.isUser), [false, false])
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

  func testLiveSpeakerAssignmentPersistsAndSurvivesReload() async throws {
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    for i in 0..<3 {
      try await TranscriptionStorage.shared.appendSegment(
        sessionId: sessionId, speaker: i == 1 ? 0 : 1, text: "segment \(i)",
        startTime: Double(i), endTime: Double(i) + 1)
    }

    let updated = try await TranscriptionStorage.shared.updateLiveSpeakerAssignment(
      sessionId: sessionId, speakerId: 1, personId: "person-live")
    XCTAssertEqual(updated, 2, "every segment row for the speaker must report as updated")
    let missed = try await TranscriptionStorage.shared.updateLiveSpeakerAssignment(
      sessionId: sessionId, speakerId: 7, personId: "person-live")
    XCTAssertEqual(
      missed, 0, "a speaker with no rows must report 0 so orchestration rejects the save")

    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()

    let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertEqual(segments.map(\.personId), ["person-live", nil, "person-live"])
    XCTAssertEqual(
      segments.map(\.isUser), [false, false, false],
      "person assignment clears isUser — the speaker is no longer 'You'")
  }
}

final class LiveSpeakerAssignmentOrchestrationTests: XCTestCase {
  final class EventLog: @unchecked Sendable {
    private(set) var values = [String]()
    func append(_ event: String) { values.append(event) }
  }

  final class CurrentFlag: @unchecked Sendable {
    var value = true
  }

  @MainActor
  private func runAssignment(
    context: AppState.LiveSpeakerAssignment.Context,
    isCurrent: @escaping @MainActor () -> Bool = { true },
    persistBackend: ((String) async throws -> [String])? = nil,
    persistLocal: ((Int64) async throws -> Int)? = nil,
    events: EventLog,
    flushFlip: CurrentFlag? = nil
  ) async -> Bool {
    await AppState.LiveSpeakerAssignment.run(
      context: context,
      isCurrent: isCurrent,
      persistBackend: { backendId in
        events.append("rest:\(backendId)")
        return try await (persistBackend ?? { _ in [] })(backendId)
      },
      persistLocal: { sessionId in
        events.append("local:\(sessionId)")
        return try await (persistLocal ?? { _ in 0 })(sessionId)
      },
      flushPendingWrites: {
        events.append("flush")
        flushFlip?.value = false
      },
      notifySocket: { ids in events.append("notify:\(ids.joined(separator: ","))") },
      applyAssignment: { events.append("apply") }
    )
  }

  @MainActor
  func testRestSuccessNotifiesSocketThenAppliesMap() async {
    let events = EventLog()
    let saved = await runAssignment(
      context: .init(backendConversationId: "conv-1", sessionId: nil),
      persistBackend: { _ in ["seg-1", "seg-2"] },
      events: events
    )
    XCTAssertTrue(saved)
    XCTAssertEqual(
      events.values, ["rest:conv-1", "notify:seg-1,seg-2", "apply"],
      "the socket wake-up must follow the REST acknowledgment, never precede it")
  }

  @MainActor
  func testCloudSaveFailureReturnsFalseWithoutLocalAcknowledgment() async {
    let events = EventLog()
    let saved = await runAssignment(
      context: .init(backendConversationId: "conv-1", sessionId: 9),
      persistBackend: { _ in throw APIError.httpError(statusCode: 500) },
      events: events
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(
      events.values, ["rest:conv-1"],
      "a rejected REST save must not touch SQLite, the socket, or the speaker map")
  }

  @MainActor
  func testStaleRestCompletionSuppressesNotifyAndApply() async {
    let events = EventLog()
    let stillCurrent = CurrentFlag()
    let saved = await runAssignment(
      context: .init(backendConversationId: "conv-1", sessionId: 9),
      isCurrent: { stillCurrent.value },
      persistBackend: { _ in
        stillCurrent.value = false
        return ["seg-1"]
      },
      persistLocal: { _ in 1 },
      events: events
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(
      events.values, ["rest:conv-1"],
      "a completion that goes stale mid-flight must not notify the socket or mutate UI")
  }

  @MainActor
  func testStaleDuringFlushSkipsTheLocalWrite() async {
    let events = EventLog()
    let stillCurrent = CurrentFlag()
    let saved = await runAssignment(
      context: .init(backendConversationId: nil, sessionId: 7),
      isCurrent: { stillCurrent.value },
      events: events,
      flushFlip: stillCurrent
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(events.values, ["flush"], "going stale during flush must prevent the SQLite write entirely")
  }

  @MainActor
  func testLocalOnlyFlushesThenRequiresAChangedRow() async {
    let events = EventLog()
    let saved = await runAssignment(
      context: .init(backendConversationId: nil, sessionId: 7),
      persistLocal: { _ in 2 },
      events: events
    )
    XCTAssertTrue(saved)
    XCTAssertEqual(
      events.values, ["flush", "local:7", "apply"],
      "queued segment writes must land before the assignment UPDATE, and no socket wake-up fires for local-only saves")
  }

  @MainActor
  func testLocalWriteWithZeroRowsFails() async {
    let events = EventLog()
    let saved = await runAssignment(
      context: .init(backendConversationId: nil, sessionId: 7),
      persistLocal: { _ in 0 },
      events: events
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(events.values, ["flush", "local:7"], "0 rows means nothing durable holds the assignment")
  }

  @MainActor
  func testNoBackendAndNoSessionNeverFabricatesAnId() async {
    let events = EventLog()
    let saved = await runAssignment(
      context: .init(backendConversationId: nil, sessionId: nil),
      events: events
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(events.values, ["flush"], "nothing may be persisted against a fabricated conversation id")
  }

  @MainActor
  func testStaleLocalCompletionStillLeavesMapUntouched() async {
    let events = EventLog()
    let current = CurrentFlag()
    let saved = await runAssignment(
      context: .init(backendConversationId: nil, sessionId: 7),
      isCurrent: { current.value },
      persistLocal: { _ in
        current.value = false
        return 1
      },
      events: events
    )
    XCTAssertFalse(saved)
    XCTAssertEqual(events.values, ["flush", "local:7"])
  }

  @MainActor
  func testLocalSTTSegmentsOverlayTheManualSpeakerMap() {
    let appState = AppState()
    appState.sttSession.activeMode = .local
    appState.liveManualSpeakerPersonMap[1] = "person-mara"

    appState.handleBackendSegments([
      TranscriptionService.BackendSegment(
        id: "seg-late", text: "later speech", speaker: "SPEAKER_01", speaker_id: 1,
        is_user: true, person_id: nil, start: 10, end: 11, translations: nil)
    ])

    XCTAssertEqual(appState.speakerSegments.first?.personId, "person-mara")
    XCTAssertFalse(
      appState.speakerSegments.first?.isUser ?? true,
      "a person assignment is no longer the user, matching the persisted row")
  }

  @MainActor
  func testAutoSuggestionMapAloneDoesNotOverlayLocalSegments() {
    let appState = AppState()
    appState.sttSession.activeMode = .local
    appState.liveSpeakerPersonMap[1] = "person-auto"

    appState.handleBackendSegments([
      TranscriptionService.BackendSegment(
        id: "seg-auto", text: "speech", speaker: "SPEAKER_01", speaker_id: 1,
        is_user: false, person_id: nil, start: 10, end: 11, translations: nil)
    ])

    XCTAssertNil(
      appState.speakerSegments.first?.personId,
      "an unconfirmed suggestion must not be written into local segments")
  }

  @MainActor
  func testCloudSegmentsDoNotOverlayTheManualSpeakerMap() {
    let appState = AppState()
    appState.sttSession.activeMode = .cloud
    appState.liveManualSpeakerPersonMap[1] = "person-mara"

    appState.handleBackendSegments([
      TranscriptionService.BackendSegment(
        id: "seg-cloud", text: "cloud speech", speaker: "SPEAKER_01", speaker_id: 1,
        is_user: false, person_id: nil, start: 10, end: 11, translations: nil)
    ])

    XCTAssertNil(
      appState.speakerSegments.first?.personId,
      "cloud suggestions keep backend authority — the local map must not rewrite them")
  }

  @MainActor
  func testManualMapDoesNotSurviveSessionReset() {
    let appState = AppState()
    appState.sttSession.activeMode = .local
    appState.liveManualSpeakerPersonMap[1] = "person-mara"
    appState.liveSpeakerPersonMap[1] = "person-mara"

    appState.clearTranscriptionState(finishSession: false)

    XCTAssertTrue(appState.liveManualSpeakerPersonMap.isEmpty)
    appState.handleBackendSegments([
      TranscriptionService.BackendSegment(
        id: "seg-next", text: "next recording", speaker: "SPEAKER_01", speaker_id: 1,
        is_user: false, person_id: nil, start: 0, end: 1, translations: nil)
    ])
    XCTAssertNil(
      appState.speakerSegments.first?.personId,
      "a new recording must not inherit the previous one's manual assignment")
  }

  func testSpeakerAssignedMessageSerializesTypePersonAndSegmentIds() throws {
    let message = try XCTUnwrap(
      TranscriptionService.speakerAssignedMessage(personId: "person-1", segmentIds: ["a", "b"]))
    let parsed = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(message.utf8)) as? [String: Any])
    XCTAssertEqual(parsed["type"] as? String, "speaker_assigned")
    XCTAssertEqual(parsed["person_id"] as? String, "person-1")
    XCTAssertEqual(parsed["segment_ids"] as? [String], ["a", "b"])
  }
}
