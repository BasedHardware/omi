import XCTest

@testable import Omi_Computer

/// The rating-prompt trigger must count each accepted logical question exactly
/// once: retries of a failed turn and busy no-op sends keep their analytics
/// event but never advance the one-time prompt trigger.
@MainActor
final class RatingPromptCountingTests: XCTestCase {
  override func setUp() async throws {
    RatingPromptManager.shared.resetForTesting()
  }

  override func tearDown() async throws {
    RatingPromptManager.shared.resetForTesting()
  }

  private func drainCounterHops() async {
    for _ in 0..<20 { await Task.yield() }
  }

  func testAcceptedQuestionsCountExactlyOnce() async {
    AnalyticsManager.shared.chatMessageSent(messageLength: 5, source: "query_shell")
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 1)
  }

  func testRetriesAndBusySendsNeverCount() async {
    AnalyticsManager.shared.chatMessageSent(messageLength: 5, source: "query_shell")
    await drainCounterHops()
    // A retry of the same failed turn (countsAsQuestion: false).
    AnalyticsManager.shared.chatMessageSent(
      messageLength: 5, source: "query_shell", countsAsQuestion: false)
    // A busy no-op send from the home ask bar.
    AnalyticsManager.shared.chatMessageSent(
      messageLength: 9, source: "home_ask_bar", countsAsQuestion: false)
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 1)
    XCTAssertFalse(RatingPromptManager.shared.isVisible)
  }
}
