import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for finalizing a GPT-Live PTT turn on the warm omni STT
/// session.
///
/// GPT-Live is full-duplex with no client commit frame and its warm session never
/// emits `session.closed` on PTT release, so without a local terminal the
/// coordinator waited out finalization until its timeout and never answered the
/// completed press. `finalizeGptLiveInputTurn` publishes the turn's final (an
/// empty final makes PushToTalkManager resolve its interim text) and finishes it.
@MainActor
final class RealtimeOmniGptLiveCommitTests: XCTestCase {
  @MainActor
  private final class SpyDelegate: RealtimeOmniServiceDelegate {
    var finals: [String] = []
    var finishCount = 0

    func omniDidConnect() {}
    func omniDidReceiveInputTranscript(_ text: String, isFinal: Bool, itemID: String?) {
      if isFinal { finals.append(text) }
    }
    func omniDidReceiveAudio(_ pcm24k: Data) {}
    func omniDidFinishTurn() { finishCount += 1 }
    func omniDidError(_ message: String) {}
  }

  func testFinalizePublishesAFinalTranscriptAndFinishesTheTurn() {
    let spy = SpyDelegate()
    let service = RealtimeOmniService(
      provider: .gptLive,
      relayBaseURL: "https://example.invalid",
      authHeader: "Bearer token",
      sttOnly: true,
      delegate: spy
    )

    service.finalizeGptLiveInputTurn()

    XCTAssertEqual(spy.finals, [""], "the final resolves the delegate's accumulated interim STT")
    XCTAssertEqual(spy.finishCount, 1, "the turn must reach one terminal coordinator outcome")
  }
}
