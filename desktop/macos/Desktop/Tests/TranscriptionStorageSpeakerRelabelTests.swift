import XCTest

@testable import Omi_Computer

/// On-device diarization can decide, a few sentences in, that the provisional "You" was the
/// other person in the room. The stored rows of the current session must swap with it in
/// one statement — a naive two-step update would map 0→1 and then 1→0 back again.
final class TranscriptionStorageSpeakerRelabelTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "transcription-storage-relabel-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDir =
      appSupport
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

  func testSwapRelabelMovesBothSpeakersOnceAndLeavesOthersAlone() async throws {
    let storage = TranscriptionStorage.shared
    let sessionId = try await storage.startSession(source: "desktop")
    let otherSession = try await storage.startSession(source: "desktop")
    _ = try await storage.upsertSegment(
      sessionId: sessionId, backendSegmentId: "a", speaker: 0, text: "provisional you",
      startTime: 0, endTime: 2, isUser: true, speakerLabel: "SPEAKER_00")
    _ = try await storage.upsertSegment(
      sessionId: sessionId, backendSegmentId: "b", speaker: 1, text: "the real user",
      startTime: 2, endTime: 5, isUser: false, personId: "person-guess", speakerLabel: "SPEAKER_01")
    _ = try await storage.upsertSegment(
      sessionId: sessionId, backendSegmentId: "c", speaker: 2, text: "someone on the call",
      startTime: 5, endTime: 7, isUser: false, speakerLabel: "SPEAKER_02")
    _ = try await storage.upsertSegment(
      sessionId: otherSession, backendSegmentId: "d", speaker: 0, text: "another session",
      startTime: 0, endTime: 1, isUser: true, speakerLabel: "SPEAKER_00")

    let moved = try await storage.relabelSpeakers(
      sessionId: sessionId,
      relabels: [
        0: LocalSpeakerRegistry.Resolution(speakerId: 1, isUser: false),
        1: LocalSpeakerRegistry.Resolution(speakerId: 0, isUser: true),
      ])

    XCTAssertEqual(moved, 2)
    let rows = try await storage.getSegments(sessionId: sessionId)
    let byId = Dictionary(rows.map { ($0.segmentId ?? "", $0) }, uniquingKeysWith: { first, _ in first })
    XCTAssertEqual(byId["a"]?.speaker, 1)
    XCTAssertEqual(byId["a"]?.speakerLabel, "SPEAKER_01")
    XCTAssertEqual(byId["a"]?.isUser, false)
    XCTAssertEqual(byId["b"]?.speaker, 0)
    XCTAssertEqual(byId["b"]?.speakerLabel, "SPEAKER_00")
    XCTAssertEqual(byId["b"]?.isUser, true)
    XCTAssertNil(byId["b"]?.personId, "a row that became the user drops its person guess")
    XCTAssertEqual(byId["c"]?.speaker, 2)
    XCTAssertEqual(byId["c"]?.isUser, false)

    let untouched = try await storage.getSegments(sessionId: otherSession)
    XCTAssertEqual(untouched.first?.speaker, 0)
    XCTAssertEqual(untouched.first?.isUser, true)
  }

  func testEmptyRelabelIsANoOp() async throws {
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    let moved = try await TranscriptionStorage.shared.relabelSpeakers(sessionId: sessionId, relabels: [:])
    XCTAssertEqual(moved, 0)
  }
}
