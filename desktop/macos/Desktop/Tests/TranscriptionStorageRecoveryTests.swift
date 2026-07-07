import XCTest
@testable import Omi_Computer

final class TranscriptionStorageRecoveryTests: XCTestCase {
    private var testUserId: String!
    private var userDir: URL?

    override func setUp() async throws {
        try await super.setUp()
        testUserId = "transcription-storage-recovery-test-\(UUID().uuidString)"
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

    func testBoundRecordingSessionIsStillCrashRecoverable() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.bindBackendConversation(
            id: sessionId,
            backendId: "backend-conversation-recording"
        )

        let crashed = try await TranscriptionStorage.shared.getCrashedSessions()

        XCTAssertTrue(
            crashed.contains { $0.id == sessionId },
            "Unsynced sessions bound to a backend conversation id must remain crash-recoverable"
        )
    }

    func testBoundPendingUploadSessionIsStillRecoverable() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.bindBackendConversation(
            id: sessionId,
            backendId: "backend-conversation-pending"
        )
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .crashRecovery)

        let pending = try await TranscriptionStorage.shared.getPendingUploadSessions()

        XCTAssertTrue(
            pending.contains { $0.id == sessionId },
            "Unsynced pending sessions with a backend conversation id must still be retried"
        )
    }

    func testBoundFailedSessionIsStillRetryable() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.bindBackendConversation(
            id: sessionId,
            backendId: "backend-conversation-failed"
        )
        try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: "transient test failure")

        let failed = try await TranscriptionStorage.shared.getFailedSessions()

        XCTAssertTrue(
            failed.contains { $0.id == sessionId },
            "Unsynced failed sessions with a backend conversation id must still be retried"
        )
    }

    func testCompletedBackendSyncedSessionIsNotRecovered() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
        try await TranscriptionStorage.shared.markSessionCompleted(
            id: sessionId,
            backendId: "backend-conversation-completed"
        )

        let needingRecovery = try await TranscriptionStorage.shared.getSessionsNeedingRecovery()

        XCTAssertFalse(
            needingRecovery.contains { $0.id == sessionId },
            "Completed backend-synced sessions should not re-enter recovery queues"
        )
    }
}
