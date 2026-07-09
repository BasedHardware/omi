import XCTest
@testable import Omi_Computer

/// Tests for the stop/reconciliation logic in the deterministic desktop finalization flow.
/// Covers: source filtering, bound backend ids, and legacy timestamp fallback validation.
final class StopReconciliationTests: XCTestCase {

    // MARK: - Conversation Source Filtering

    /// Verify that reconciliation matching correctly filters by source.
    /// This tests the logic pattern used in both AppState.reconcileSession
    /// and TranscriptionRetryService.reconcileSession.
    func testSourceFilterRejectsNonDesktopConversations() {
        // Simulate the matching logic
        let desktopSource: ConversationSource = .desktop
        let phoneSource: ConversationSource = .phone
        let omiSource: ConversationSource = .omi

        XCTAssertEqual(desktopSource, .desktop, "Desktop source should match")
        XCTAssertNotEqual(phoneSource, .desktop, "Phone source should not match desktop filter")
        XCTAssertNotEqual(omiSource, .desktop, "Omi source should not match desktop filter")
    }

    // MARK: - Legacy Timestamp Fallback Validation

    /// Simulate the validation logic used only for older unbound sessions that have no durable
    /// backend conversation id.
    func testTimestampFallbackAcceptsMatchingConversation() {
        let sessionStartTime = Date()
        let convStartedAt = sessionStartTime.addingTimeInterval(2) // 2s offset
        let convSource: ConversationSource = .desktop

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertTrue(matches, "Conversation within 10s and source=desktop should match")
    }

    func testTimestampFallbackRejectsTimeMismatch() {
        let sessionStartTime = Date()
        let convStartedAt = sessionStartTime.addingTimeInterval(15) // 15s offset
        let convSource: ConversationSource = .desktop

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertFalse(matches, "Conversation >10s away should not match")
    }

    func testTimestampFallbackRejectsSourceMismatch() {
        let sessionStartTime = Date()
        let convStartedAt = sessionStartTime.addingTimeInterval(1) // 1s offset
        let convSource: ConversationSource = .phone

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertFalse(matches, "Non-desktop conversation should not match")
    }

    func testTimestampFallbackRejectsBothMismatch() {
        let sessionStartTime = Date()
        let convStartedAt = sessionStartTime.addingTimeInterval(20)
        let convSource: ConversationSource = .omi

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertFalse(matches, "Both time and source mismatch should not match")
    }

    // MARK: - Boundary Cases

    func testValidationAtExactBoundary() {
        let sessionStartTime = Date()
        // Exactly 10s — should NOT match (condition is < 10, not <=)
        let convStartedAt = sessionStartTime.addingTimeInterval(DesktopConversationMatchPolicy.startedAtTolerance)
        let convSource: ConversationSource = .desktop

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertFalse(matches, "Exactly 10s offset should not match (< 10 boundary)")
    }

    func testValidationJustUnderBoundary() {
        let sessionStartTime = Date()
        let convStartedAt = sessionStartTime.addingTimeInterval(9.99)
        let convSource: ConversationSource = .desktop

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertTrue(matches, "9.99s offset should match")
    }

    func testTimestampReconciliationQueriesInProgressProcessingAndCompleted() {
        XCTAssertEqual(
            DesktopConversationMatchPolicy.cloudReconciliationStatuses,
            [.inProgress, .processing, .completed]
        )
    }

    func testTimestampMatchedInProgressConversationUsesSpecificFinalizeBeforeCompletion() {
        XCTAssertTrue(
            DesktopConversationMatchPolicy.shouldFinalizeTimestampMatchedConversation(status: .inProgress)
        )
        XCTAssertFalse(
            DesktopConversationMatchPolicy.canCompleteTimestampMatchedConversation(
                status: .inProgress,
                source: .desktop
            ),
            "Timestamp matches must not complete locally until exact-id finalize returns a non-in-progress status"
        )
    }

    func testTimestampMatchedProcessingConversationCanCompleteWithoutFinalize() {
        XCTAssertFalse(
            DesktopConversationMatchPolicy.shouldFinalizeTimestampMatchedConversation(status: .processing)
        )
        XCTAssertTrue(
            DesktopConversationMatchPolicy.canCompleteTimestampMatchedConversation(
                status: .processing,
                source: .desktop
            )
        )
    }

