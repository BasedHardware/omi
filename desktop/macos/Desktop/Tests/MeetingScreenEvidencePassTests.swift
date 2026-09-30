import Foundation
import XCTest

@testable import Omi_Computer

final class MeetingScreenEvidencePassTests: XCTestCase {
  override func setUp() async throws {
    try await super.setUp()
    await MainActor.run { MeetingScreenshotsStore.resetSessionCacheForTesting() }
  }

  // MARK: - Fingerprint parity with the server

  /// Expected values were produced by the backend's own `_trusted_content_window` and
  /// `_selection_fingerprint` (`backend/routers/screen_frames.py`), run over these conversations and
  /// serialized the way FastAPI serializes them (`datetime.isoformat()`). If the client's window
  /// differs from the server's by a millisecond, a note opened after finalization re-selects and
  /// re-uploads a set the server already judged.
  private struct FingerprintVector {
    let name: String
    let startedAt: String
    let finishedAt: String?
    let segments: [(Double, Double, String)]
    let fromSegments: Bool
    let audioTimelineV2: Bool
    let fingerprint: String?
  }

  private static let serverVectors: [FingerprintVector] = [
    .init(
      name: "from_segments_microsecond_origin", startedAt: "2026-09-30T12:00:00.123456+00:00", finishedAt: nil,
      segments: [(1.0004, 5.2, "hello"), (0.25, 3.0, "hello"), (0.1, 9.0, "   ")], fromSegments: true,
      audioTimelineV2: false, fingerprint: "meeting-content-v1:1790769600373:1790769605323"),
    .init(
      name: "half_millisecond_rounds_half_even", startedAt: "2026-09-30T12:00:00+00:00", finishedAt: nil,
      segments: [(1.2345, 7.0125, "hello")], fromSegments: true, audioTimelineV2: false,
      fingerprint: "meeting-content-v1:1790769601234:1790769607012"),
    .init(
      name: "sub_millisecond_origin_carries", startedAt: "2026-09-30T12:00:00.999600+00:00", finishedAt: nil,
      segments: [(0.0003, 61.0007, "hello")], fromSegments: false, audioTimelineV2: true,
      fingerprint: "meeting-content-v1:1790769601000:1790769662000"),
    .init(
      name: "microsecond_origin_rounds_up", startedAt: "2026-09-30T12:00:00.000600+00:00", finishedAt: nil,
      segments: [(1.0, 2.0, "hello")], fromSegments: true, audioTimelineV2: false,
      fingerprint: "meeting-content-v1:1790769601001:1790769602001"),
    .init(
      name: "legacy_within_tolerance", startedAt: "2026-09-30T12:00:00.250000+00:00",
      finishedAt: "2026-09-30T12:09:35.250000+00:00", segments: [(0, 600, "hello")], fromSegments: false,
      audioTimelineV2: false, fingerprint: "meeting-content-v1:1790769600250:1790770200250"),
    .init(
      name: "legacy_outside_tolerance_untrusted", startedAt: "2026-09-30T12:00:00.250000+00:00",
      finishedAt: "2026-09-30T12:09:15.250000+00:00", segments: [(0, 600, "hello")], fromSegments: false,
      audioTimelineV2: false, fingerprint: nil),
    .init(
      name: "no_speech_untrusted", startedAt: "2026-09-30T12:00:00+00:00", finishedAt: nil,
      segments: [(0, 5, "")], fromSegments: true, audioTimelineV2: false, fingerprint: nil),
  ]

  func testClientSelectionFingerprintEqualsTheServersForTheSameConversation() throws {
    for vector in Self.serverVectors {
      let conversation = try Self.decodeConversation(vector)
      XCTAssertEqual(
        MeetingScreenshotSelectionWindow.resolve(conversation)?.fingerprint, vector.fingerprint, vector.name)
    }
  }

  // MARK: - One pass, reused by the note

