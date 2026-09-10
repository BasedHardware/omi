import XCTest

@testable import Omi_Computer

/// Segments and speaker relabels can outrun the DB session: `currentSessionId` is installed
/// only after the async session-creation task finishes, and on a real meeting boundary that
/// has lagged capture resume by tens of seconds. Work arriving in that window must be held
/// and flushed into the session once it exists — not silently dropped. A live meeting's
/// transcript was lost exactly this way: every segment persisted only in memory, the empty
/// session was deleted at meeting end, and nothing uploaded.
@MainActor
final class TranscriptSessionTimingPersistenceTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?
  private var state: AppState?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "transcript-session-timing-test-\(UUID().uuidString)"
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

    let state = AppState()
    state.isTranscribing = true
    self.state = state
  }

  override func tearDown() async throws {
    state?.isTranscribing = false
    state = nil
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir {
      try? FileManager.default.removeItem(at: userDir)
    }
    try await super.tearDown()
  }

  private func segment(_ text: String, speaker: Int = 0, isUser: Bool = true)
    -> TranscriptionService.BackendSegment
  {
    TranscriptionService.BackendSegment(
      id: UUID().uuidString.lowercased(),
      text: text,
      speaker: String(format: "SPEAKER_%02d", speaker),
      speaker_id: speaker,
      is_user: isUser,
      person_id: nil,
      start: 0,
      end: 1,
      translations: nil
    )
  }

  /// Simulates the session-creation task completing: a storage row is created and the app
  /// installs its id, which is where held work must flush.
  private func createAndInstallSession(_ state: AppState) async throws -> Int64 {
    let sessionId = try await TranscriptionStorage.shared.startSession(source: "desktop")
    state.currentSessionId = sessionId
    state.flushHeldTranscriptWork(sessionId: sessionId)
    return sessionId
  }

  func testSegmentsArrivingBeforeTheSessionExistsLandInTheCreatedSession() async throws {
    let state = try XCTUnwrap(state)
    state.handleBackendSegments([segment("held before the session existed")])
    XCTAssertEqual(state.totalSegmentCount, 1, "the segment still enters the live transcript")
    await state.flushTranscriptPersistence()

    let sessionId = try await createAndInstallSession(state)
    await state.flushTranscriptPersistence()

    let rows = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertEqual(rows.map(\.text), ["held before the session existed"])
    XCTAssertEqual(rows.first?.speaker, 0)
    XCTAssertEqual(rows.first?.isUser, true)
  }

  func testRelabelsArrivingBeforeTheSessionExistsApplyToTheHeldRowsInOrder() async throws {
    let state = try XCTUnwrap(state)
    state.handleBackendSegments([segment("provisional you")])
    // The diarizer bootstrap decides the mic voice was the other person — while the session
    // id is still nil, exactly as in the lost-meeting run.
    state.applyLocalSpeakerRelabels([
      0: LocalSpeakerRegistry.Resolution(speakerId: 1, isUser: false)
    ])
    await state.flushTranscriptPersistence()

    let sessionId = try await createAndInstallSession(state)
    await state.flushTranscriptPersistence()

    let rows = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertEqual(rows.map(\.text), ["provisional you"])
    XCTAssertEqual(rows.first?.speaker, 1, "the held relabel lands after the held segment's upsert")
    XCTAssertEqual(rows.first?.isUser, false)
  }

  func testSegmentsAfterTheRecordingStopsAreNotHeldForAFutureSession() async throws {
    let state = try XCTUnwrap(state)
    state.isTranscribing = false
    state.handleBackendSegments([segment("arrived after stop")])
    XCTAssertEqual(state.totalSegmentCount, 1)

    let sessionId = try await createAndInstallSession(state)
    await state.flushTranscriptPersistence()

    let rows = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertTrue(rows.isEmpty, "work from a stopped recording must not leak into a later session")
  }

  func testHeldWorkIsDiscardedWhenTheRecordingEndsWithoutASession() async throws {
    let state = try XCTUnwrap(state)
    state.handleBackendSegments([segment("never got a session")])
    state.discardHeldTranscriptWork()

    let sessionId = try await createAndInstallSession(state)
    await state.flushTranscriptPersistence()

    let rows = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    XCTAssertTrue(rows.isEmpty)
  }
}
