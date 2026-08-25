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

  /// Drives the PRODUCTION submit/retry ledger the query shell delegates to —
  /// the same sequence a user produces with a failed turn and 'Try again'.
  func testQueryShellRetrySequenceCountsTheQuestionExactlyOnce() async {
    var ledger = QueryShellSendLedger()

    guard let submit = ledger.planSubmit("what changed today?") else {
      return XCTFail("a resolved submit must produce a send plan")
    }
    XCTAssertTrue(submit.countsAsQuestion)
    AnalyticsManager.shared.chatMessageSent(
      messageLength: submit.question.count, source: "query_shell",
      countsAsQuestion: submit.countsAsQuestion)

    // The turn fails; the user presses 'Try again' twice.
    for _ in 0..<2 {
      guard let retry = ledger.planRetry() else {
        return XCTFail("retry after a submit must produce a send plan")
      }
      XCTAssertEqual(retry.question, "what changed today?")
      XCTAssertFalse(retry.countsAsQuestion)
      AnalyticsManager.shared.chatMessageSent(
        messageLength: retry.question.count, source: "query_shell",
        countsAsQuestion: retry.countsAsQuestion)
    }
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 1)
  }

  /// Return pressed during an active send: the production ledger computes the
  /// outcome — no plan, so nothing dispatches and nothing is emitted (the test
  /// mirrors the view: analytics fire only when a plan exists).
  func testReturnDuringActiveSendNeitherDispatchesNorCounts() async {
    var ledger = QueryShellSendLedger()

    if let plan = ledger.planSubmit("while the agent is busy", providerBusy: true) {
      AnalyticsManager.shared.chatMessageSent(
        messageLength: plan.question.count, source: "query_shell",
        countsAsQuestion: plan.countsAsQuestion)
      XCTFail("a busy provider must not produce a send plan")
    }
    // The dropped submit also must not poison 'Try again' with a question
    // that never dispatched.
    XCTAssertNil(ledger.planRetry())
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 0)
    XCTAssertFalse(RatingPromptManager.shared.isVisible)

    // The same question submitted once the provider is free counts normally.
    if let plan = ledger.planSubmit("while the agent is busy", providerBusy: false) {
      AnalyticsManager.shared.chatMessageSent(
        messageLength: plan.question.count, source: "query_shell",
        countsAsQuestion: plan.countsAsQuestion)
    } else {
      XCTFail("a free provider must produce a send plan")
    }
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 1)
  }

  func testQueryShellLedgerRejectsRetryBeforeAnySubmitAndEmptySubmits() {
    var ledger = QueryShellSendLedger()
    XCTAssertNil(ledger.planRetry())
    XCTAssertNil(ledger.planSubmit(nil))
    XCTAssertNil(ledger.planSubmit(""))
    XCTAssertEqual(ledger.planSubmit("q")?.countsAsQuestion, true)
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