  @MainActor
  func testFinalizationAdjudicatesOnceAndTheNoteLoadsThePersistedSet() async throws {
    let vector = Self.serverVectors[0]
    let conversation = try Self.decodeConversation(vector, id: "one-pass-\(UUID().uuidString)")
    let server = FakeScreenFrameServer(
      // The server stamps its own fingerprint, computed from its own copy of the conversation.
      stampedFingerprint: try XCTUnwrap(vector.fingerprint))
    let selections = SelectionCounter()
    let pass = Self.makePass(server: server, selections: selections)
    // Finalization reads the window the server reports on its side-effect-free screenshots route.
    let serverFingerprint = try XCTUnwrap(vector.fingerprint)

    let outcome = await pass.beforeNotes(
      captureInterval: DateInterval(start: Date(timeIntervalSince1970: 1_790_769_600), duration: 60),
      conversationID: conversation.id,
      fetchSelectionWindow: { MeetingScreenshotSelectionWindow(serverFingerprint: serverFingerprint) })

    XCTAssertEqual(outcome, .settled(.ready))
    XCTAssertEqual(selections.count, 1)
    let adjudicationsAfterFinalization = await server.adjudications
    XCTAssertEqual(adjudicationsAfterFinalization, 1)

    // A later launch: nothing in the session cache, the note view resolves its own window.
    MeetingScreenshotsStore.resetSessionCacheForTesting()
    let noteStore = Self.makeStore(server: server, selections: selections)
    let phase = await noteStore.loadAndWait(
      conversationID: conversation.id,
      selectionWindow: try XCTUnwrap(MeetingScreenshotSelectionWindow.resolve(conversation)))

    XCTAssertEqual(phase, .ready)
    XCTAssertEqual(noteStore.frames.count, 1)
    XCTAssertEqual(selections.count, 1, "opening the note must not re-select")
    let adjudications = await server.adjudications
    XCTAssertEqual(adjudications, 1, "opening the note must not re-adjudicate")
  }

  @MainActor
  func testNoteOpenedDuringFinalizationJoinsTheRunningAdjudication() async throws {
    let vector = Self.serverVectors[3]
    let conversation = try Self.decodeConversation(vector, id: "mid-run-\(UUID().uuidString)")
    let window = try XCTUnwrap(MeetingScreenshotSelectionWindow.resolve(conversation))
    let server = FakeScreenFrameServer(stampedFingerprint: window.fingerprint, holdsAdjudication: true)
    let selections = SelectionCounter()
    let pass = Self.makePass(server: server, selections: selections)

    let finalization = Task { @MainActor in
      await pass.beforeNotes(
        captureInterval: DateInterval(start: window.start, end: window.end),
        conversationID: conversation.id,
        fetchSelectionWindow: { window })
    }
    await server.waitUntilAdjudicationStarts()

    let noteStore = Self.makeStore(server: server, selections: selections)
    noteStore.load(conversationID: conversation.id, selectionWindow: window)
    await server.releaseAdjudication()

    let outcome = await finalization.value
    let notePhase = await noteStore.loadAndWait(conversationID: conversation.id, selectionWindow: window)
    XCTAssertEqual(outcome, .settled(.ready))
    XCTAssertEqual(notePhase, .ready)
    XCTAssertEqual(selections.count, 1)
    let adjudications = await server.adjudications
    XCTAssertEqual(adjudications, 1, "the note must await the finalization run, not start a second one")
  }

  func testBoundExpiresWithoutWaitingForSlowEvidence() async {
    let released = AsyncFlag()
    let pass = MeetingScreenEvidencePass(
      timeout: .seconds(20),
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { _, _ in
        await released.wait()
        return .ready
      },
      sleep: { _ in })  // the bound fires immediately

    let outcome = await pass.beforeNotes(
      captureInterval: DateInterval(start: Date(timeIntervalSince1970: 0), duration: 10),
      conversationID: "slow",
      fetchSelectionWindow: { Self.sampleWindow })

    XCTAssertEqual(outcome, .timedOut)
    await released.set()
  }

