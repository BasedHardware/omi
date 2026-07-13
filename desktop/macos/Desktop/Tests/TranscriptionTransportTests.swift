import Network
import XCTest

@testable import Omi_Computer

/// S-04 — Transcription transport truthfulness (BL-011–014).
/// Behavioral tests where the object is constructible; source-scrape guards
/// (same pattern as `PTTAudioCaptureRaceTests`) for the hot-path / singleton
/// changes that can't be driven without a backend or real audio device.
final class TranscriptionTransportTests: XCTestCase {

  // MARK: BL-011 — RawWebSocket port force-unwrap

  /// A URL can carry an out-of-range port (URL.port is an Int; e.g. `:99999`).
  /// `UInt16(url.port ?? 443)` / `NWEndpoint.Port(rawValue:)!` would trap. connect()
  /// must report the error instead of crashing. (The guard itself landed upstream
  /// in #9069 / 243bab529 — this regression test guards the port validation our
  /// hub transport depends on; its message is "invalid WebSocket port <n>".)
  func testConnectWithOutOfRangePortReportsErrorInsteadOfCrashing() {
    let socket = RawWebSocket(
      url: URL(string: "wss://example.com:99999/path")!,
      queue: DispatchQueue(label: "test.rawws"))
    let errored = expectation(description: "onError fires")
    socket.onError = { message in
      XCTAssertTrue(message.lowercased().contains("port"), "got: \(message)")
      errored.fulfill()
    }
    socket.connect()  // pre-fix: traps in UInt16(99999)
    wait(for: [errored], timeout: 2.0)
  }

  // MARK: BL-012 — isConnected reflects the real socket open

  /// The delegate must forward the real WS handshake events so `isConnected`
  /// is driven by `didOpenWithProtocol`, not a fixed timer.
  func testWebSocketConnectionDelegateForwardsOpenAndClose() {
    let delegate = WebSocketConnectionDelegate()
    var opened = false
    var closedCode: URLSessionWebSocketTask.CloseCode?
    delegate.onOpen = { opened = true }
    delegate.onClose = { closedCode = $0 }

    let session = URLSession(configuration: .default)
    let task = session.webSocketTask(with: URL(string: "wss://example.com/ws")!)
    delegate.urlSession(session, webSocketTask: task, didOpenWithProtocol: nil)
    delegate.urlSession(session, webSocketTask: task, didCloseWith: .goingAway, reason: nil)
    session.invalidateAndCancel()

    XCTAssertTrue(opened)
    XCTAssertEqual(closedCode, .goingAway)
  }

  /// The 0.5s "assume connected" timer must be gone; isConnected is set on the
  /// real open event and the session is created with the delegate.
  func testConnectIsEventDrivenNotTimer() throws {
    let src = try source(relativePath: "Sources/TranscriptionService.swift")
    XCTAssertFalse(
      src.contains("asyncAfter(deadline: .now() + 0.5)"),
      "the fixed 0.5s connect timer must be replaced by the real open event")
    XCTAssertTrue(src.contains("delegate.onOpen"))
    XCTAssertTrue(src.contains("URLSession(configuration: configuration, delegate: delegate"))
    XCTAssertTrue(src.contains("didOpenWithProtocol"))
  }

  func testConversationWebSocketCarriesDeviceProvenanceHeaders() throws {
    let src = try source(relativePath: "Sources/TranscriptionService.swift")

    XCTAssertTrue(src.contains("X-App-Platform"))
    XCTAssertTrue(src.contains("X-Device-Id-Hash"))
    XCTAssertTrue(src.contains("ClientDeviceService.shared.deviceIdHash"))
  }

  // MARK: BL-013 — bounded per-turn audio buffer

