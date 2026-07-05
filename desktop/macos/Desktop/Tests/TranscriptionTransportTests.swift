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

  // MARK: BL-013 — bounded per-turn audio buffer

  func testBatchAudioBufferIsBounded() throws {
    let src = try source(relativePath: "Sources/FloatingControlBar/PushToTalkManager.swift")
    XCTAssertTrue(src.contains("maxBatchAudioBytes"))
    XCTAssertTrue(src.contains("appendBatchAudioBounded"))
    // The raw unbounded appends are gone from the audio callback.
    XCTAssertFalse(
      src.contains("self.batchAudioBuffer.append(audioData)"),
      "audio-thread appends must go through the bounded helper")
    // A user-visible warning surfaces via the rendered pttHintText channel.
    XCTAssertTrue(src.contains("Recording too long"))
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