  func testFailuresAreSilentAndTheOCRFlushStillRuns() async {
    let flushed = AsyncCounter()
    var pass = MeetingScreenEvidencePass(
      screenshotsEnabled: { false },
      flushScreenActivity: { _ in await flushed.increment() },
      adjudicate: { _, _ in
        XCTFail("disabled screenshots must never select or upload")
        return .ready
      },
      sleep: boundThatNeverFires)
    let interval = DateInterval(start: Date(timeIntervalSince1970: 0), duration: 10)

    let disabled = await pass.beforeNotes(
      captureInterval: interval, conversationID: "id", fetchSelectionWindow: { throw URLError(.timedOut) })
    XCTAssertEqual(disabled, .disabled)

    pass.screenshotsEnabled = { true }
    pass.adjudicate = { _, _ in .failed("409 screen_frame_egress_unavailable") }
    let unavailable = await pass.beforeNotes(
      captureInterval: interval, conversationID: "id", fetchSelectionWindow: { throw URLError(.timedOut) })
    XCTAssertEqual(unavailable, .conversationUnavailable)
    let unbound = await pass.beforeNotes(captureInterval: interval, conversationID: nil, fetchSelectionWindow: nil)
    XCTAssertEqual(unbound, .unbound)
    let egressOff = await pass.beforeNotes(
      captureInterval: interval, conversationID: "id",
      fetchSelectionWindow: { Self.sampleWindow })
    XCTAssertEqual(egressOff, .settled(.failed("409 screen_frame_egress_unavailable")))

    let flushes = await flushed.value
    XCTAssertEqual(flushes, 4, "the OCR flush serves the notes whether or not screenshots are on")
  }

  func testDeadlineExpiryAndFailureRecordDegradedFallbackTelemetry() async {
    let fallbacks = FallbackRecorder()
    var pass = MeetingScreenEvidencePass(
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { _, _ in .ready },
      sleep: { _ in },
      recordFallback: { fallbacks.record($0) })
    let interval = DateInterval(start: Date(timeIntervalSince1970: 0), duration: 10)
    let fetch: @Sendable () async throws -> MeetingScreenshotSelectionWindow? = { Self.sampleWindow }

    let blocked = AsyncFlag()
    pass.adjudicate = { _, _ in
      await blocked.wait()
      return .ready
    }
    let timedOut = await pass.beforeNotes(
      captureInterval: interval, conversationID: "telemetry", fetchSelectionWindow: fetch)
    XCTAssertEqual(timedOut, .timedOut)
    XCTAssertTrue(timedOut.needsRetryAfterFinalize)
    await blocked.set()

    pass.sleep = boundThatNeverFires
    pass.adjudicate = { _, _ in .failed("503") }
    let failed = await pass.beforeNotes(
      captureInterval: interval, conversationID: "telemetry", fetchSelectionWindow: fetch)
    XCTAssertTrue(failed.needsRetryAfterFinalize)

    pass.adjudicate = { _, _ in .ready }
    let settled = await pass.beforeNotes(
      captureInterval: interval, conversationID: "telemetry", fetchSelectionWindow: fetch)
    XCTAssertFalse(settled.needsRetryAfterFinalize)

    XCTAssertEqual(fallbacks.reasons, ["timeout", "upload_failed"], "a settled pass records no fallback")
  }

  func testAfterCreationFailureRecordsDegradedFallbackTelemetry() async throws {
    let fallbacks = FallbackRecorder()
    var pass = MeetingScreenEvidencePass(
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { _, _ in .failed("409 screen_frame_egress_unavailable") },
      sleep: boundThatNeverFires,
      recordFallback: { fallbacks.record($0) })
    let conversation = try Self.decodeConversation(Self.serverVectors[3], id: "created")

    let failed = await pass.afterCreation(conversation: conversation)
    XCTAssertEqual(failed, .settled(.failed("409 screen_frame_egress_unavailable")))
    pass.adjudicate = { _, _ in .ready }
    let settled = await pass.afterCreation(conversation: conversation)
    XCTAssertEqual(settled, .settled(.ready))

    XCTAssertEqual(
      fallbacks.recorded,
      [.init(reason: "upload_failed", from: "after_creation", to: "note_open")],
      "a failed post-creation pass is degraded telemetry; a settled one records nothing")
  }

