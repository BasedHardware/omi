import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

final class ClientCaptureRefactorTests: XCTestCase {
  func testExplicitOwnerAndRetractionWithLegacyFallback() {
    XCTAssertEqual(ResolvedSpeakerLabel(personID: nil, isUser: true, retracted: false).liveMapValue, "user")
    XCTAssertFalse(ResolvedSpeakerLabel(personID: "user", isUser: false, retracted: false).isUser)
    let retracted = ResolvedSpeakerLabel(personID: "", isUser: true, retracted: true)
    XCTAssertNil(retracted.liveMapValue)
    XCTAssertFalse(retracted.isUser)
    let segment = SpeakerSegment(segmentId: "s", speaker: 1, text: "synthetic", start: 0, end: 1)
    let owner = ResolvedSpeakerLabel(personID: "user", isUser: nil, retracted: false).apply(to: segment)
    XCTAssertEqual(
      SpeakerLabelFormatter(names: [:]).label(isUser: owner.isUser, personId: owner.personId, speakerId: 1), "You")
    let explicitOther = ResolvedSpeakerLabel(personID: "user", isUser: false, retracted: false).apply(to: owner)
    XCTAssertEqual(
      SpeakerLabelFormatter(names: [:]).label(
        isUser: explicitOther.isUser,
        personId: explicitOther.personId, speakerId: 1), "Speaker 2")
    let cleared = retracted.apply(to: owner)
    XCTAssertFalse(cleared.isUser)
    XCTAssertNil(cleared.personId)
  }

  func testLabelsJoinOnlyOnSegmentIdentityAndServerResolutionWinsAutomatic() {
    var local = record(id: "old", isUser: true)
    var incoming = record(id: "new", person: "resolved")
    XCTAssertEqual(ServerSegmentLabelMerge.merge(incoming, existing: local).personId, "resolved")
    incoming.segmentId = "old"
    XCTAssertFalse(ServerSegmentLabelMerge.merge(incoming, existing: local).isUser)
    local.speakerLabelSource = "manual"
    XCTAssertTrue(ServerSegmentLabelMerge.merge(incoming, existing: local).isUser)
    local.segmentId = nil
    incoming.segmentId = nil
    XCTAssertEqual(ServerSegmentLabelMerge.merge(incoming, existing: local).personId, "resolved")
  }

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

  func testBoundaryEvidenceHasStableIdentityOnEndAndNewIdentityForBackToBackCalls() throws {
    var evidence = MeetingBoundaryEvidence()
    let now = Date(timeIntervalSince1970: 100)
    let first = evidence.observe(active: true, callChanged: false, now: now, makeID: { "first" })
    XCTAssertEqual(first.count, 1)
    XCTAssertTrue(evidence.observe(active: true, callChanged: false, now: now).isEmpty)
    let changed = evidence.observe(
      active: true, callChanged: true, now: now.addingTimeInterval(60), makeID: { "second" })
    XCTAssertEqual(changed.map(\.externalID), ["first", "second"])
    XCTAssertEqual(changed.first?.endedAt, now.addingTimeInterval(60))
    let ended = evidence.observe(active: false, callChanged: false, now: now.addingTimeInterval(120))
    XCTAssertEqual(ended.first?.externalID, "second")
    XCTAssertNil(evidence.active)
    let wire = try JSONSerialization.jsonObject(with: JSONEncoder().encode(ended)) as? [[String: Any]]
    XCTAssertEqual(wire?.first?["kind"] as? String, "desktop_meeting")
    XCTAssertNotNil(wire?.first?["ended_at"])
    // Evidence has no dependency on the local boundary decision.
    XCTAssertEqual(
      MeetingConversationBoundaryPolicy.transition(previousRole: .ambient, meetingActive: true)?.nextRole, .meeting)
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

  private func record(id: String, isUser: Bool = false, person: String? = nil) -> TranscriptionSegmentRecord {
    TranscriptionSegmentRecord(
      sessionId: 1, speaker: 0, text: "synthetic", startTime: 0, endTime: 1,
      segmentOrder: 0, segmentId: id, isUser: isUser, personId: person)
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
  func testStoredRefreshNeverGraftsByPositionAndServerReplacesAutomaticLabels() async throws {
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
      conversation(segment("old", person: nil)),
      sessionId: session, useSegmentIdentity: true)
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: session, speakerId: 1, personId: "user", useExplicitOwner: true)
    try await storage.upsertSegmentsFromServerConversation(
      conversation(segment("new", person: "resolved")),
      sessionId: session, useSegmentIdentity: true)
    var rows = try await storage.getSegments(sessionId: session)
    XCTAssertFalse(rows[0].isUser)
    XCTAssertEqual(rows[0].personId, "resolved")
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: session, speakerId: 1, personId: "user",
      automatic: true, useExplicitOwner: true)
    try await storage.upsertSegmentsFromServerConversation(
      conversation(segment("new", person: "corrected")),
      sessionId: session, useSegmentIdentity: true)
    rows = try await storage.getSegments(sessionId: session)
    XCTAssertFalse(rows[0].isUser)
    XCTAssertEqual(rows[0].personId, "corrected")
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: session, speakerId: 1, personId: "user", useExplicitOwner: true)
    try await storage.upsertSegmentsFromServerConversation(
      conversation(segment("new", person: "corrected")),
      sessionId: session, useSegmentIdentity: true)
    rows = try await storage.getSegments(sessionId: session)
    XCTAssertTrue(rows[0].isUser)
    XCTAssertEqual(rows[0].speakerLabelSource, "manual")
  }

  func testLiveOwnerPersistsAndRetractionClearsAutomaticButNotManual() async throws {
    let storage = TranscriptionStorage.shared
    let id = try await storage.startSession(source: "desktop")
    guard let db = await RewindDatabase.shared.getDatabaseQueue() else { return XCTFail("missing database") }
    try await db.write { database in
      let automatic = TranscriptionSegmentRecord(
        sessionId: id, speaker: 1, text: "synthetic", startTime: 0,
        endTime: 1, segmentOrder: 0, segmentId: "auto")
      var manual = TranscriptionSegmentRecord(
        sessionId: id, speaker: 1, text: "synthetic", startTime: 1,
        endTime: 2, segmentOrder: 1, segmentId: "manual", personId: "manual-person")
      manual.speakerLabelSource = "manual"
      try automatic.insert(database)
      try manual.insert(database)
    }
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: id, speakerId: 1, personId: "", isUser: true,
      automatic: true, useExplicitOwner: true)
    var rows = try await storage.getSegments(sessionId: id)
    XCTAssertTrue(rows[0].isUser)
    XCTAssertNil(rows[0].personId)
    XCTAssertEqual(rows[1].personId, "manual-person")
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: id, speakerId: 1, personId: "", isUser: false,
      retracted: true, automatic: true, useExplicitOwner: true)
    rows = try await storage.getSegments(sessionId: id)
    XCTAssertFalse(rows[0].isUser)
    XCTAssertNil(rows[0].personId)
    XCTAssertEqual(rows[1].personId, "manual-person")
    _ = try await storage.updateLiveSpeakerAssignment(
      sessionId: id, speakerId: 1, personId: "user", useExplicitOwner: true)
    rows = try await storage.getSegments(sessionId: id)
    XCTAssertTrue(rows.allSatisfy(\.isUser))
  }
}
