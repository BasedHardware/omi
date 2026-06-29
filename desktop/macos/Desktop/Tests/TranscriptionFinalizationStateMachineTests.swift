import XCTest
@testable import Omi_Computer

final class TranscriptionFinalizationStateMachineTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL?

    override func setUp() async throws {
        try await super.setUp()
        testUserId = "transcription-finalization-test-\(UUID().uuidString)"
        await RewindDatabase.shared.close()
        await TranscriptionStorage.shared.invalidateCache()
        RewindDatabase.currentUserId = testUserId
        await RewindDatabase.shared.configure(userId: testUserId)
        try await RewindDatabase.shared.initialize()

        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        userDir = appSupport
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

    func testFinalizationStrategyReasonAndTimestampsPersistAcrossStorageReopen() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .localSegments
        )

        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .finishAndContinue
        )
        try await TranscriptionStorage.shared.markSessionUploading(id: sessionId)

        let uploadingSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let uploading = try XCTUnwrap(uploadingSession)
        XCTAssertEqual(uploading.status, .uploading)
        XCTAssertEqual(uploading.finalizationStrategy, .localSegments)
        XCTAssertEqual(uploading.finalizationReason, .finishAndContinue)
        XCTAssertNotNil(uploading.finishedAt)
        XCTAssertNotNil(uploading.finalizationStartedAt)
        XCTAssertNil(uploading.finalizationCompletedAt)

        try await TranscriptionStorage.shared.markSessionCompleted(
            id: sessionId,
            backendId: "backend-finalized"
        )

        await RewindDatabase.shared.close()
        await TranscriptionStorage.shared.invalidateCache()
        try await RewindDatabase.shared.initialize()

        let completedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let completed = try XCTUnwrap(completedSession)
        XCTAssertEqual(completed.status, .completed)
        XCTAssertEqual(completed.backendId, "backend-finalized")
        XCTAssertTrue(completed.backendSynced)
        XCTAssertEqual(completed.finalizationStrategy, .localSegments)
        XCTAssertEqual(completed.finalizationReason, .finishAndContinue)
        XCTAssertNotNil(completed.finalizationStartedAt)
        XCTAssertNotNil(completed.finalizationCompletedAt)
    }

    func testFinishSessionDefaultsStrategyAndStoresReason() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")

        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .userStop
        )

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let session = try XCTUnwrap(storedSession)
        XCTAssertEqual(session.status, .pendingUpload)
        XCTAssertEqual(session.finalizationStrategy, .cloudReconcile)
        XCTAssertEqual(session.finalizationReason, .userStop)
        XCTAssertNil(session.finalizationStartedAt)
        XCTAssertNil(session.finalizationCompletedAt)
    }

    func testSessionsNeedingFinalizationIncludesRetryableWorkOnly() async throws {
        let recordingId = try await TranscriptionStorage.shared.startSession(source: "desktop")

        let pendingId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: pendingId,
            reason: .userStop
        )

        let failedRetryableId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: failedRetryableId,
            reason: .retry
        )
        try await TranscriptionStorage.shared.markSessionFailed(
            id: failedRetryableId,
            error: "transient finalization failure"
        )

        let failedExhaustedId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: failedExhaustedId,
            reason: .retry
        )
        try await TranscriptionStorage.shared.markSessionFailed(
            id: failedExhaustedId,
            error: "exhausted finalization failure"
        )
        for _ in 0..<5 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: failedExhaustedId)
        }

        let completedId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: completedId,
            reason: .userStop
        )
        try await TranscriptionStorage.shared.markSessionCompleted(
            id: completedId,
            backendId: "backend-completed"
        )

        let needingFinalization = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
        let ids = Set(needingFinalization.compactMap(\.id))

        XCTAssertTrue(ids.contains(pendingId))
        XCTAssertTrue(ids.contains(failedRetryableId))
        XCTAssertFalse(ids.contains(recordingId))
        XCTAssertFalse(ids.contains(failedExhaustedId))
        XCTAssertFalse(ids.contains(completedId))
    }

    func testFreshUploadingSessionWaitsForStaleRecoveryWindow() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .userStop
        )
        try await TranscriptionStorage.shared.markSessionUploading(id: sessionId)

        let needingFinalization = try await TranscriptionStorage.shared.getSessionsNeedingFinalization(
            uploadingStaleAfter: 300
        )

        XCTAssertFalse(
            needingFinalization.contains { $0.id == sessionId },
            "Fresh uploading sessions should not be retried until the stale recovery window expires"
        )
    }

    func testFreshUploadingSessionCannotBeReclaimedImmediately() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .userStop
        )

        let firstClaim = try await TranscriptionStorage.shared.markSessionUploading(id: sessionId)
        let secondClaim = try await TranscriptionStorage.shared.markSessionUploading(id: sessionId)

        XCTAssertTrue(firstClaim)
        XCTAssertFalse(secondClaim)
    }

    func testProcessingServerConversationDoesNotStampFinalizationCompletedAt() async throws {
        let conversation = makeServerConversation(status: .processing)

        let sessionId = try await TranscriptionStorage.shared.syncServerConversation(conversation)
        let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let unwrappedSession = try XCTUnwrap(session)

        XCTAssertEqual(unwrappedSession.conversationStatus, .processing)
        XCTAssertNil(unwrappedSession.finalizationCompletedAt)
    }

    func testEmptyLocalSegmentsSessionIsDiscardedInsteadOfRetriedForever() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .localSegments
        )
        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .userStop
        )

        await ConversationFinalizationService.shared.finalizeSession(
            id: sessionId,
            reason: .userStop
        )

        let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
        XCTAssertNil(session)
    }

    private func makeServerConversation(status: ConversationStatus) -> ServerConversation {
        let createdAt = Date(timeIntervalSince1970: 1_000)
        return ServerConversation(
            id: "server-\(status.rawValue)",
            createdAt: createdAt,
            startedAt: createdAt,
            finishedAt: createdAt.addingTimeInterval(60),
            structured: Structured(
                title: "Title",
                overview: "Overview",
                emoji: "chat",
                category: "other",
                actionItems: [],
                events: []
            ),
            transcriptSegments: [],
            transcriptSegmentsIncluded: true,
            geolocation: nil,
            photos: [],
            appsResults: [],
            source: .desktop,
            language: "en",
            status: status,
            discarded: false,
            deleted: false,
            isLocked: false,
            starred: false,
            folderId: nil,
            inputDeviceName: nil,
            deferred: false
        )
    }
}