  @MainActor
  func testRetryAfterFinalizeJoinsTheRunTheDeadlineLeftInFlight() async throws {
    let vector = Self.serverVectors[3]
    let conversation = try Self.decodeConversation(vector, id: "retry-\(UUID().uuidString)")
    let window = try XCTUnwrap(MeetingScreenshotSelectionWindow.resolve(conversation))
    let server = FakeScreenFrameServer(stampedFingerprint: window.fingerprint, holdsAdjudication: true)
    let selections = SelectionCounter()
    var pass = Self.makePass(server: server, selections: selections)
    pass.sleep = { _ in await server.waitUntilAdjudicationStarts() }  // the bound expires mid-judging

    let before = await pass.beforeNotes(
      captureInterval: DateInterval(start: window.start, end: window.end),
      conversationID: conversation.id,
      fetchSelectionWindow: { window })
    XCTAssertEqual(before, .timedOut)

    let retry = Task { @MainActor in
      await pass.afterFinalize(conversationID: conversation.id, fetchSelectionWindow: { window })
    }
    await server.releaseAdjudication()
    let after = await retry.value

    XCTAssertEqual(after, .settled(.ready))
    XCTAssertEqual(selections.count, 1)
    let adjudications = await server.adjudications
    XCTAssertEqual(adjudications, 1, "the retry must join the in-flight run, not judge the frames twice")
  }

  @MainActor
  func testFramesInTheUnsealedChunkAreSealedAndReselectedBeforeJudging() async throws {
    let window = MeetingScreenshotSelectionWindow(
      start: Date(timeIntervalSince1970: 1_000), end: Date(timeIntervalSince1970: 1_600))
    let server = FakeScreenFrameServer(stampedFingerprint: window.fingerprint)
    let chunk = ActiveChunk()
    let store = MeetingScreenshotsStore(
      featureEnabled: { true },
      selectCandidates: { window in await chunk.select(in: window) },
      adjudicateAndCommit: { candidates, _ in try await server.adjudicate(capturedAt: candidates[0].timestamp) },
      fetchPersistedSet: { _ in await server.persisted() },
      deleteFrameRemote: { _, _ in },
      sealActiveRecording: { await chunk.seal() })

    let phase = await store.loadAndWait(conversationID: "seal-\(UUID().uuidString)", selectionWindow: window)

    XCTAssertEqual(phase, .ready)
    let seals = await chunk.seals
    XCTAssertEqual(seals, 1)
    let adjudications = await server.adjudications
    XCTAssertEqual(adjudications, 1)
  }

  @MainActor
  func testAnUnsealableChunkIsRetryableNotCachedAsNoCapture() async throws {
    let window = MeetingScreenshotSelectionWindow(
      start: Date(timeIntervalSince1970: 2_000), end: Date(timeIntervalSince1970: 2_600))
    let server = FakeScreenFrameServer(stampedFingerprint: window.fingerprint)
    let chunk = ActiveChunk(sealable: false)
    let conversationID = "unsealed-\(UUID().uuidString)"
    func makeStore() -> MeetingScreenshotsStore {
      MeetingScreenshotsStore(
        featureEnabled: { true },
        selectCandidates: { window in await chunk.select(in: window) },
        adjudicateAndCommit: { candidates, _ in try await server.adjudicate(capturedAt: candidates[0].timestamp) },
        fetchPersistedSet: { _ in await server.persisted() },
        deleteFrameRemote: { _, _ in },
        sealActiveRecording: { await chunk.seal() })
    }

    let first = await makeStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    XCTAssertEqual(first, .failed(MeetingScreenshotsStore.activeChunkRetryDetail))
    let judgedWhileUnsealed = await server.adjudications
    XCTAssertEqual(judgedWhileUnsealed, 0, "a set missing the meeting's end must not be judged and stamped")

    await chunk.makeSealable()
    let second = await makeStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    XCTAssertEqual(second, .ready, "the next load selects again instead of reading a cached .noCapture")
    let adjudications = await server.adjudications
    XCTAssertEqual(adjudications, 1)
  }

