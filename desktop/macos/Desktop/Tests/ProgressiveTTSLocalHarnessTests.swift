import AVFoundation
import Foundation
import XCTest

@testable import Omi_Computer

private final class LocalStreamingDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
  var onData: (@MainActor (Data) throws -> Void)?
  var responseStatus: Int?
  var receivedError: Error?
  var isComplete = false

  func urlSession(
    _ session: URLSession,
    dataTask: URLSessionDataTask,
    didReceive response: URLResponse,
    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
  ) {
    MainActor.assumeIsolated {
      responseStatus = (response as? HTTPURLResponse)?.statusCode
    }
    completionHandler(.allow)
  }

  func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
    MainActor.assumeIsolated {
      do {
        try onData?(data)
      } catch {
        receivedError = error
        dataTask.cancel()
      }
    }
  }

  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didCompleteWithError error: Error?
  ) {
    MainActor.assumeIsolated {
      if receivedError == nil { receivedError = error }
      isComplete = true
    }
  }
}

/// Opt-in localhost-only measurement. Run through
/// `scripts/run-progressive-tts-harness.sh`; normal unit/CI runs skip it.
@MainActor
final class ProgressiveTTSLocalHarnessTests: XCTestCase {
  func testSlowLocalMP3StartsBeforeBufferedPlaybackCouldStart() throws {
    guard
      let rawURL = ProcessInfo.processInfo.environment["OMI_TTS_STREAM_HARNESS_URL"],
      let url = URL(string: rawURL),
      url.host == "127.0.0.1" || url.host == "localhost"
    else {
      throw XCTSkip("Set OMI_TTS_STREAM_HARNESS_URL to the localhost slow-MP3 server")
    }

    let baselineStart = Date()
    let baselineData = try Data(contentsOf: url)
    let baselinePlayer = try AVAudioPlayer(data: baselineData)
    baselinePlayer.volume = 0
    baselinePlayer.prepareToPlay()
    let bufferedReadyMilliseconds = Date().timeIntervalSince(baselineStart) * 1_000
    baselinePlayer.stop()

    let progressiveStart = Date()
    let progressivePlayer = try ProgressiveMP3Player(
      playbackRate: 1,
      manualRenderingForTesting: true)
    var progressiveStartMilliseconds: Double?
    progressivePlayer.onStarted = {
      progressiveStartMilliseconds = Date().timeIntervalSince(progressiveStart) * 1_000
    }

    let streamDelegate = LocalStreamingDelegate()
    streamDelegate.onData = { data in
      try progressivePlayer.append(data)
    }
    let delegateQueue = OperationQueue.main
    let session = URLSession(
      configuration: .ephemeral,
      delegate: streamDelegate,
      delegateQueue: delegateQueue)
    let task = session.dataTask(with: url)
    task.resume()
    let deadline = Date().addingTimeInterval(15)
    while progressiveStartMilliseconds == nil, !streamDelegate.isComplete, Date() < deadline {
      RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
    }
    let streamError = streamDelegate.receivedError
    task.cancel()
    session.invalidateAndCancel()

    progressivePlayer.stop()

    XCTAssertEqual(streamDelegate.responseStatus, 200)
    if let streamError { throw streamError }
    let progressiveMilliseconds = try XCTUnwrap(progressiveStartMilliseconds)
    let improvement = (1 - progressiveMilliseconds / bufferedReadyMilliseconds) * 100
    print(
      String(
        format: "TTS_HARNESS buffered_ready_ms=%.0f progressive_start_ms=%.0f improvement_pct=%.1f",
        bufferedReadyMilliseconds,
        progressiveMilliseconds,
        improvement))
    XCTAssertLessThan(progressiveMilliseconds, bufferedReadyMilliseconds)
  }
}
