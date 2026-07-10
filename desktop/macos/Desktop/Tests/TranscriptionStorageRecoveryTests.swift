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

    func testBackendHydratesCompletedLocalSegmentUploadShellEvenWhenLocalTimestampIsNewer() async throws {
        let backendId = "backend-conversation-local-segments"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        try await TranscriptionStorage.shared.updateStarred(id: sessionId, starred: true)
        try await TranscriptionStorage.shared.updateFolderByBackendId(backendId, folderId: "local-folder")
        try await TranscriptionStorage.shared.deleteByBackendId(backendId)

        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)
        XCTAssertTrue(localShell.backendSynced)
        XCTAssertEqual(localShell.finalizationStrategy, .localSegments)
        XCTAssertEqual(localShell.title ?? "", "")
        XCTAssertEqual(localShell.overview ?? "", "")

        let serverConversation = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "Processed backend title",
            overview: "Processed backend overview",
            starred: false,
            folderId: "server-folder"
        )

        let result = try await TranscriptionStorage.shared.upsertFromServerConversation(serverConversation)

        XCTAssertEqual(result.sessionId, sessionId)
        XCTAssertTrue(result.changed)

        let storedHydrated = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let hydrated = try XCTUnwrap(storedHydrated)
        XCTAssertEqual(hydrated.title, "Processed backend title")
        XCTAssertEqual(hydrated.overview, "Processed backend overview")
        XCTAssertTrue(hydrated.starred, "Hydration must not erase newer local star mutations")
        XCTAssertEqual(hydrated.folderId, "local-folder", "Hydration must not erase newer local folder mutations")
        XCTAssertTrue(hydrated.deleted, "Hydration must not resurrect locally deleted conversations")
    }

    func testBackendHydratesCompletedCloudReconcileShellEvenWhenLocalTimestampIsNewer() async throws {
        let backendId = "backend-conversation-cloud-reconcile"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .cloudReconcile,
            segmentText: "cloud transcript segment"
        )
        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)

        let serverConversation = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "Processed cloud title",
            overview: "Processed cloud overview",
            starred: false,
            folderId: nil
        )

        let result = try await TranscriptionStorage.shared.upsertFromServerConversation(serverConversation)

        XCTAssertTrue(result.changed)
        let storedHydrated = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let hydrated = try XCTUnwrap(storedHydrated)
        XCTAssertEqual(hydrated.title, "Processed cloud title")
        XCTAssertEqual(hydrated.overview, "Processed cloud overview")
    }

    func testEmptyBackendStructuredDataDoesNotChurnNewerLocalShell() async throws {
        let backendId = "backend-conversation-empty-structured"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)

        let serverConversation = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "",
            overview: "",
            starred: false,
            folderId: nil
        )

        let result = try await TranscriptionStorage.shared.upsertFromServerConversation(serverConversation)

        XCTAssertFalse(result.changed)
        let storedStillShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let stillShell = try XCTUnwrap(storedStillShell)
        XCTAssertEqual(stillShell.title ?? "", "")
        XCTAssertEqual(stillShell.overview ?? "", "")
    }

    func testLocallyEditedTitleStillAllowsMissingBackendFieldsToHydrate() async throws {
        let backendId = "backend-conversation-local-title"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        try await TranscriptionStorage.shared.updateTitleByBackendId(backendId, title: "Local title edit")
        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)

        let serverConversation = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "Backend title",
            overview: "Backend overview",
            starred: false,
            folderId: nil
        )

        let result = try await TranscriptionStorage.shared.upsertFromServerConversation(serverConversation)

        XCTAssertTrue(result.changed)
        let storedPreserved = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let preserved = try XCTUnwrap(storedPreserved)
        XCTAssertEqual(preserved.title, "Local title edit")
        XCTAssertEqual(preserved.overview, "Backend overview")
    }

    func testUnknownRevisionEmptyProjectionDoesNotBlockLaterStructuredHydration() async throws {
        let backendId = "backend-conversation-json-array-hydration"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        let storedShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let shell = try XCTUnwrap(storedShell)

        let emptyStructured = makeServerConversation(
            id: backendId,
            createdAt: shell.startedAt.addingTimeInterval(-60),
            startedAt: shell.startedAt,
            finishedAt: shell.updatedAt.addingTimeInterval(60),
            title: "",
            overview: "",
            starred: false,
            folderId: nil
        )
        let emptyResult = try await TranscriptionStorage.shared.upsertFromServerConversation(emptyStructured)
        XCTAssertFalse(emptyResult.changed)
        let storedEmpty = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let empty = try XCTUnwrap(storedEmpty)
        XCTAssertNil(empty.actionItemsJson)

        try await TranscriptionStorage.shared.updateTitleByBackendId(backendId, title: "Local title edit")
        let storedLocalMutation = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localMutation = try XCTUnwrap(storedLocalMutation)

        let hydratedStructured = makeServerConversation(
            id: backendId,
            createdAt: shell.startedAt.addingTimeInterval(-60),
            startedAt: shell.startedAt,
            finishedAt: localMutation.updatedAt.addingTimeInterval(-60),
            title: "Backend title",
            overview: "Backend overview",
            starred: false,
            folderId: nil,
            actionItems: [
                ActionItem(description: "Follow up", completed: false, deleted: false)
            ]
        )

        let hydratedResult = try await TranscriptionStorage.shared.upsertFromServerConversation(hydratedStructured)

        XCTAssertTrue(hydratedResult.changed)
        let storedHydrated = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let hydrated = try XCTUnwrap(storedHydrated)
        XCTAssertEqual(hydrated.title, "Local title edit")
        XCTAssertEqual(hydrated.overview, "Backend overview")
        XCTAssertNotEqual(hydrated.actionItemsJson, "[]")
        XCTAssertTrue(hydrated.actionItemsJson?.contains("Follow up") ?? false)
    }

    func testDetailSegmentsHydrateEvenWhenSessionRowIsSkippedAsLocallyNewer() async throws {
        let backendId = "backend-conversation-detail-segments"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        try await TranscriptionStorage.shared.updateTitleByBackendId(backendId, title: "Local title edit")
        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)

        let serverConversation = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "",
            overview: "",
            starred: false,
            folderId: nil,
            transcriptSegments: [
                TranscriptSegment(
                    id: "backend-segment-1",
                    backendId: "backend-segment-1",
                    text: "backend enriched segment",
                    speaker: "SPEAKER_01",
                    isUser: true,
                    personId: "person-1",
                    start: 0,
                    end: 1
                )
            ],
            transcriptSegmentsIncluded: true
        )

        let syncedId = try await TranscriptionStorage.shared.syncServerConversation(serverConversation)

        XCTAssertEqual(syncedId, sessionId)
        let storedPreserved = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let preserved = try XCTUnwrap(storedPreserved)
        XCTAssertEqual(preserved.title, "Local title edit")
        let storedBundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: sessionId)
        let bundle = try XCTUnwrap(storedBundle)
        XCTAssertEqual(bundle.segments.count, 1)
        XCTAssertEqual(bundle.segments[0].segmentId, "backend-segment-1")
        XCTAssertEqual(bundle.segments[0].speakerLabel, "SPEAKER_01")
        XCTAssertTrue(bundle.segments[0].isUser)
        XCTAssertEqual(bundle.segments[0].personId, "person-1")
    }

    func testDetailSegmentHydrationPreservesExistingSpeakerAssignment() async throws {
        let backendId = "backend-conversation-preserve-speaker-assignment"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local transcript segment"
        )
        let storedLocalShell = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let localShell = try XCTUnwrap(storedLocalShell)

        let initialDetail = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "",
            overview: "",
            starred: false,
            folderId: nil,
            transcriptSegments: [
                TranscriptSegment(
                    id: "backend-segment-1",
                    backendId: "backend-segment-1",
                    text: "backend enriched segment",
                    speaker: "SPEAKER_01",
                    isUser: true,
                    personId: "person-backend",
                    start: 0,
                    end: 1
                )
            ],
            transcriptSegmentsIncluded: true
        )
        _ = try await TranscriptionStorage.shared.syncServerConversation(initialDetail)
        try await TranscriptionStorage.shared.updateSegmentSpeakerAssignment(
            backendConversationId: backendId,
            segmentIds: ["backend-segment-1"],
            personId: "person-local",
            isUser: false
        )

        let staleDetail = makeServerConversation(
            id: backendId,
            createdAt: localShell.startedAt.addingTimeInterval(-60),
            startedAt: localShell.startedAt,
            finishedAt: localShell.updatedAt.addingTimeInterval(-60),
            title: "",
            overview: "",
            starred: false,
            folderId: nil,
            transcriptSegments: [
                TranscriptSegment(
                    id: "backend-segment-1",
                    backendId: "backend-segment-1",
                    text: "backend refreshed text",
                    speaker: "SPEAKER_02",
                    isUser: false,
                    personId: nil,
                    start: 0,
                    end: 1
                )
            ],
            transcriptSegmentsIncluded: true
        )

        _ = try await TranscriptionStorage.shared.syncServerConversation(staleDetail)

        let storedBundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: sessionId)
        let bundle = try XCTUnwrap(storedBundle)
        XCTAssertEqual(bundle.segments.count, 1)
        XCTAssertEqual(bundle.segments[0].text, "backend refreshed text")
        XCTAssertEqual(bundle.segments[0].speakerLabel, "SPEAKER_02")
        XCTAssertFalse(bundle.segments[0].isUser)
        XCTAssertEqual(bundle.segments[0].personId, "person-local")
    }

    func testServerRevisionReplacesStaleMetadataWithoutDowngradingCachedDetail() async throws {
        let backendId = "backend-versioned-cache"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local segment"
        )
        let created = Date(timeIntervalSince1970: 100)
        let revision1 = Date(timeIntervalSince1970: 1_000)
        let revision2 = Date(timeIntervalSince1970: 2_000)

        let detail = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: revision1,
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "First server title",
            overview: "First summary",
            starred: false,
            folderId: nil,
            transcriptSegments: [
                TranscriptSegment(
                    id: "segment-1",
                    backendId: "segment-1",
                    text: "canonical transcript",
                    speaker: "SPEAKER_00",
                    isUser: true,
                    personId: nil,
                    start: 0,
                    end: 1
                )
            ],
            transcriptSegmentsIncluded: true
        )
        _ = try await TranscriptionStorage.shared.syncServerConversation(detail)

        let newerListProjection = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: revision2,
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "Newer server title",
            overview: "Processing finished",
            starred: true,
            folderId: "work"
        )
        _ = try await TranscriptionStorage.shared.syncServerConversation(newerListProjection)

        let storedRecord = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let record = try XCTUnwrap(storedRecord)
        XCTAssertEqual(record.serverUpdatedAt, revision2)
        XCTAssertEqual(record.cacheCompleteness, .detail)
        XCTAssertEqual(record.title, "Newer server title")
        XCTAssertEqual(record.overview, "Processing finished")
        XCTAssertTrue(record.starred)
        XCTAssertEqual(record.folderId, "work")
        let storedDetail = try await TranscriptionStorage.shared.getCachedConversation(id: backendId)
        let cachedDetail = try XCTUnwrap(storedDetail)
        XCTAssertEqual(cachedDetail.transcriptSegments.map(\.text), ["canonical transcript"])
        XCTAssertTrue(cachedDetail.transcriptSegmentsIncluded)
    }

    func testOlderServerRevisionCannotRegressCachedConversation() async throws {
        let backendId = "backend-version-ordering"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local segment"
        )
        let created = Date(timeIntervalSince1970: 100)
        let newest = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: Date(timeIntervalSince1970: 3_000),
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "Newest",
            overview: "Newest summary",
            starred: true,
            folderId: "new-folder"
        )
        _ = try await TranscriptionStorage.shared.syncServerConversation(newest)
        let stale = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: Date(timeIntervalSince1970: 2_000),
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "Stale",
            overview: "Stale summary",
            starred: false,
            folderId: nil
        )

        _ = try await TranscriptionStorage.shared.syncServerConversation(stale)

        let storedRecord = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let record = try XCTUnwrap(storedRecord)
        XCTAssertEqual(record.title, "Newest")
        XCTAssertEqual(record.overview, "Newest summary")
        XCTAssertTrue(record.starred)
        XCTAssertEqual(record.folderId, "new-folder")
    }

    func testOlderDetailProjectionAddsTranscriptWithoutRegressingNewerListMetadata() async throws {
        let backendId = "backend-older-detail"
        let sessionId = try await createCompletedShell(
            backendId: backendId,
            strategy: .localSegments,
            segmentText: "local segment"
        )
        let created = Date(timeIntervalSince1970: 100)
        let newestRevision = Date(timeIntervalSince1970: 3_000)
        let newestList = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: newestRevision,
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "Newest title",
            overview: "Newest summary",
            starred: true,
            folderId: "new-folder"
        )
        _ = try await TranscriptionStorage.shared.syncServerConversation(newestList)
        let olderDetail = makeServerConversation(
            id: backendId,
            createdAt: created,
            updatedAt: Date(timeIntervalSince1970: 2_000),
            startedAt: created,
            finishedAt: created.addingTimeInterval(60),
            title: "Stale title",
            overview: "Stale summary",
            starred: false,
            folderId: nil,
            transcriptSegments: [
                TranscriptSegment(
                    id: "segment-1",
                    backendId: "segment-1",
                    text: "detail transcript",
                    speaker: "SPEAKER_00",
                    isUser: true,
                    personId: nil,
                    start: 0,
                    end: 1
                )
            ],
            transcriptSegmentsIncluded: true
        )

        _ = try await TranscriptionStorage.shared.syncServerConversation(olderDetail)

        let storedRecord = try await TranscriptionStorage.shared.getSession(id: sessionId)
        let record = try XCTUnwrap(storedRecord)
        XCTAssertEqual(record.serverUpdatedAt, newestRevision)
        XCTAssertEqual(record.title, "Newest title")
        XCTAssertEqual(record.overview, "Newest summary")
        XCTAssertTrue(record.starred)
        XCTAssertEqual(record.folderId, "new-folder")
        XCTAssertEqual(record.cacheCompleteness, .detail)
        let storedDetail = try await TranscriptionStorage.shared.getCachedConversation(id: backendId)
        let detail = try XCTUnwrap(storedDetail)
        XCTAssertEqual(detail.transcriptSegments.map(\.text), ["detail transcript"])
    }

    private func createCompletedShell(
        backendId: String,
        strategy: TranscriptionFinalizationStrategy,
        segmentText: String
    ) async throws -> Int64 {
        let sessionId = try await TranscriptionStorage.shared.startSession(
            source: ConversationSource.desktop.rawValue,
            finalizationStrategy: strategy
        )
        try await TranscriptionStorage.shared.appendSegment(
            sessionId: sessionId,
            speaker: 0,
            text: segmentText,
            startTime: 0,
            endTime: 1
        )
        try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
        try await TranscriptionStorage.shared.markSessionCompleted(
            id: sessionId,
            backendId: backendId,
            conversationStatus: .completed
        )
        return sessionId
    }

    private func makeServerConversation(
        id: String,
        createdAt: Date,
        updatedAt: Date? = nil,
        startedAt: Date,
        finishedAt: Date,
        title: String,
        overview: String,
        starred: Bool,
        folderId: String?,
        actionItems: [ActionItem] = [],
        events: [Event] = [],
        transcriptSegments: [TranscriptSegment] = [],
        transcriptSegmentsIncluded: Bool = false
    ) -> ServerConversation {
        ServerConversation(
            id: id,
            createdAt: createdAt,
            updatedAt: updatedAt,
            startedAt: startedAt,
            finishedAt: finishedAt,
            structured: Structured(
                title: title,
                overview: overview,
                emoji: "",
                category: "other",
                actionItems: actionItems,
                events: events
            ),
            transcriptSegments: transcriptSegments,
            transcriptSegmentsIncluded: transcriptSegmentsIncluded,
            geolocation: nil,
            photos: [],
            appsResults: [],
            source: .desktop,
            language: "en",
            status: .completed,
            discarded: false,
            deleted: false,
            isLocked: false,
            starred: starred,
            folderId: folderId,
            inputDeviceName: nil,
            deferred: false
        )
    }
}