  @MainActor
  func testCachedSetWithExpiringSignedURLsIsRefetchedBeforeRendering() async throws {
    let window = MeetingScreenshotSelectionWindow(
      start: Date(timeIntervalSince1970: 3_000), end: Date(timeIntervalSince1970: 3_600))
    let clock = TestClock(Date(timeIntervalSince1970: 10_000))
    let server = SigningServer(fingerprint: window.fingerprint, capturedAt: window.start, clock: clock)
    let conversationID = "expiry-\(UUID().uuidString)"
    func makeStore() -> MeetingScreenshotsStore {
      MeetingScreenshotsStore(
        featureEnabled: { true },
        selectCandidates: { _ in
          XCTFail("a persisted set for this window must be read, not re-selected")
          return MeetingFrameSelector.Outcome()
        },
        fetchPersistedSet: { _ in server.persisted() },
        deleteFrameRemote: { _, _ in },
        now: { clock.now })
    }

    // The finalization pass fills the session cache with a signature good for 20 minutes.
    _ = await makeStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    XCTAssertEqual(server.fetches, 1)

    // Opened 10 minutes later: still fresh beyond the margin, so the cache is used as is.
    clock.now = clock.now.addingTimeInterval(10 * 60)
    let fresh = await makeStore().loadAndWait(conversationID: conversationID, selectionWindow: window)
    XCTAssertEqual(fresh, .ready)
    XCTAssertEqual(server.fetches, 1)

    // Opened 16 minutes after that: 4 minutes left is inside the margin, so it is re-read.
    clock.now = clock.now.addingTimeInterval(16 * 60)
    let note = makeStore()
    let refreshed = await note.loadAndWait(conversationID: conversationID, selectionWindow: window)
    XCTAssertEqual(refreshed, .ready)
    XCTAssertEqual(server.fetches, 2)
    XCTAssertEqual(note.frames.first?.thumbnailURL, "https://example.test/thumb-2.jpg")
    XCTAssertGreaterThan(note.frames.first?.urlExpiresAt ?? .distantPast, clock.now.addingTimeInterval(15 * 60))

    // Every tile reporting a failed thumbnail at once still costs one refetch.
    async let first: Void = note.refreshAfterContentUnavailable()
    async let second: Void = note.refreshAfterContentUnavailable()
    _ = await (first, second)
    XCTAssertEqual(server.fetches, 3)
    XCTAssertEqual(note.frames.first?.thumbnailURL, "https://example.test/thumb-3.jpg")
  }

  private static let sampleWindow = MeetingScreenshotSelectionWindow(
    start: Date(timeIntervalSince1970: 5_000), end: Date(timeIntervalSince1970: 5_600))

  func testServerReportedWindowKeepsItsFingerprintAndSelectsInsideIt() throws {
    for vector in Self.serverVectors {
      guard let fingerprint = vector.fingerprint else { continue }
      let window = try XCTUnwrap(MeetingScreenshotSelectionWindow(serverFingerprint: fingerprint), vector.name)
      XCTAssertEqual(window.fingerprint, fingerprint, vector.name)
      let derived = try XCTUnwrap(MeetingScreenshotSelectionWindow.resolve(Self.decodeConversation(vector)))
      XCTAssertEqual(window.fingerprint, derived.fingerprint, "the note view derives the same key: \(vector.name)")
      // Strictly inside the server's exact window, whichever way its milliseconds were rounded.
      XCTAssertGreaterThan(window.start, derived.start, vector.name)
      XCTAssertLessThan(window.end, derived.end, vector.name)
    }
    for malformed in ["", "meeting-lifecycle-v0:1:9", "meeting-content-v1:9:1", "meeting-content-v1:a:b"] {
      XCTAssertNil(MeetingScreenshotSelectionWindow(serverFingerprint: malformed), malformed)
    }
  }

