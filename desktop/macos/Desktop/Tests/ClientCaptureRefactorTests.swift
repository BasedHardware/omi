import Foundation
import XCTest

@testable import Omi_Computer

final class ClientCaptureRefactorTests: XCTestCase {
  func testContinuationPreservesEveryAlternatingSpeakerAndWireSessionIdentity() throws {
    let segments = (0..<1201).map { index in
      APIClient.UploadSegment(
        text: "synthetic", speaker: "SPEAKER_\(index % 2)", speaker_id: index % 2,
        is_user: index.isMultiple(of: 2), person_id: index.isMultiple(of: 2) ? nil : "person",
        start: Double(index), end: Double(index) + 0.5)
    }
    let request = APIClient.CreateConversationFromSegmentsRequest(
      transcript_segments: segments, source: "desktop",
      started_at: "2026-01-01T00:00:00Z", finished_at: "2026-01-01T01:00:00Z", language: "en",
      client_conversation_id: "session", conversation_role: "meeting", conversation_finalization_reason: nil,
      client_processing: nil, captureEvidence: nil)
    let chunks = SegmentContinuationUpload.chunks(segments)
    XCTAssertEqual(chunks.map(\.count), [500, 500, 201])
    var restored: [[String: Any]] = []
    for (index, chunk) in chunks.enumerated() {
      let data = try JSONEncoder().encode(
        SegmentContinuationUpload.Payload(
          request: request, segments: chunk,
          index: index, count: chunks.count))
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      XCTAssertEqual(json["client_session_id"] as? String, "session")
      XCTAssertEqual(json["chunk_index"] as? Int, index)
      XCTAssertEqual(json["chunk_count"] as? Int, 3)
      restored += try XCTUnwrap(json["transcript_segments"] as? [[String: Any]])
    }
    XCTAssertEqual(restored.count, segments.count)
    for (index, segment) in restored.enumerated() {
      XCTAssertEqual(segment["speaker_id"] as? Int, index % 2)
      XCTAssertEqual(segment["start"] as? Double, Double(index))
      XCTAssertEqual(segment["is_user"] as? Bool, index.isMultiple(of: 2))
    }
  }

  func testContinuationMissingFinishUsesLastSegmentEndAndPreservesExplicitFinish() {
    let start = Date(timeIntervalSince1970: 100)
    XCTAssertEqual(
      SegmentContinuationUpload.finishedAt(
        startedAt: start, finishedAt: nil,
        segmentEnds: [0.5, 3, 2, .nan]), start.addingTimeInterval(3))
    XCTAssertEqual(
      SegmentContinuationUpload.finishedAt(
        startedAt: start, finishedAt: start.addingTimeInterval(5),
        segmentEnds: [3]), start.addingTimeInterval(5))
    XCTAssertNil(SegmentContinuationUpload.finishedAt(startedAt: start, finishedAt: nil, segmentEnds: []))
  }
}

final class ClientCaptureRefactorStorageTests: XCTestCase {
  private var owner = ""
  override func setUp() async throws {
    owner = "l5-tests-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = owner
    await RewindDatabase.shared.configure(userId: owner)
    try await RewindDatabase.shared.initialize()
  }
  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    guard !owner.isEmpty else { return }
    let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("Omi").appendingPathComponent(owner)
    try? FileManager.default.removeItem(at: root)
  }
  func testStoredRefreshPreservesTheLegacyPositionFallback() async throws {
    let storage = TranscriptionStorage.shared
    let session = try await storage.startSession(source: "desktop")
    func segment(_ key: String, person: String?) -> TranscriptSegment {
      TranscriptSegment(
        id: key, backendId: key, text: "synthetic", speaker: "SPEAKER_01",
        isUser: false, personId: person, start: 0, end: 1)
    }
    func conversation(_ segment: TranscriptSegment) -> ServerConversation {
      ServerConversation(
        id: "conversation", createdAt: Date(), startedAt: Date(), finishedAt: Date(),
        structured: Structured(title: "", overview: "", emoji: "", category: "other", actionItems: [], events: []),
        transcriptSegments: [segment], transcriptSegmentsIncluded: true, geolocation: nil, photos: [], appsResults: [],
        source: .desktop, language: "en", status: .completed, discarded: false, deleted: false, isLocked: false,
        starred: false, folderId: nil, inputDeviceName: nil, deferred: false)
    }
    try await storage.upsertSegmentsFromServerConversation(
      conversation(segment("old", person: nil)), sessionId: session)
    try await storage.updateLiveSpeakerAssignment(sessionId: session, speakerId: 1, personId: "manual-person")
    var rows = try await storage.getSegments(sessionId: session)
    XCTAssertEqual(rows.first?.personId, "manual-person")
    XCTAssertEqual(rows.first?.speakerLabelSource, "manual")

    try await storage.upsertSegmentsFromServerConversation(
      conversation(segment("new", person: "resolved")), sessionId: session)
    rows = try await storage.getSegments(sessionId: session)
    XCTAssertEqual(rows.first?.segmentId, "new")
    XCTAssertEqual(rows.first?.personId, "manual-person")
  }
}
