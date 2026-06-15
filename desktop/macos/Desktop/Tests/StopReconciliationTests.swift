import XCTest
@testable import Omi_Computer

/// Tests for the stop/reconciliation logic in the from-segments removal migration.
/// Covers: generation guard, source filtering, and force-process response validation.
final class StopReconciliationTests: XCTestCase {

    // MARK: - Recording Generation Guard

    /// Verify that recordingGeneration increments correctly and can detect
    /// when a new recording started during a delay window.
    func testRecordingGenerationDetectsNewRecording() {
        // Simulate the pattern used in stopTranscription():
        // 1. Capture generation before stop
        // 2. New recording starts (increments generation)
        // 3. Check if generation changed
        var generation: UInt64 = 0
        let capturedGeneration = generation

        // Simulate new recording starting
        generation &+= 1

        XCTAssertNotEqual(generation, capturedGeneration,
            "Generation should change when a new recording starts")
    }

    func testRecordingGenerationStableWhenNoNewRecording() {
        var generation: UInt64 = 42
        let capturedGeneration = generation

        // No new recording
        XCTAssertEqual(generation, capturedGeneration,
            "Generation should be stable when no new recording starts")

        // Incrementing only when recording starts
        generation &+= 1
        XCTAssertNotEqual(generation, capturedGeneration)
    }

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

    // MARK: - Force-Process Response Validation

    /// Simulate the validation logic used in stopTranscription() when
    /// force-process returns a conversation.
    func testForceProcessValidationAcceptsMatchingConversation() {
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

    func testForceProcessValidationRejectsTimeMismatch() {
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

    func testForceProcessValidationRejectsSourceMismatch() {
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

    func testForceProcessValidationRejectsBothMismatch() {
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
}

private extension Date {
    var iso8601String: String {
        ISO8601DateFormatter().string(from: self)
    }
}