  /// Bodies serialized by the merged backend model (`ConversationScreenFrameSet.model_dump_json()`
  /// with `trusted_selection_fingerprint` set, and null when the transcript fixes no window yet).
  func testDecodesTheOwnerRoutesTrustedSelectionFingerprint() throws {
    let trusted = Data(
      #"{"revision":0,"banner":null,"strip":[],"adjudicated_at":null,"selection_fingerprint":null,"trusted_selection_fingerprint":"meeting-content-v1:1783418401623:1783418458373"}"#
        .utf8)
    let untrusted = Data(
      #"{"revision":0,"banner":null,"strip":[],"adjudicated_at":null,"selection_fingerprint":null,"trusted_selection_fingerprint":null}"#
        .utf8)
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601

    let set = try decoder.decode(ConversationScreenFrameSet.self, from: trusted)
    XCTAssertEqual(set.trustedSelectionFingerprint, "meeting-content-v1:1783418401623:1783418458373")
    XCTAssertEqual(
      set.trustedSelectionFingerprint.flatMap(MeetingScreenshotSelectionWindow.init(serverFingerprint:))?.fingerprint,
      "meeting-content-v1:1783418401623:1783418458373")
    XCTAssertNil(try decoder.decode(ConversationScreenFrameSet.self, from: untrusted).trustedSelectionFingerprint)
  }

  func testAFailedWindowReadIsDegradedButAnUnboundCallIsNot() async {
    let fallbacks = FallbackRecorder()
    let pass = MeetingScreenEvidencePass(
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { _, _ in .ready },
      sleep: boundThatNeverFires,
      recordFallback: { fallbacks.record($0) })
    let interval = DateInterval(start: Date(timeIntervalSince1970: 0), duration: 10)

    let unbound = await pass.beforeNotes(captureInterval: interval, conversationID: nil, fetchSelectionWindow: nil)
    XCTAssertEqual(unbound, .unbound)
    XCTAssertTrue(fallbacks.recorded.isEmpty, "no conversation id yet is the expected shape, not a degradation")

    let failedRead = await pass.beforeNotes(
      captureInterval: interval, conversationID: "read-fails", fetchSelectionWindow: { throw URLError(.timedOut) })
    XCTAssertEqual(failedRead, .conversationUnavailable)
    let failedRetryRead = await pass.afterFinalize(
      conversationID: "read-fails", fetchSelectionWindow: { throw URLError(.timedOut) })
    XCTAssertEqual(failedRetryRead, .conversationUnavailable)

    XCTAssertEqual(
      fallbacks.recorded,
      [
        .init(reason: "other", from: "before_notes", to: "after_finalize"),
        .init(reason: "other", from: "after_finalize", to: "note_open"),
      ])
  }

  func testAfterFinalizeFailureRecordsDegradedFallbackToNoteOpen() async {
    let fallbacks = FallbackRecorder()
    let pass = MeetingScreenEvidencePass(
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { _, _ in .failed("503") },
      sleep: boundThatNeverFires,
      recordFallback: { fallbacks.record($0) })

    let outcome = await pass.afterFinalize(conversationID: "finalized", fetchSelectionWindow: { Self.sampleWindow })

    XCTAssertEqual(outcome, .settled(.failed("503")))
    XCTAssertEqual(fallbacks.recorded, [.init(reason: "upload_failed", from: "after_finalize", to: "note_open")])
  }

  // MARK: - Helpers

