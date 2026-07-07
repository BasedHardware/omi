import XCTest
import GRDB
@testable import Omi_Computer

private struct FinalizationRecoveryRequest {
    let url: URL
    let method: String
    let body: Data?
}

private final class FinalizationRecoveryURLStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var _requests: [FinalizationRecoveryRequest] = []

    static var requests: [FinalizationRecoveryRequest] {
        lock.lock()
        defer { lock.unlock() }
        return _requests
    }

    static func reset() {
        lock.lock()
        _requests.removeAll()
        lock.unlock()
    }

    private static func record(_ request: FinalizationRecoveryRequest) {
        lock.lock()
        _requests.append(request)
        lock.unlock()
    }

    private static func bodyData(from request: URLRequest) -> Data? {
        if let body = request.httpBody {
            return body
        }
        guard let stream = request.httpBodyStream else {
            return nil
        }

        stream.open()
        defer { stream.close() }

        var data = Data()
        let bufferSize = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }

        while stream.hasBytesAvailable {
            let readCount = stream.read(buffer, maxLength: bufferSize)
            if readCount > 0 {
                data.append(buffer, count: readCount)
            } else {
                break
            }
        }

        return data.isEmpty ? nil : data
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        if let url = request.url {
            Self.record(FinalizationRecoveryRequest(
                url: url,
                method: request.httpMethod ?? "GET",
                body: Self.bodyData(from: request)
            ))
        }

        let path = request.url?.path ?? ""
        if path == "/v1/conversations/from-segments" {
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(
                self,
                didLoad: Data(#"{"id":"local-fallback-conversation","status":"processing","discarded":false}"#.utf8)
            )
        } else if path == "/v1/conversations/local-fallback-conversation" {
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(
                self,
                didLoad: Data(
                    """
                    {
                      "id": "local-fallback-conversation",
                      "created_at": "2026-07-07T10:00:00Z",
                      "started_at": "2026-07-07T10:00:00Z",
                      "finished_at": "2026-07-07T10:01:00Z",
                      "structured": {
                        "title": "Hydrated local fallback",
                        "overview": "Hydrated overview",
                        "emoji": "",
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
                    }
                    """.utf8
                )
            )
        } else {
            let response = HTTPURLResponse(url: request.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(#"{"detail":"not found"}"#.utf8))
        }
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

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
        let clientConversationId = UUID().uuidString.lowercased()
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            clientConversationId: clientConversationId,
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
        XCTAssertEqual(uploading.clientConversationId, clientConversationId)
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
        XCTAssertEqual(completed.clientConversationId, clientConversationId)
        XCTAssertTrue(completed.backendSynced)
        XCTAssertEqual(completed.finalizationStrategy, .localSegments)
        XCTAssertEqual(completed.finalizationReason, .finishAndContinue)
        XCTAssertNotNil(completed.finalizationStartedAt)
        XCTAssertNotNil(completed.finalizationCompletedAt)
    }

    func testLocalUploadFallbackReusesPersistedClientConversationId() {
        let clientConversationId = UUID().uuidString.lowercased()
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            source: "desktop",
            clientConversationId: clientConversationId
        )

        XCTAssertEqual(
            ConversationFinalizationService.localClientConversationId(session: session, sessionId: 42),
            clientConversationId
        )
    }

    func testLocalUploadFallbackUsesStableLegacyKeyWhenClientConversationIdIsMissing() {
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000.123),
            source: "desktop"
        )

        XCTAssertEqual(
            ConversationFinalizationService.localClientConversationId(session: session, sessionId: 42),
            "macos-local-42-1700000000123"
        )
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

    func testMeetingEndedFinalizationReasonPersists() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .localSegments
        )

        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .meetingEnded
        )

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let session = try XCTUnwrap(storedSession)
        XCTAssertEqual(session.status, .pendingUpload)
        XCTAssertEqual(session.finalizationStrategy, .localSegments)
        XCTAssertEqual(session.finalizationReason, .meetingEnded)
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

    func testExhaustedCloudSessionsWithLocalSegmentsAreRecoverable() async throws {
        let recoverableId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.finishSession(id: recoverableId, reason: .userStop)
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: recoverableId,
            speaker: 0,
            text: "saved transcript",
            startTime: 0,
            endTime: 1
        )
        try await TranscriptionStorage.shared.markSessionFailed(id: recoverableId, error: "session_reconciliation_failed")
        for _ in 0..<5 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: recoverableId)
        }

        let legacyBackendBoundId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.bindBackendConversation(
            id: legacyBackendBoundId,
            backendId: "legacy-backend-id"
        )
        try await TranscriptionStorage.shared.finishSession(id: legacyBackendBoundId, reason: .userStop)
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: legacyBackendBoundId,
            speaker: 0,
            text: "legacy saved transcript",
            startTime: 0,
            endTime: 1
        )
        try await TranscriptionStorage.shared.markSessionFailed(
            id: legacyBackendBoundId,
            error: "session_reconciliation_failed"
        )
        for _ in 0..<5 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: legacyBackendBoundId)
        }
        let dbQueue = await RewindDatabase.shared.getDatabaseQueue()
        let db = try XCTUnwrap(dbQueue)
        try await db.write { database in
            try database.execute(
                sql: "UPDATE transcription_sessions SET finalizationStrategy = NULL WHERE id = ?",
                arguments: [legacyBackendBoundId]
            )
        }

        let emptyExhaustedId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.finishSession(id: emptyExhaustedId, reason: .userStop)
        try await TranscriptionStorage.shared.markSessionFailed(id: emptyExhaustedId, error: "session_reconciliation_failed")
        for _ in 0..<5 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: emptyExhaustedId)
        }

        let tooManyFallbackFailuresId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.finishSession(id: tooManyFallbackFailuresId, reason: .userStop)
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: tooManyFallbackFailuresId,
            speaker: 0,
            text: "already retried fallback",
            startTime: 0,
            endTime: 1
        )
        try await TranscriptionStorage.shared.markSessionFailed(
            id: tooManyFallbackFailuresId,
            error: "local fallback upload failed"
        )
        for _ in 0..<8 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: tooManyFallbackFailuresId)
        }

        let recoverable = try await TranscriptionStorage.shared.getExhaustedCloudSessionsWithLocalSegments()
        let ids = Set(recoverable.compactMap(\.id))

        XCTAssertTrue(ids.contains(recoverableId))
        XCTAssertTrue(ids.contains(legacyBackendBoundId))
        XCTAssertFalse(ids.contains(emptyExhaustedId))
        XCTAssertFalse(ids.contains(tooManyFallbackFailuresId))
    }

    func testRecoverPendingFinalizationsProcessesExhaustedBackendBoundLocalFallback() async throws {
        FinalizationRecoveryURLStub.reset()
        setenv("OMI_PYTHON_API_URL", "https://finalization-recovery.test/", 1)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FinalizationRecoveryURLStub.self]
        let client = APIClient(session: URLSession(configuration: config))
        await client.setTestAuthHeader("Bearer test-token")
        await ConversationFinalizationService.shared.setAPIClientForTesting(client)
        addTeardownBlock {
            await ConversationFinalizationService.shared.setAPIClientForTesting(nil)
        }
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            FinalizationRecoveryURLStub.reset()
        }

        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            clientConversationId: "client-fallback-id",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: "stale-backend-id")
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: sessionId,
            speaker: 0,
            text: "saved transcript for recovery",
            startTime: 0,
            endTime: 1
        )
        try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: "session_reconciliation_failed")
        for _ in 0..<5 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
        }

        await ConversationFinalizationService.shared.recoverPendingFinalizations()

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let session = try XCTUnwrap(storedSession)
        XCTAssertEqual(session.status, .completed)
        XCTAssertEqual(session.backendId, "local-fallback-conversation")
        XCTAssertTrue(session.backendSynced)
        XCTAssertEqual(session.title, "Hydrated local fallback")
        XCTAssertEqual(session.overview, "Hydrated overview")

        let requests = FinalizationRecoveryURLStub.requests
        let postRequests = requests.filter { $0.method == "POST" }
        let getRequests = requests.filter { $0.method == "GET" }
        XCTAssertEqual(postRequests.count, 1)
        XCTAssertEqual(postRequests.first?.url.path, "/v1/conversations/from-segments")
        XCTAssertEqual(getRequests.map(\.url.path), ["/v1/conversations/local-fallback-conversation"])

        let body = try XCTUnwrap(postRequests.first?.body)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(json["client_conversation_id"] as? String, "client-fallback-id")
        let segments = try XCTUnwrap(json["transcript_segments"] as? [[String: Any]])
        XCTAssertEqual(segments.first?["text"] as? String, "saved transcript for recovery")
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

    func testRestartRecoveryDoesNotForceProcessWhenCapturedBackendIdWasNotPersisted() async throws {
        let capturedBackendId = "backend-conversation-123"
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.finishSession(
            id: sessionId,
            reason: .userStop
        )

        await RewindDatabase.shared.close()
        await TranscriptionStorage.shared.invalidateCache()
        try await RewindDatabase.shared.initialize()

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let recoveredSession = try XCTUnwrap(storedSession)
        XCTAssertNil(recoveredSession.backendId)
        XCTAssertFalse(
            DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
                capturedBackendId: capturedBackendId,
                persistedBackendId: recoveredSession.backendId
            ),
            "After restart, a captured-but-unpersisted id must not enable current-pointer force-process"
        )
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

    func testFromSegmentsSuccessWithCompletionConflictMarksRetryableFailure() async throws {
        FinalizationRecoveryURLStub.reset()
        setenv("OMI_PYTHON_API_URL", "https://finalization-recovery.test/", 1)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FinalizationRecoveryURLStub.self]
        let client = APIClient(session: URLSession(configuration: config))
        await client.setTestAuthHeader("Bearer test-token")
        await ConversationFinalizationService.shared.setAPIClientForTesting(client)
        addTeardownBlock {
            await ConversationFinalizationService.shared.setAPIClientForTesting(nil)
        }
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            FinalizationRecoveryURLStub.reset()
        }

        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: "desktop",
            finalizationStrategy: .localSegments
        )
        try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: "existing-backend-id")
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: sessionId,
            speaker: 0,
            text: "saved transcript for conflicting completion",
            startTime: 0,
            endTime: 1
        )

        await ConversationFinalizationService.shared.finalizeSession(
            id: sessionId,
            reason: .userStop
        )

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let session = try XCTUnwrap(storedSession)
        XCTAssertEqual(session.status, .failed)
        XCTAssertEqual(session.retryCount, 1)
        XCTAssertEqual(session.backendId, "existing-backend-id")
        XCTAssertFalse(session.backendSynced)
        let segmentCount = try await TranscriptionStorage.shared.getSegmentCount(sessionId: sessionId)
        XCTAssertEqual(segmentCount, 1)

        let requests = FinalizationRecoveryURLStub.requests
        XCTAssertEqual(requests.filter { $0.method == "POST" }.map(\.url.path), ["/v1/conversations/from-segments"])
        XCTAssertTrue(requests.filter { $0.method == "GET" }.isEmpty)
    }

    func testCloudReconciliationExhaustionKeepsRetryingBeforeMaxAttempts() {
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            source: ConversationSource.desktop.rawValue,
            retryCount: 3,
            finalizationStrategy: .cloudReconcile
        )

        XCTAssertEqual(
            ConversationFinalizationService.cloudReconciliationExhaustionAction(
                session: session,
                segmentCount: 0
            ),
            .keepRetrying
        )
    }

    func testCloudReconciliationExhaustionFallsBackToLocalSegmentsWhenAvailable() {
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            source: ConversationSource.desktop.rawValue,
            retryCount: 4,
            finalizationStrategy: .cloudReconcile
        )

        XCTAssertEqual(
            ConversationFinalizationService.cloudReconciliationExhaustionAction(
                session: session,
                segmentCount: 2
            ),
            .uploadLocalSegments
        )
    }

    func testCloudReconciliationExhaustionDiscardsEmptyDesktopSessions() {
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            source: ConversationSource.desktop.rawValue,
            retryCount: 4,
            finalizationStrategy: .cloudReconcile
        )

        XCTAssertEqual(
            ConversationFinalizationService.cloudReconciliationExhaustionAction(
                session: session,
                segmentCount: 0
            ),
            .discardEmptyDesktopSession
        )
    }

    func testExhaustedEmptyDesktopCloudSessionIsDeletedInsteadOfFailed() async throws {
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: ConversationSource.desktop.rawValue,
            finalizationStrategy: .cloudReconcile
        )
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        for _ in 0..<4 {
            try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
        }

        let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let session = try XCTUnwrap(storedSession)

        let handled = try await ConversationFinalizationService.shared.resolveExhaustedCloudReconciliation(
            session: session,
            sessionId: sessionId
        )

        XCTAssertTrue(handled)
        let deletedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
        XCTAssertNil(deletedSession)
    }

    func testCloudReconciliationExhaustionReportsEmptyNonDesktopSessions() {
        let session = TranscriptionSessionRecord(
            startedAt: Date(timeIntervalSince1970: 1_700_000_000),
            source: ConversationSource.omi.rawValue,
            retryCount: 4,
            finalizationStrategy: .cloudReconcile
        )

        XCTAssertEqual(
            ConversationFinalizationService.cloudReconciliationExhaustionAction(
                session: session,
                segmentCount: 0
            ),
            .reportFailure
        )
    }

    func testReconciliationFailureDiagnosticsExposeRecoveryInputs() {
        let now = Date(timeIntervalSince1970: 1_700_000_000)
        let session = TranscriptionSessionRecord(
            startedAt: now.addingTimeInterval(-120),
            finishedAt: now.addingTimeInterval(-60),
            source: ConversationSource.desktop.rawValue,
            inputDeviceName: "Built-in Microphone",
            status: .failed,
            retryCount: 5,
            finalizationStrategy: .cloudReconcile,
            finalizationReason: .userStop,
            finalizationStartedAt: now.addingTimeInterval(-30)
        )

        let diagnostics = ReconciliationFailureDiagnostics(
            session: session,
            segmentCount: 2,
            retryCount: 5,
            maxRetries: 5,
            maxLocalFallbackRetries: 3
        )

        XCTAssertEqual(diagnostics.sessionStatus, "failed")
        XCTAssertEqual(diagnostics.finalizationReason, "user_stop")
        XCTAssertTrue(diagnostics.hasFinishedAt)
        XCTAssertTrue(diagnostics.hasInputDeviceName)
        XCTAssertEqual(diagnostics.hasLocalSegments, true)
        XCTAssertEqual(diagnostics.sessionDurationSeconds, 60)
        XCTAssertTrue(diagnostics.localFallbackAvailable)
        XCTAssertEqual(diagnostics.localFallbackRetriesRemaining, 3)
    }

    func testCompactsOversizedLocalUploadWithoutDroppingText() {
        let segments = (0..<750).map { index in
            APIClient.UploadSegment(
                text: "segment-\(index)",
                speaker: index.isMultiple(of: 2) ? "SPEAKER_00" : "SPEAKER_01",
                speaker_id: index.isMultiple(of: 2) ? 0 : 1,
                is_user: index.isMultiple(of: 2),
                person_id: nil,
                start: Double(index),
                end: Double(index) + 0.5
            )
        }

        let compacted = ConversationFinalizationService.compactSegmentsForBackendLimit(segments)

        XCTAssertEqual(compacted.count, 500)
        XCTAssertEqual(compacted.first?.start, 0)
        XCTAssertEqual(compacted.last?.end, 749.5)
        let compactedText = compacted.map(\.text).joined(separator: " ")
        for index in 0..<750 {
            XCTAssertTrue(compactedText.contains("segment-\(index)"))
        }
        XCTAssertTrue(compacted.contains { $0.speaker == "MIXED" })
    }

    func testCompactionLeavesBackendSizedUploadsUnchanged() {
        let segments = (0..<3).map { index in
            APIClient.UploadSegment(
                text: "segment-\(index)",
                speaker: "SPEAKER_00",
                speaker_id: 0,
                is_user: true,
                person_id: "person-1",
                start: Double(index),
                end: Double(index) + 0.5
            )
        }

        let compacted = ConversationFinalizationService.compactSegmentsForBackendLimit(segments)

        XCTAssertEqual(compacted.count, segments.count)
        XCTAssertEqual(compacted.map(\.text), segments.map(\.text))
        XCTAssertEqual(compacted.map(\.speaker), segments.map(\.speaker))
        XCTAssertEqual(compacted.map(\.person_id), segments.map(\.person_id))
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
