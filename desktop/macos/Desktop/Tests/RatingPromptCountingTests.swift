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
    ledger.recordAccepted(submit)

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
    let ledger = QueryShellSendLedger()

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

  /// A REAL ChatProvider rejection through the production sendMessage seam: a
  /// fresh provider has no runtime owner, so sendMessage refuses before any
  /// network work and never invokes onAccepted (the only place analytics,
  /// counting, and retry state now commit — ChatProvider.swift invokes
  /// onAccepted only after every rejection guard has passed).
  func testRealProviderRejectionEmitsNothingAndPreservesLedger() async {
    let provider = ChatProvider()
    var ledger = QueryShellSendLedger()
    guard let plan = ledger.planSubmit("did I miss anything?", providerBusy: provider.isSending)
    else {
      return XCTFail("an idle provider must yield a plan")
    }

    var accepted = false
    let result = await provider.sendMessage(
      plan.question,
      onAccepted: {
        accepted = true
        AnalyticsManager.shared.chatMessageSent(
          messageLength: plan.question.count, source: "query_shell",
          countsAsQuestion: plan.countsAsQuestion)
        ledger.recordAccepted(plan)
      })

    XCTAssertNil(result)
    XCTAssertFalse(accepted, "a refused send must never reach onAccepted")
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 0)
    // The rejected question must not become what 'Try again' re-sends.
    XCTAssertNil(ledger.planRetry())

    // The acceptance path commits everything the rejection skipped.
    ledger.recordAccepted(plan)
    AnalyticsManager.shared.chatMessageSent(
      messageLength: plan.question.count, source: "query_shell",
      countsAsQuestion: plan.countsAsQuestion)
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 1)
    XCTAssertEqual(ledger.planRetry()?.question, "did I miss anything?")
    XCTAssertEqual(ledger.planRetry()?.countsAsQuestion, false)
  }

  /// Non-QueryShell surfaces (home ask bar, dashboard chat, onboarding
  /// opener) all send through sendMainDraft, which forwards onAccepted to the
  /// same sendMessage guard chain — a REAL rejection must emit nothing there
  /// either.
  func testRealSendMainDraftRejectionEmitsNothing() async {
    let provider = ChatProvider()
    var accepted = false
    let result = await provider.sendMainDraft(
      "ask bar question",
      onAccepted: {
        accepted = true
        AnalyticsManager.shared.chatMessageSent(
          messageLength: 16, source: "home_ask_bar")
      })
    XCTAssertNil(result)
    XCTAssertFalse(accepted)
    await drainCounterHops()
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 0)
  }

  func testQueryShellLedgerRejectsRetryBeforeAnySubmitAndEmptySubmits() {
    let ledger = QueryShellSendLedger()
    XCTAssertNil(ledger.planRetry())
    XCTAssertNil(ledger.planSubmit(nil))
    XCTAssertNil(ledger.planSubmit(""))
    XCTAssertEqual(ledger.planSubmit("q")?.countsAsQuestion, true)
    // Planning alone commits nothing; only acceptance does.
    XCTAssertNil(ledger.planRetry())
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