  @MainActor
  private static func makeStore(server: FakeScreenFrameServer, selections: SelectionCounter) -> MeetingScreenshotsStore
  {
    MeetingScreenshotsStore(
      featureEnabled: { true },
      selectCandidates: { window in
        selections.count += 1
        var outcome = MeetingFrameSelector.Outcome()
        outcome.framesInWindow = 1
        outcome.candidates = [
          MeetingFrameCandidate(
            id: 1, timestamp: window.start, appName: "Keynote", windowTitle: "Roadmap", imagePath: "frame.jpg",
            videoChunkPath: nil, frameOffset: 0, ocrText: nil)
        ]
        return outcome
      },
      adjudicateAndCommit: { candidates, _ in try await server.adjudicate(capturedAt: candidates[0].timestamp) },
      fetchPersistedSet: { _ in await server.persisted() },
      deleteFrameRemote: { _, _ in })
  }

  private static func makePass(server: FakeScreenFrameServer, selections: SelectionCounter) -> MeetingScreenEvidencePass
  {
    MeetingScreenEvidencePass(
      screenshotsEnabled: { true },
      flushScreenActivity: { _ in },
      adjudicate: { @MainActor conversationID, window in
        await Self.makeStore(server: server, selections: selections)
          .loadAndWait(conversationID: conversationID, selectionWindow: window)
      },
      sleep: boundThatNeverFires)
  }

  private static func decodeConversation(_ vector: FingerprintVector, id: String = "conversation") throws
    -> ServerConversation
  {
    var object: [String: Any] = [
      "id": id,
      "created_at": vector.startedAt,
      "started_at": vector.startedAt,
      "finished_at": vector.finishedAt ?? NSNull(),
      "structured": [
        "title": "Meeting", "overview": "", "emoji": "", "category": "other", "action_items": [], "events": [],
      ],
      "status": "in_progress",
      "source": "desktop",
      "discarded": false,
      "transcript_segments": vector.segments.enumerated().map { index, segment in
        [
          "id": "segment-\(index)", "text": segment.2, "speaker": "SPEAKER_00", "speaker_id": 0,
          "is_user": false, "start": segment.0, "end": segment.1,
        ] as [String: Any]
      },
    ]
    if vector.fromSegments {
      object["external_data"] = ["from_segments_client_session_id": "session-1"]
    }
    if vector.audioTimelineV2 {
      object["audio_timeline"] = ["version": 2]
    }
    let data = try JSONSerialization.data(withJSONObject: object)
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return try decoder.decode(ServerConversation.self, from: data)
  }
}

@MainActor
private final class SelectionCounter {
  var count = 0
}

private actor AsyncCounter {
  private(set) var value = 0
  func increment() { value += 1 }
}

private actor AsyncFlag {
  private var isSet = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    if isSet { return }
    await withCheckedContinuation { waiters.append($0) }
  }

  func set() {
    isSet = true
    let pending = waiters
    waiters.removeAll()
    for waiter in pending { waiter.resume() }
  }
}

/// The server's side of the contract, reduced to what the one-pass guarantee depends on: it stamps
/// its own selection fingerprint on the adjudicated set, and `GET` returns that set afterwards.
private actor FakeScreenFrameServer {
  private let stampedFingerprint: String
  private let holdsAdjudication: Bool
  private var stored = ConversationScreenFrameSet.empty
  private let started = AsyncFlag()
  private let release = AsyncFlag()
  private(set) var adjudications = 0

  init(stampedFingerprint: String, holdsAdjudication: Bool = false) {
    self.stampedFingerprint = stampedFingerprint
    self.holdsAdjudication = holdsAdjudication
  }

  func adjudicate(capturedAt: Date) async throws -> ConversationScreenFrameSet {
    adjudications += 1
    await started.set()
    if holdsAdjudication { await release.wait() }
    let frame = ConversationScreenFrame(
      id: "frame-1", capturedAt: capturedAt, role: "strip", rank: 0, caption: "Roadmap slide", labels: [],
      sourceBadge: nil, focalRegion: nil, width: 1280, height: 800, contentURL: "https://example.test/frame.jpg",
      thumbnailURL: "https://example.test/thumb.jpg", urlExpiresAt: capturedAt.addingTimeInterval(3_600),
      ground: nil)
    stored = ConversationScreenFrameSet(
      revision: 1, banner: nil, strip: [frame], adjudicatedAt: Date(), selectionFingerprint: stampedFingerprint)
    return stored
  }

  func persisted() -> ConversationScreenFrameSet { stored }

  func waitUntilAdjudicationStarts() async { await started.wait() }

  func releaseAdjudication() async { await release.set() }
}