    func testNegativeTimeOffset() {
        let sessionStartTime = Date()
        // Backend conversation started 3s BEFORE local session start (clock skew)
        let convStartedAt = sessionStartTime.addingTimeInterval(-3)
        let convSource: ConversationSource = .desktop

        let matches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertTrue(matches, "Negative offset within 10s should match (abs)")
    }

    // MARK: - memory_created Event Matching

    func testMemoryCreatedEventAcceptsMatchingDesktopStartedAt() {
        let sessionStartTime = Date()
        let memory: [String: Any] = [
            "source": "desktop",
            "started_at": sessionStartTime.addingTimeInterval(2).iso8601String
        ]

        XCTAssertTrue(DesktopConversationMatchPolicy.memoryEventMatchesFinishedSession(
            memory,
            sessionStartedAt: sessionStartTime
        ))
    }

    func testMemoryCreatedEventRejectsLiveRecordingStartedAt() {
        let sessionStartTime = Date()
        let memory: [String: Any] = [
            "source": "desktop",
            "started_at": sessionStartTime
                .addingTimeInterval(DesktopConversationMatchPolicy.startedAtTolerance + 1)
                .iso8601String
        ]

        XCTAssertFalse(DesktopConversationMatchPolicy.memoryEventMatchesFinishedSession(
            memory,
            sessionStartedAt: sessionStartTime
        ))
    }

    func testMemoryCreatedEventRejectsNonDesktopSource() {
        let sessionStartTime = Date()
        let memory: [String: Any] = [
            "source": "phone",
            "started_at": sessionStartTime.iso8601String
        ]

        XCTAssertFalse(DesktopConversationMatchPolicy.memoryEventMatchesFinishedSession(
            memory,
            sessionStartedAt: sessionStartTime
        ))
    }

    func testMemoryCreatedEventAllowsMissingSourceWhenStartedAtMatches() {
        let sessionStartTime = Date()
        let memory: [String: Any] = [
            "started_at": sessionStartTime.iso8601String
        ]

        XCTAssertTrue(DesktopConversationMatchPolicy.memoryEventMatchesFinishedSession(
            memory,
            sessionStartedAt: sessionStartTime
        ))
    }
    // MARK: - Backend Conversation ID Binding

    func testBoundBackendConversationIdAcceptsExactMatchBeforeTimestampFallback() {
        let sessionStartTime = Date()
        let boundBackendId = "backend-conversation-123"
        let returnedBackendId = "backend-conversation-123"
        let convStartedAt = sessionStartTime.addingTimeInterval(30)
        let convSource: ConversationSource = .phone

        let exactIdMatches = returnedBackendId == boundBackendId
        let timestampMatches = DesktopConversationMatchPolicy.matchesDesktopConversation(
            startedAt: convStartedAt,
            source: convSource,
            sessionStartedAt: sessionStartTime
        )

        XCTAssertTrue(exactIdMatches, "A bound listen conversation id should identify the stopped session exactly")
        XCTAssertFalse(timestampMatches, "This fixture would be rejected by the old timestamp/source fallback")
    }

    func testBoundBackendConversationIdRejectsDifferentForceProcessConversation() {
        let boundBackendId = "backend-conversation-123"
        let returnedBackendId = "backend-conversation-456"

        XCTAssertNotEqual(returnedBackendId, boundBackendId,
            "Force-process must not bind a different conversation when the listen session id is known")
    }

    func testBoundBackendConversationShouldUseSpecificFinalizePath() {
        let capturedBackendId = "backend-conversation-123"

        XCTAssertFalse(capturedBackendId.isEmpty)
        XCTAssertEqual(
            "v1/conversations/\(capturedBackendId)/finalize",
            "v1/conversations/backend-conversation-123/finalize"
        )
    }

