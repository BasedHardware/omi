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
}
