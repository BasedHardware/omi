import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingStreamingRevealTests: XCTestCase {
  func testStreamMessageRevealsIncrementallyBeforeSettling() async throws {
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      streamSleeper: { _ in await Task.yield() },
      onComplete: nil)
    model.step = .promise
    let full = model.message(for: .promise)
    XCTAssertGreaterThan(full.count, 0)

    model.streamMessage(for: .promise)
    defer { model.streamTask?.cancel() }

    // Wait for the reveal to start (after the initial typing delay), then
    // sample the streaming text until the thread settles.
    var observedPrefixes: [String] = []
    for _ in 0..<full.count * 2 where model.thread.isEmpty {
      await Task.yield()
      if let streaming = model.streamingText {
        observedPrefixes.append(streaming)
      }
      // omi-test-quality: wall-clock-wait -- poll the reveal loop, which itself ticks on a 40ms timer
    }

    XCTAssertFalse(observedPrefixes.isEmpty, "onboarding message should reveal through streamingText")
    for prefix in observedPrefixes {
      XCTAssertTrue(full.hasPrefix(prefix), "streaming text must be a prefix of the full reply")
    }
    let strictlyProgressive = observedPrefixes.filter { $0.count < full.count }
    XCTAssertFalse(
      strictlyProgressive.isEmpty,
      "reveal must pass through at least one intermediate prefix instead of one full-string diff")
  }
}
