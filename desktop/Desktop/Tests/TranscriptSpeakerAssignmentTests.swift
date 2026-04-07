import XCTest

@testable import Omi_Computer

final class TranscriptSpeakerAssignmentTests: XCTestCase {
  func testTranscriptSegmentDecodingPreservesBackendId() throws {
    let json = """
      {
        "id": "seg_backend_123",
        "text": "Hello",
        "speaker": "SPEAKER_01",
        "is_user": false,
        "person_id": "person_abc",
        "start": 1.25,
        "end": 2.5
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)

    XCTAssertEqual(segment.id, "seg_backend_123")
    XCTAssertEqual(segment.backendId, "seg_backend_123")
    XCTAssertEqual(segment.personId, "person_abc")
  }

  func testTranscriptSegmentDecodingFallsBackToEphemeralIdWhenBackendIdMissing() throws {
    let json = """
      {
        "text": "Hello",
        "speaker": "SPEAKER_01",
        "is_user": false,
        "start": 1.25,
        "end": 2.5
      }
      """.data(using: .utf8)!

    let segment = try JSONDecoder().decode(TranscriptSegment.self, from: json)

    XCTAssertFalse(segment.id.isEmpty)
    XCTAssertNil(segment.backendId)
  }

  func testTranscriptionSegmentRecordRoundTripKeepsBackendId() {
    let record = TranscriptionSegmentRecord(
      sessionId: 1,
      speaker: 1,
      text: "Hello",
      startTime: 1.25,
      endTime: 2.5,
      segmentOrder: 0,
      segmentId: "seg_backend_123",
      speakerLabel: "SPEAKER_01",
      isUser: false,
      personId: "person_abc"
    )

    let segment = record.toTranscriptSegment()

    XCTAssertEqual(segment.id, "seg_backend_123")
    XCTAssertEqual(segment.backendId, "seg_backend_123")
    XCTAssertEqual(segment.personId, "person_abc")
  }

  // MARK: - SpeakerSegment isUser Tests

  func testSpeakerSegmentIsUserTrueWithNonZeroSpeaker() {
    // Backend can return is_user=true with speaker_id != 0 (speech profile match)
    let segment = SpeakerSegment(
      speaker: 1,
      text: "Hello from user",
      start: 0,
      end: 1,
      isUser: true
    )

    XCTAssertTrue(segment.isUser, "Segment with isUser=true should be treated as user regardless of speaker ID")
    XCTAssertEqual(segment.speaker, 1, "Speaker ID should remain 1")
  }

  func testSpeakerSegmentIsUserFalseWithZeroSpeaker() {
    // A segment from speaker 0 that isn't the user (e.g., no speech profile match)
    let segment = SpeakerSegment(
      speaker: 0,
      text: "Hello from someone else",
      start: 0,
      end: 1,
      isUser: false
    )

    XCTAssertFalse(segment.isUser, "Segment with isUser=false should not be treated as user even with speaker 0")
  }

  func testSpeakerSegmentDefaultsIsUserToFalse() {
    let segment = SpeakerSegment(
      speaker: 0,
      text: "Test",
      start: 0,
      end: 1
    )

    XCTAssertFalse(segment.isUser, "isUser should default to false")
  }

  func testAssignmentMetadataPrefersBackendIdsAndFallsBackToIndices() {
    let segments = [
      TranscriptSegment(
        id: UUID().uuidString,
        backendId: nil,
        text: "Local only",
        speaker: "SPEAKER_00",
        isUser: false,
        personId: nil,
        start: 0,
        end: 1
      ),
      TranscriptSegment(
        id: "seg_backend_123",
        backendId: "seg_backend_123",
        text: "Synced",
        speaker: "SPEAKER_01",
        isUser: false,
        personId: nil,
        start: 1,
        end: 2
      ),
      TranscriptSegment(
        id: "seg_backend_456",
        backendId: "seg_backend_456",
        text: "Also synced",
        speaker: "SPEAKER_02",
        isUser: false,
        personId: nil,
        start: 2,
        end: 3
      ),
    ]

    let assignment = ConversationDetailView.assignmentMetadata(
      for: [0, 1, 99, 2],
      in: segments
    )

    XCTAssertEqual(
      assignment.targets,
      ["#index:0", "seg_backend_123", "seg_backend_456"]
    )
    XCTAssertEqual(
      assignment.backendIds,
      ["seg_backend_123", "seg_backend_456"]
    )
    XCTAssertEqual(assignment.fallbackOrders, [0])
  }
}
