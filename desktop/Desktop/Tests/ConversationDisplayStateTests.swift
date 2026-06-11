import XCTest
@testable import Omi_Computer

/// Unit tests for `ServerConversation.displayState` / `displayTitle` /
/// `canReprocess`. The intent of these accessors is to disambiguate the four
/// reasons a conversation might lack a title — locked, processing, recoverable
/// silent-failure, and genuinely-empty — so the row UI can render an honest
/// label instead of a flat "Untitled".
final class ConversationDisplayStateTests: XCTestCase {

    // MARK: - Builders

    /// Builds a minimally-populated `ServerConversation` with overridable knobs.
    /// Keeps the tests focused on the fields that drive displayState.
    private func makeConversation(
        title: String = "",
        status: ConversationStatus = .completed,
        isLocked: Bool = false,
        segments: [TranscriptSegment] = []
    ) -> ServerConversation {
        ServerConversation(
            id: "id",
            createdAt: Date(),
            startedAt: nil,
            finishedAt: nil,
            structured: Structured(
                title: title,
                overview: "",
                emoji: "",
                category: "",
                actionItems: [],
                events: []
            ),
            transcriptSegments: segments,
            geolocation: nil,
            photos: [],
            appsResults: [],
            source: nil,
            language: nil,
            status: status,
            discarded: false,
            deleted: false,
            isLocked: isLocked,
            starred: false,
            folderId: nil,
            inputDeviceName: nil
        )
    }

    private func segment(_ text: String) -> TranscriptSegment {
        TranscriptSegment(
            id: UUID().uuidString,
            text: text,
            speaker: "SPEAKER_00",
            isUser: false,
            personId: nil,
            start: 0,
            end: 1
        )
    }

    // MARK: - Titled

    func test_completedWithTitle_returnsTitledState() {
        let conv = makeConversation(title: "Morning standup")
        if case .titled(let t) = conv.displayState {
            XCTAssertEqual(t, "Morning standup")
        } else {
            XCTFail("Expected .titled, got \(conv.displayState)")
        }
        XCTAssertEqual(conv.displayTitle, "Morning standup")
        XCTAssertFalse(conv.canReprocess)
    }

    // MARK: - Locked

    func test_lockedTakesPrecedence_overEverythingElse() {
        // Locked + has title + completed — locked still wins so the user
        // gets an honest signal that their content is gated.
        let conv = makeConversation(
            title: "Was titled before lock",
            status: .completed,
            isLocked: true,
            segments: [segment("plenty of words to look recoverable normally")]
        )
        XCTAssertEqual(conv.displayState, .locked)
        XCTAssertEqual(conv.displayTitle, "Locked")
        XCTAssertFalse(conv.canReprocess, "Reprocess shouldn't be offered while locked")
    }

    // MARK: - Processing

    func test_inProgressStatus_returnsProcessing() {
        let conv = makeConversation(status: .inProgress)
        XCTAssertEqual(conv.displayState, .processing)
        XCTAssertEqual(conv.displayTitle, "Processing…")
        XCTAssertFalse(conv.canReprocess)
    }

    func test_processingStatus_returnsProcessing() {
        let conv = makeConversation(status: .processing)
        XCTAssertEqual(conv.displayState, .processing)
    }

    func test_mergingStatus_returnsProcessing() {
        let conv = makeConversation(status: .merging)
        XCTAssertEqual(conv.displayState, .processing)
    }

    // MARK: - Failed

    func test_failedStatus_returnsFailed_andCanReprocess() {
        let conv = makeConversation(status: .failed)
        XCTAssertEqual(conv.displayState, .failed)
        XCTAssertEqual(conv.displayTitle, "Failed to process")
        XCTAssertTrue(conv.canReprocess, "User should be able to retry a failed conversation")
    }

    // MARK: - Recoverable vs empty

    func test_completedNoTitle_withSubstantialTranscript_returnsRecoverable() {
        // 5+ words in a single segment satisfies the "real content" heuristic.
        let conv = makeConversation(
            status: .completed,
            segments: [segment("hello this is a longer transcript please title me")]
        )
        XCTAssertEqual(conv.displayState, .untitledRecoverable)
        XCTAssertEqual(conv.displayTitle, "Untitled")
        XCTAssertTrue(conv.canReprocess, "Recoverable rows should expose the reprocess CTA")
    }

    func test_completedNoTitle_withShortTranscript_returnsEmpty() {
        // ≤ 4 words across the only segment — treat as ambient/accidental
        // capture. No reprocess CTA (would burn LLM tokens on noise).
        let conv = makeConversation(
            status: .completed,
            segments: [segment("hello there")]
        )
        XCTAssertEqual(conv.displayState, .untitledEmpty)
        XCTAssertEqual(conv.displayTitle, "Untitled")
        XCTAssertFalse(conv.canReprocess, "Empty rows shouldn't offer reprocess")
    }

    func test_completedNoTitle_withNoTranscript_returnsEmpty() {
        let conv = makeConversation(status: .completed, segments: [])
        XCTAssertEqual(conv.displayState, .untitledEmpty)
        XCTAssertFalse(conv.canReprocess)
    }

    func test_completedNoTitle_anyOneSegmentLongEnough_recoverable() {
        // Even if the first segment is tiny, a later substantial segment
        // promotes the conversation to recoverable.
        let conv = makeConversation(
            status: .completed,
            segments: [
                segment("um"),
                segment("ok"),
                segment("this is the substantive part of the conversation"),
            ]
        )
        XCTAssertEqual(conv.displayState, .untitledRecoverable)
        XCTAssertTrue(conv.canReprocess)
    }
}