/// A pass bound that never fires on its own: it ends only when the work finishes first and the pass
/// cancels it, so these tests never wait on wall-clock time.
private let boundThatNeverFires: @Sendable (Duration) async -> Void = { _ in
  let (stream, continuation) = AsyncStream<Void>.makeStream()
  for await _ in stream {}
  continuation.finish()
}

private final class FallbackRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private var fallbacks: [MeetingScreenEvidencePass.Fallback] = []

  var recorded: [MeetingScreenEvidencePass.Fallback] {
    lock.lock()
    defer { lock.unlock() }
    return fallbacks
  }

  var reasons: [String] { recorded.map(\.reason) }

  func record(_ fallback: MeetingScreenEvidencePass.Fallback) {
    lock.lock()
    fallbacks.append(fallback)
    lock.unlock()
  }
}

/// Rewind's active chunk, reduced to what selection sees: until sealed, the meeting's last frame
/// is dropped as still being written.
private actor ActiveChunk {
  private var sealable: Bool
  private var sealed = false
  private(set) var seals = 0

  init(sealable: Bool = true) {
    self.sealable = sealable
  }

  func seal() {
    seals += 1
    if sealable { sealed = true }
  }

  func makeSealable() { sealable = true }

  func select(in window: MeetingScreenshotSelectionWindow) -> MeetingFrameSelector.Outcome {
    var outcome = MeetingFrameSelector.Outcome()
    outcome.framesInWindow = 1
    if sealed {
      outcome.candidates = [
        MeetingFrameCandidate(
          id: 7, timestamp: window.end, appName: "Keynote", windowTitle: "Decisions", imagePath: nil,
          videoChunkPath: "chunk.mp4", frameOffset: 0, ocrText: nil)
      ]
    } else {
      outcome.drops[MeetingFrameSelector.activeChunkDropReason] = 1
    }
    return outcome
  }
}

private final class TestClock: @unchecked Sendable {
  private let lock = NSLock()
  private var current: Date

  init(_ start: Date) { current = start }

  var now: Date {
    get {
      lock.lock()
      defer { lock.unlock() }
      return current
    }
    set {
      lock.lock()
      current = newValue
      lock.unlock()
    }
  }
}

/// A persisted set whose signatures are re-minted on every `GET`, each good for 20 minutes.
private final class SigningServer: @unchecked Sendable {
  private let lock = NSLock()
  private let fingerprint: String
  private let capturedAt: Date
  private let clock: TestClock
  private var count = 0

  init(fingerprint: String, capturedAt: Date, clock: TestClock) {
    self.fingerprint = fingerprint
    self.capturedAt = capturedAt
    self.clock = clock
  }

  var fetches: Int {
    lock.lock()
    defer { lock.unlock() }
    return count
  }

  func persisted() -> ConversationScreenFrameSet {
    lock.lock()
    count += 1
    let generation = count
    lock.unlock()
    let frame = ConversationScreenFrame(
      id: "frame-1", capturedAt: capturedAt, role: "strip", rank: 0, caption: "Roadmap", labels: [],
      sourceBadge: nil, focalRegion: nil, width: 1280, height: 800,
      contentURL: "https://example.test/frame-\(generation).jpg",
      thumbnailURL: "https://example.test/thumb-\(generation).jpg",
      urlExpiresAt: clock.now.addingTimeInterval(20 * 60), ground: nil)
    return ConversationScreenFrameSet(
      revision: 1, banner: nil, strip: [frame], adjudicatedAt: capturedAt, selectionFingerprint: fingerprint)
  }
}
