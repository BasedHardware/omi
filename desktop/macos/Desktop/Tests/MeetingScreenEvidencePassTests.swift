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

    let outcome = await pass.beforeNotes(
      captureInterval: DateInterval(start: Date(timeIntervalSince1970: 1_790_769_600), duration: 60),
      conversationID: conversation.id,
      fetchConversation: { conversation })

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
        fetchConversation: { conversation })
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
      fetchConversation: { try Self.decodeConversation(Self.serverVectors[3], id: "slow") })

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
      captureInterval: interval, conversationID: "id", fetchConversation: { throw URLError(.timedOut) })
    XCTAssertEqual(disabled, .disabled)

    pass.screenshotsEnabled = { true }
    pass.adjudicate = { _, _ in .failed("409 screen_frame_egress_unavailable") }
    let unavailable = await pass.beforeNotes(
      captureInterval: interval, conversationID: "id", fetchConversation: { throw URLError(.timedOut) })
    XCTAssertEqual(unavailable, .conversationUnavailable)
    let unbound = await pass.beforeNotes(captureInterval: interval, conversationID: nil, fetchConversation: nil)
    XCTAssertEqual(unbound, .conversationUnavailable)
    let egressOff = await pass.beforeNotes(
      captureInterval: interval, conversationID: "id",
      fetchConversation: { try Self.decodeConversation(Self.serverVectors[3], id: "id") })
    XCTAssertEqual(egressOff, .settled(.failed("409 screen_frame_egress_unavailable")))

    let flushes = await flushed.value
    XCTAssertEqual(flushes, 4, "the OCR flush serves the notes whether or not screenshots are on")
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