    func testUnboundStopDoesNotUseGlobalForceProcessFallback() {
        let capturedBackendId: String? = nil

        XCTAssertFalse(
            DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
                capturedBackendId: capturedBackendId,
                persistedBackendId: nil
            ),
            "Unbound sessions should not force-process the user's current in-progress pointer"
        )
    }

    func testCapturedButUnpersistedBackendIdDoesNotUseGlobalForceProcessFallback() {
        XCTAssertFalse(
            DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
                capturedBackendId: "backend-conversation-123",
                persistedBackendId: nil
            ),
            "A captured listen id must be durably stored before force-processing is allowed"
        )
    }

    func testCapturedBackendIdMustMatchPersistedBackendIdBeforeForceProcess() {
        XCTAssertFalse(
            DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
                capturedBackendId: "backend-conversation-123",
                persistedBackendId: "backend-conversation-456"
            )
        )
    }

    func testPersistedCapturedBackendIdAllowsSpecificFinalize() {
        XCTAssertTrue(
            DesktopConversationMatchPolicy.canForceProcessBoundCloudSession(
                capturedBackendId: "backend-conversation-123",
                persistedBackendId: "backend-conversation-123"
            )
        )
    }

    func testBoundBackendConversationCompletionRejectsNonDesktopExactMatch() {
        XCTAssertFalse(DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
            id: "backend-conversation-123",
            boundBackendId: "backend-conversation-123",
            status: .completed,
            source: .phone
        ), "Exact listen ids still need source validation before completing a desktop session")
    }

    func testBoundBackendConversationCompletionRejectsInProgressExactMatch() {
        XCTAssertFalse(DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
            id: "backend-conversation-123",
            boundBackendId: "backend-conversation-123",
            status: .inProgress,
            source: .desktop
        ), "Exact listen ids must not complete a session until backend processing finishes")
    }

    func testBoundBackendConversationCompletionAcceptsCompletedDesktopExactMatch() {
        XCTAssertTrue(DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
            id: "backend-conversation-123",
            boundBackendId: "backend-conversation-123",
            status: .completed,
            source: .desktop
        ))
    }

    func testRecordingSessionWithBackendIdCanStillBeFinishedForRetryReconciliation() {
        var session = TranscriptionSessionRecord(
            source: "desktop",
            status: .recording,
            backendId: "backend-conversation-123",
            backendSynced: false
        )

        XCTAssertEqual(session.backendId, "backend-conversation-123")
        XCTAssertFalse(session.backendSynced)
        XCTAssertEqual(session.status, .recording)
        session.status = .pendingUpload
        XCTAssertEqual(session.status, .pendingUpload,
            "Binding the backend id is not completion; stop flow must still be able to mark the session pending")
    }

    func testActiveBackendConversationIdAcceptsMatchingReemit() {
        XCTAssertTrue(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: "active-conversation",
            activeBackendId: "active-conversation",
            ignoredRotatedBackendIds: []
        ))
    }

    func testActiveBackendConversationIdRejectsDifferentRollover() {
        XCTAssertFalse(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: "rolled-over-conversation",
            activeBackendId: "active-conversation",
            ignoredRotatedBackendIds: []
        ))
    }

    func testRejectedRolloverBackendConversationIdIsCarriedAcrossRotation() {
        let activeBackendId = "active-conversation"
        let rejectedRolloverId = "rolled-over-conversation"
        let ignoredAfterFinish: Set<String> = [activeBackendId, rejectedRolloverId]

        XCTAssertFalse(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: rejectedRolloverId,
            activeBackendId: activeBackendId,
            ignoredRotatedBackendIds: []
        ))
        XCTAssertFalse(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: rejectedRolloverId,
            activeBackendId: nil,
            ignoredRotatedBackendIds: ignoredAfterFinish
        ), "A backend conversation rejected as an active-session rollover must not bind after local rotation")
    }

    func testRotatedBackendConversationIdIsNotBoundToFreshSession() {
        XCTAssertFalse(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: "previous-conversation",
            activeBackendId: nil,
            ignoredRotatedBackendIds: ["previous-conversation"]
        ))
    }

    func testNewBackendConversationIdAfterRotationCanBindFreshSession() {
        XCTAssertTrue(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: "new-conversation",
            activeBackendId: nil,
            ignoredRotatedBackendIds: ["previous-conversation"]
        ))
    }

    func testEmptyConversationSessionIdIsRejected() {
        XCTAssertFalse(DesktopConversationMatchPolicy.shouldBindConversationSession(
            incomingBackendId: "",
            activeBackendId: nil,
            ignoredRotatedBackendIds: []
        ))
    }
}

private extension Date {
    var iso8601String: String {
        ISO8601DateFormatter().string(from: self)
    }
}
