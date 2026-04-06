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

  func testTranscriptSegmentRequestEncodingIncludesStableId() throws {
    let request = APIClient.TranscriptSegmentRequest(
      id: "seg_backend_123",
      text: "Hello",
      speaker: "SPEAKER_01",
      speakerId: 1,
      isUser: false,
      personId: "person_abc",
      start: 1.25,
      end: 2.5
    )

    let data = try JSONEncoder().encode(request)
    let payload = try XCTUnwrap(
      JSONSerialization.jsonObject(with: data) as? [String: Any]
    )

    XCTAssertEqual(payload["id"] as? String, "seg_backend_123")
    XCTAssertEqual(payload["person_id"] as? String, "person_abc")
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
