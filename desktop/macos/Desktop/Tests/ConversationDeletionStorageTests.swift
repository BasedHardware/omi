@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class ConversationDeletionStorageTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "conversation-deletion")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testDeletedSessionRejectsEqualAndNewerHydrationAcrossRestart() async throws {
    let conversation = makeConversation(id: "deleted-recording", revision: 100)
    let sessionId = try await TranscriptionStorage.shared.syncServerConversation(conversation)
    try await TranscriptionStorage.shared.deleteByBackendId(conversation.id)
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()

    for revision in [100.0, 200.0] {
      do {
        _ = try await TranscriptionStorage.shared.syncServerConversation(
          makeConversation(id: conversation.id, revision: revision))
        XCTFail("A server snapshot must not hydrate a deleted conversation")
      } catch is CancellationError {
        // Deletion remains authoritative over either server revision.
      }
    }

    let stored = try await TranscriptionStorage.shared.getSession(id: sessionId)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: conversation.id)
    let listed = try await TranscriptionStorage.shared.getLocalConversations()
    XCTAssertEqual(stored?.deleted, true)
    XCTAssertNil(cached)
    XCTAssertFalse(listed.contains { $0.id == conversation.id })
  }

  func testDeletionWithoutCachedRowRejectsLaterHydration() async throws {
    try await TranscriptionStorage.shared.deleteByBackendId("never-cached")
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()

    do {
      _ = try await TranscriptionStorage.shared.syncServerConversation(makeConversation(id: "never-cached"))
      XCTFail("Deletion evidence must survive without a transcription session")
    } catch is CancellationError {
      // A content-free deletion marker blocks a later insert.
    }
    let stored = try await TranscriptionStorage.shared.getSessionByBackendId("never-cached")
    XCTAssertNil(stored, "A deletion marker must not fabricate a conversation row")
  }

  func testDeletedRecordCannotRetryOrAcceptServerRestoration() {
    var record = TranscriptionSessionRecord.from(makeConversation(id: "retired"))
    record.deleted = true
    record.updateFrom(makeConversation(id: "retired", revision: 200))

    XCTAssertTrue(record.deleted)
    XCTAssertFalse(record.canRetry)
    XCTAssertFalse(record.canAcceptCompletion(backendId: "retired"))
    XCTAssertNil(record.toServerConversation(segments: []))
  }

  func testPendingIntentWithoutCachedRowSurvivesRestartAndConfirmationCannotRollback() async throws {
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: "pending-orphan")
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()
    let pending = try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
    let all = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    XCTAssertEqual(pending, ["pending-orphan"])
    XCTAssertEqual(all, ["pending-orphan"])

    try await TranscriptionStorage.shared.confirmConversationDeletion(backendId: "pending-orphan")
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: "pending-orphan")
    try await TranscriptionStorage.shared.rollbackConversationDeletion(backendId: "pending-orphan")
    let confirmed = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    let remainingPending = try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
    XCTAssertEqual(confirmed, ["pending-orphan"])
    XCTAssertTrue(remainingPending.isEmpty, "A repeated prepare cannot demote a confirmed deletion")
  }

  func testFailedPendingDeleteRestoresTheOriginalLiveRowAndRetainsOtherDeletions() async throws {
    let visible = makeConversation(id: "rollback-visible")
    let id = try await TranscriptionStorage.shared.syncServerConversation(visible)
    let retired = try await TranscriptionStorage.shared.syncServerConversation(makeConversation(id: "retired-other"))
    try await TranscriptionStorage.shared.deleteByBackendId("retired-other")

    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: visible.id)
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: visible.id)
    let hidden = try await TranscriptionStorage.shared.getCachedConversation(id: visible.id)
    XCTAssertNil(hidden)
    try await TranscriptionStorage.shared.rollbackConversationDeletion(backendId: visible.id)

    let restored = try await TranscriptionStorage.shared.getSession(id: id)
    let stillDeleted = try await TranscriptionStorage.shared.getSession(id: retired)
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: visible.id)
    let pending = try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
    let deletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    XCTAssertEqual(restored?.deleted, false)
    XCTAssertEqual(cached?.id, visible.id)
    XCTAssertEqual(stillDeleted?.deleted, true)
    XCTAssertTrue(pending.isEmpty)
    XCTAssertEqual(deletions, ["retired-other"])
  }

  func testFailedPendingDeleteWithoutRowDoesNotFabricateRestoration() async throws {
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: "missing")
    try await TranscriptionStorage.shared.rollbackConversationDeletion(backendId: "missing")
    let ids = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    let row = try await TranscriptionStorage.shared.getSessionByBackendId("missing")
    XCTAssertTrue(ids.isEmpty)
    XCTAssertNil(row)
    _ = try await TranscriptionStorage.shared.syncServerConversation(makeConversation(id: "missing"))
  }

  func testOwnerScopeRejectsStaleDeletionBeforeTransactionAdmission() async throws {
    let scope = ConversationCacheWriteScope()
    let generation = scope.capture()
    scope.advance()
    do {
      try await TranscriptionStorage.shared.prepareConversationDeletion(
        backendId: "previous-owner", cacheScope: scope, cacheGeneration: generation)
      XCTFail("A previous owner's deletion must not enter the current database")
    } catch is CancellationError {
      // The transaction must leave no marker or session mutation.
    }
    let ids = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    XCTAssertTrue(ids.isEmpty)
  }

  func testLedgerDeletionRejectsLateIdentityBindingAndCompletion() async throws {
    try await TranscriptionStorage.shared.deleteByBackendId("retired-identity")
    let id = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.bindBackendConversation(id: id, backendId: "retired-identity")
    let completed = try await TranscriptionStorage.shared.markSessionCompleted(id: id, backendId: "retired-identity")
    let row = try await TranscriptionStorage.shared.getSession(id: id)
    XCTAssertFalse(completed)
    XCTAssertNil(row?.backendId)
    XCTAssertEqual(row?.status, .recording)
  }

  func testConfirmedUnboundSessionDeletionIsTerminalAcrossRestart() async throws {
    let owner = try XCTUnwrap(fixture?.testUserId)
    let id = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.finishSession(id: id)
    let stored = try await TranscriptionStorage.shared.getSession(id: id)
    let session = try XCTUnwrap(stored)
    let expectedIdentity = ConversationFinalizationService.localClientConversationId(session: session, sessionId: id)
    try await TranscriptionStorage.shared.confirmSessionDeletion(
      id: id, expectedOwner: owner, expectedSessionId: expectedIdentity)
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    try await RewindDatabase.shared.initialize()
    let row = try await TranscriptionStorage.shared.getSession(id: id)
    let recovery = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    let uploading = try await TranscriptionStorage.shared.markSessionUploading(id: id)
    let completed = try await TranscriptionStorage.shared.markSessionCompleted(id: id, backendId: "late-id")
    let backendDeletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    XCTAssertEqual(row?.deleted, true)
    XCTAssertNil(row?.backendId)
    XCTAssertFalse(recovery.contains { $0.id == id })
    XCTAssertFalse(uploading)
    XCTAssertFalse(completed)
    XCTAssertTrue(backendDeletions.isEmpty, "Retiring an unbound session must not invent a backend identity")
  }

  func testConfirmedBoundSessionDeletionAlsoConfirmsTheBackendLedger() async throws {
    let owner = try XCTUnwrap(fixture?.testUserId)
    let id = try await TranscriptionStorage.shared.startSession(
      source: "desktop", clientConversationId: "bound-session")
    try await TranscriptionStorage.shared.bindBackendConversation(id: id, backendId: "bound-retired")
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: "bound-retired")
    try await TranscriptionStorage.shared.confirmSessionDeletion(
      id: id, expectedOwner: owner, expectedSessionId: "bound-session")
    try await TranscriptionStorage.shared.rollbackConversationDeletion(backendId: "bound-retired")
    let row = try await TranscriptionStorage.shared.getSession(id: id)
    let deletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    let pending = try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
    XCTAssertEqual(row?.deleted, true)
    XCTAssertEqual(deletions, ["bound-retired"])
    XCTAssertTrue(pending.isEmpty)
  }

  func testSessionRetirementRejectsAReusedRowWithAnotherStableIdentity() async throws {
    let owner = try XCTUnwrap(fixture?.testUserId)
    let id = try await TranscriptionStorage.shared.startSession(
      source: "desktop", clientConversationId: "current-session")
    do {
      try await TranscriptionStorage.shared.confirmSessionDeletion(
        id: id, expectedOwner: owner, expectedSessionId: "foreign-session")
      XCTFail("An old response cannot retire a row holding another stable session identity")
    } catch is CancellationError {
      // The numeric row id alone is not sufficient deletion authority.
    }
    let row = try await TranscriptionStorage.shared.getSession(id: id)
    let deletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
    XCTAssertEqual(row?.deleted, false)
    XCTAssertTrue(deletions.isEmpty)
  }

  func testSessionRetirementRejectsTheNextOwnersReusedRowId() async throws {
    let first = try XCTUnwrap(fixture)
    let otherOwner = first.testUserId + "-retirement-other"
    let otherDirectory = RewindStorageTestIsolation.userDirectory(for: otherOwner)
    let firstID = try await TranscriptionStorage.shared.startSession(
      source: "desktop", clientConversationId: "same-session-identity")
    do {
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: otherOwner)
      try await RewindDatabase.shared.initialize()
      let otherID = try await TranscriptionStorage.shared.startSession(
        source: "desktop", clientConversationId: "same-session-identity")
      XCTAssertEqual(firstID, otherID, "The fixture must reproduce a reused numeric session id")
      do {
        try await TranscriptionStorage.shared.confirmSessionDeletion(
          id: firstID, expectedOwner: first.testUserId, expectedSessionId: "same-session-identity")
        XCTFail("A previous owner's response cannot retire the next owner's row")
      } catch is CancellationError {
        // Even a matching client id cannot authorize a write under another owner.
      }
      do {
        _ = try await TranscriptionStorage.shared.markSessionCompleted(
          id: otherID, backendId: "old-owner-response", expectedOwner: first.testUserId,
          expectedSessionId: "same-session-identity")
        XCTFail("A previous owner's completion must not bind the next owner's reused row")
      } catch is CancellationError {}
      do {
        try await TranscriptionStorage.shared.incrementRetryCount(
          id: otherID, expectedOwner: first.testUserId, expectedSessionId: "same-session-identity")
        XCTFail("A previous owner's failure must not spend the next owner's retry budget")
      } catch is CancellationError {}
      do {
        try await TranscriptionStorage.shared.markSessionFailed(
          id: otherID, error: "old-owner-failure", expectedOwner: first.testUserId,
          expectedSessionId: "same-session-identity")
        XCTFail("A previous owner's failure must not mark the next owner's row failed")
      } catch is CancellationError {}
      let otherRow = try await TranscriptionStorage.shared.getSession(id: otherID)
      XCTAssertEqual(otherRow?.deleted, false)
      XCTAssertEqual(otherRow?.retryCount, 0)
      XCTAssertNil(otherRow?.backendId)
      XCTAssertNil(otherRow?.lastError)
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: first.testUserId)
      try await RewindDatabase.shared.initialize()
      let original = try await TranscriptionStorage.shared.getSession(id: firstID)
      XCTAssertEqual(original?.deleted, false)
    } catch {
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: first.testUserId)
      try? FileManager.default.removeItem(at: otherDirectory)
      throw error
    }
    try FileManager.default.removeItem(at: otherDirectory)
  }

  func testSegmentHydrationAfterDeletionCannotReplaceSavedTranscript() async throws {
    let conversation = makeConversation(id: "retired-transcript")
    let id = try await TranscriptionStorage.shared.syncServerConversation(conversation)
    try await TranscriptionStorage.shared.appendSegment(
      sessionId: id, speaker: 0, text: "Original synthetic transcript", startTime: 0, endTime: 1)
    try await TranscriptionStorage.shared.prepareConversationDeletion(backendId: conversation.id)
    var staleDetail = conversation
    staleDetail.transcriptSegments = [
      TranscriptSegment(
        id: "late", text: "Late replacement", speaker: "SPEAKER_00", isUser: false,
        personId: nil, start: 0, end: 1)
    ]
    do {
      try await TranscriptionStorage.shared.upsertSegmentsFromServerConversation(staleDetail, sessionId: id)
      XCTFail("A detail write admitted after deletion must not replace the transcript")
    } catch is CancellationError {
      // A deletion between the session and segment transactions fences the second write.
    }
    let segments = try await TranscriptionStorage.shared.getSegments(sessionId: id)
    XCTAssertEqual(segments.map(\.text), ["Original synthetic transcript"])
  }

  func testDeletionLedgerWinsIfALegacyWriterClearsTheSessionFlag() async throws {
    let conversation = makeConversation(id: "ledger-authority")
    let id = try await TranscriptionStorage.shared.syncServerConversation(conversation)
    try await TranscriptionStorage.shared.deleteByBackendId(conversation.id)
    let pool = await RewindDatabase.shared.getDatabaseQueue()
    let db = try XCTUnwrap(pool)
    try await db.write { database in
      try database.execute(
        sql: "UPDATE transcription_sessions SET deleted = 0, backendSynced = 0, status = ? WHERE id = ?",
        arguments: [TranscriptionSessionStatus.pendingUpload.rawValue, id])
    }
    let cached = try await TranscriptionStorage.shared.getCachedConversation(id: conversation.id)
    let bundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: id)
    let recovery = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    let upload = try await TranscriptionStorage.shared.markSessionUploading(id: id)
    XCTAssertNil(cached)
    XCTAssertNil(bundle)
    XCTAssertFalse(recovery.contains { $0.id == id })
    XCTAssertFalse(upload)
  }

  func testDeletionLedgerIsScopedToTheDatabaseOwner() async throws {
    let first = try XCTUnwrap(fixture)
    let otherOwner = first.testUserId + "-other"
    let otherDirectory = RewindStorageTestIsolation.userDirectory(for: otherOwner)
    try await TranscriptionStorage.shared.deleteByBackendId("same-id")
    do {
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: otherOwner)
      try await RewindDatabase.shared.initialize()
      let otherDeletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
      XCTAssertTrue(otherDeletions.isEmpty)
      _ = try await TranscriptionStorage.shared.syncServerConversation(makeConversation(id: "same-id"))
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: first.testUserId)
      try await RewindDatabase.shared.initialize()
      let originalDeletions = try await TranscriptionStorage.shared.getConversationDeletionIDs()
      let originalRow = try await TranscriptionStorage.shared.getSessionByBackendId("same-id")
      XCTAssertEqual(originalDeletions, ["same-id"])
      XCTAssertNil(originalRow)
    } catch {
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      await RewindDatabase.shared.configure(userId: first.testUserId)
      try? FileManager.default.removeItem(at: otherDirectory)
      throw error
    }
    try FileManager.default.removeItem(at: otherDirectory)
  }

  func testEveryRecoveryQueueExcludesDeletedRowsAndKeepsLiveWork() async throws {
    let pool = await RewindDatabase.shared.getDatabaseQueue()
    let db = try XCTUnwrap(pool)
    let stale = Date(timeIntervalSince1970: 1)
    var deletedIDs = Set<Int64>()
    for (index, status) in [
      TranscriptionSessionStatus.recording, .pendingUpload, .uploading, .failed, .failed,
    ].enumerated() {
      let id = try await TranscriptionStorage.shared.startSession(source: "desktop")
      let backendId = "recovery-retired-\(index)"
      try await TranscriptionStorage.shared.bindBackendConversation(id: id, backendId: backendId)
      try await TranscriptionStorage.shared.appendSegment(
        sessionId: id, speaker: 0, text: "Synthetic evidence", startTime: 0, endTime: 1)
      try await TranscriptionStorage.shared.deleteByBackendId(backendId)
      try await db.write { database in
        try database.execute(
          sql: "UPDATE transcription_sessions SET status = ?, retryCount = ?, updatedAt = ? WHERE id = ?",
          arguments: [status.rawValue, index == 4 ? 5 : 0, stale, id])
      }
      deletedIDs.insert(id)
    }
    let live = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.finishSession(id: live)

    let queues = [
      try await TranscriptionStorage.shared.getPendingUploadSessions(),
      try await TranscriptionStorage.shared.getFailedSessions(),
      try await TranscriptionStorage.shared.getSessionsNeedingFinalization(),
      try await TranscriptionStorage.shared.getExhaustedCloudSessionsWithLocalSegments(),
      try await TranscriptionStorage.shared.getCrashedSessions(),
      try await TranscriptionStorage.shared.getStuckUploadingSessions(olderThan: 0),
      try await TranscriptionStorage.shared.getSessionsNeedingRecovery(),
    ]
    for queue in queues {
      XCTAssertTrue(deletedIDs.isDisjoint(with: queue.compactMap(\.id)))
    }
    XCTAssertEqual(queues[0].compactMap(\.id), [live])
    XCTAssertEqual(queues[2].compactMap(\.id), [live])
    XCTAssertEqual(queues[6].compactMap(\.id), [live])
    let active = try await TranscriptionStorage.shared.getActiveSession()
    XCTAssertNil(active)
  }

  func testMigrationCopiesLegacyDeletionEvidenceWithoutChangingContent() throws {
    let queue = try DatabaseQueue()
    try queue.write { database in
      try database.execute(
        sql: """
          CREATE TABLE transcription_sessions (id INTEGER PRIMARY KEY, backendId TEXT, deleted INTEGER, title TEXT);
          INSERT INTO transcription_sessions VALUES (1, 'retired', 1, 'Keep original');
          INSERT INTO transcription_sessions VALUES (2, 'retired', 1, 'Duplicate legacy cache');
          INSERT INTO transcription_sessions VALUES (3, 'live', 0, 'Live original');
          INSERT INTO transcription_sessions VALUES (4, NULL, 1, 'Local only');
          """)
    }
    var migrator = DatabaseMigrator()
    RewindDatabase.registerConversationDeletionMigration(on: &migrator)
    try migrator.migrate(queue)
    try queue.read { database in
      XCTAssertEqual(try String.fetchAll(database, sql: "SELECT backendId FROM conversation_deletions"), ["retired"])
      XCTAssertEqual(try Bool.fetchOne(database, sql: "SELECT pending FROM conversation_deletions"), false)
      XCTAssertEqual(
        try String.fetchOne(database, sql: "SELECT restorableSessionIds FROM conversation_deletions"), "[]")
      XCTAssertEqual(try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM transcription_sessions"), 4)
      XCTAssertEqual(
        try String.fetchOne(database, sql: "SELECT title FROM transcription_sessions WHERE id = 1"), "Keep original")
      XCTAssertEqual(
        try database.columns(in: "conversation_deletions").map(\.name),
        [
          "backendId", "pending", "restorableSessionIds",
        ])
    }
  }

  func testDeletedUnfinishedSessionsNeverEnterRecoveryOrAcceptLateWrites() async throws {
    let id = try await TranscriptionStorage.shared.startSession(source: "desktop")
    try await TranscriptionStorage.shared.bindBackendConversation(id: id, backendId: "deleted-pending")
    try await TranscriptionStorage.shared.appendSegment(
      sessionId: id, speaker: 0, text: "Synthetic evidence", startTime: 0, endTime: 1)
    try await TranscriptionStorage.shared.finishSession(id: id)
    try await TranscriptionStorage.shared.deleteByBackendId("deleted-pending")

    let pending = try await TranscriptionStorage.shared.getPendingUploadSessions()
    let finalizing = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    let recovery = try await TranscriptionStorage.shared.getSessionsNeedingRecovery()
    let bundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: id)
    XCTAssertFalse(pending.contains { $0.id == id })
    XCTAssertFalse(finalizing.contains { $0.id == id })
    XCTAssertFalse(recovery.contains { $0.id == id })
    XCTAssertNil(bundle)

    let uploading = try await TranscriptionStorage.shared.markSessionUploading(id: id)
    let completed = try await TranscriptionStorage.shared.markSessionCompleted(
      id: id, backendId: "another-id", allowBackendIdOverride: true)
    try await TranscriptionStorage.shared.markSessionFailed(id: id, error: "late error")
    try await TranscriptionStorage.shared.incrementRetryCount(id: id)
    let stored = try await TranscriptionStorage.shared.getSession(id: id)
    XCTAssertFalse(uploading)
    XCTAssertFalse(completed)
    XCTAssertEqual(stored?.deleted, true)
    XCTAssertEqual(stored?.status, .pendingUpload)
    XCTAssertEqual(stored?.backendId, "deleted-pending")
    XCTAssertEqual(stored?.retryCount, 0)
    XCTAssertNil(stored?.lastError)
  }

  private func makeConversation(id: String, revision: TimeInterval = 100) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: revision),
      startedAt: Date(timeIntervalSince1970: 1),
      finishedAt: Date(timeIntervalSince1970: 2),
      structured: Structured(
        title: "Synthetic conversation", overview: "Synthetic summary", emoji: "", category: "other",
        actionItems: [], events: []),
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
      visibility: "private",
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }
}