  func testBatchAudioBufferIsBounded() throws {
    let src = try source(relativePath: "Sources/FloatingControlBar/PushToTalkManager.swift")
    XCTAssertTrue(src.contains("maxBatchAudioBytes"))
    XCTAssertTrue(src.contains("appendBatchAudioBounded"))
    XCTAssertTrue(
      src.contains("appendBatchAudioBounded(_ audioData: Data, turn: UInt64)"),
      "bounded append should take the audio callback's stable turn id")
    XCTAssertTrue(
      src.contains("appendBatchAudioBounded(audioData, turn: generation)"),
      "audio callbacks should pass their captured generation into the bounded append helper")
    // The raw unbounded appends are gone from the audio callback.
    XCTAssertFalse(
      src.contains("self.batchAudioBuffer.append(audioData)"),
      "audio-thread appends must go through the bounded helper")
    // A user-visible warning surfaces via the rendered pttHintText channel.
    XCTAssertTrue(src.contains("Recording too long"))
    // Review fixes: the overflow warning is turn-guarded (no stale warning painting a
    // newer turn) and self-clears (doesn't linger after the capped turn is submitted).
    guard let range = src.range(of: "func showBatchAudioOverflowWarning") else {
      return XCTFail("showBatchAudioOverflowWarning not found")
    }
    let body = String(src[range.lowerBound...].prefix(700))
    XCTAssertTrue(body.contains("micCaptureGeneration == turn"), "warning must be turn-guarded")
    XCTAssertTrue(body.contains(".hintChanged(turnID:"), "warning must use the reducer-owned hint path")

    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(
      model,
      .hintChanged(turnID: turnID, text: "Recording too long — keep it under 5 min")
    ).model
    XCTAssertTrue(model.turn?.deadlines.contains(.hintVisibility) == true)
    model = reducer.reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .hintVisibility)
    ).model
    XCTAssertEqual(model.turn?.projection.hint, "")
  }

  /// MIC-04 (behavioral): the per-turn buffer must stop growing at the ~4.5-min cap
  /// (bounded RSS on a >5-min dictation) and warn the user exactly once, at the
  /// crossing. The live-mic path can't reach this cap from the automation bridge —
  /// the PTT actions drive the realtime hub, not the batch buffer (proven in the
  /// Wave-19 runtime attempts) — so the pure cap decision is the criterion's real
  /// test seam.
  func testBatchAudioCapBoundsBufferAndWarnsExactlyOnce() {
    let cap = PushToTalkManager.maxBatchAudioBytes
    XCTAssertEqual(cap, Int(4.5 * 60) * 16_000 * 2, "cap is 4.5 min of 16kHz s16 mono")

    // Well under the cap: keep appending, no warning.
    let low = PushToTalkManager.batchAudioCapDecision(
      bufferedBytes: 0, chunkBytes: 3_200, alreadySignaled: false)
    XCTAssertTrue(low.append)
    XCTAssertFalse(low.warn)

    // The chunk that crosses the cap is kept, and it is the one that warns.
    let crossing = PushToTalkManager.batchAudioCapDecision(
      bufferedBytes: cap - 100, chunkBytes: 3_200, alreadySignaled: false)
    XCTAssertTrue(crossing.append, "the crossing chunk is kept so the buffered audio still transcribes")
    XCTAssertTrue(crossing.warn, "the crossing chunk warns the user")

    // Same crossing, already warned: still no second warning (once per turn).
    let crossingAgain = PushToTalkManager.batchAudioCapDecision(
      bufferedBytes: cap - 100, chunkBytes: 3_200, alreadySignaled: true)
    XCTAssertTrue(crossingAgain.append)
    XCTAssertFalse(crossingAgain.warn, "the overflow warning must fire exactly once per turn")

    // At/over the cap the buffer stops growing entirely — this is the bounded-RSS guarantee.
    for buffered in [cap, cap + 1, cap * 2] {
      let over = PushToTalkManager.batchAudioCapDecision(
        bufferedBytes: buffered, chunkBytes: 3_200, alreadySignaled: true)
      XCTAssertFalse(over.append, "buffer must not grow past the cap (bounded memory)")
      XCTAssertFalse(over.warn)
    }
  }

  /// Simulating a >5-min dictation chunk-by-chunk: RSS is bounded at the cap and the
  /// user is warned exactly once across the whole turn.
  func testSimulatedLongDictationStaysBoundedWithSingleWarning() {
    let cap = PushToTalkManager.maxBatchAudioBytes
    let chunk = 3_200  // 100ms of 16kHz s16 mono
    var buffered = 0
    var signaled = false
    var warnings = 0

    // 6 minutes of continuous speech — well past the 4.5-min cap.
    let chunksIn6Min = (6 * 60 * 16_000 * 2) / chunk
    for _ in 0..<chunksIn6Min {
      let d = PushToTalkManager.batchAudioCapDecision(
        bufferedBytes: buffered, chunkBytes: chunk, alreadySignaled: signaled)
      if d.append { buffered += chunk }
      if d.warn {
        warnings += 1
        signaled = true
      }
    }

    XCTAssertEqual(warnings, 1, "exactly one 'Recording too long' warning across a 6-min turn")
    XCTAssertLessThanOrEqual(
      buffered, cap + chunk,
      "buffer must not exceed the cap by more than the single crossing chunk (bounded RSS)")
    XCTAssertGreaterThanOrEqual(buffered, cap, "the full ~4.5 min is retained for transcription")
  }

  // MARK: BL-014 — deinit must not deadlock

  func testAudioCaptureDeinitDoesNotSyncOnAudioQueue() throws {
    let src = try source(relativePath: "Sources/AudioCaptureService.swift")
    // The deadlock construct — a sync dispatch block onto audioQueue — must be gone
    // entirely (the file otherwise only uses `audioQueue.async {`).
    XCTAssertFalse(
      src.contains("audioQueue.sync {"),
      "deinit must call HAL teardown directly, not sync-dispatch to audioQueue (deadlock)")
    // deinit still tears the HAL device down.
    guard let deinitRange = src.range(of: "deinit {") else {
      return XCTFail("deinit not found")
    }
    let deinitBody = String(src[deinitRange.lowerBound...].prefix(900))
    XCTAssertTrue(deinitBody.contains("AudioDeviceStop"))
    XCTAssertTrue(deinitBody.contains("AudioDeviceDestroyIOProcID"))
  }

  // MARK: Helper

  private func source(relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}
