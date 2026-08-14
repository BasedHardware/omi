import XCTest

@testable import Omi_Computer

/// Coverage for the policy a failed chat turn leaves behind.
///
/// The live defect: with the backend answering every turn `HTTP 402`, six
/// failed turns produced six consecutive user rows with nothing between them.
/// The turn's assistant row stayed empty, `projectJournalTurns` deletes an
/// empty `.failed` row as a placeholder, and the only account of the failure
/// was the provider-wide `errorMessage` — dismissible, overwritten by the next
/// turn, gone on relaunch. A reader could not tell which question failed.
final class ChatTurnFailureNoticeTests: XCTestCase {
  /// The exact string the running build logged on every turn. It has to reach
  /// the reader as the classifier's billing copy, and it must not invite a
  /// retry that cannot work.
  func testBareHTTP402BecomesTheBillingMarker() {
    let notice = ChatTurnFailureNotice.forFailure(
      errorDescription: "HTTP 402 status code (no body)",
      presentsUserError: true
    )

    XCTAssertEqual(
      notice?.text,
      AgentErrorClassifier.classify("HTTP 402 status code (no body)").userMessage,
      "The marker must say exactly what the classifier says — one wording, not a second vocabulary"
    )
    XCTAssertEqual(notice?.retryable, false, "Payment Required is never fixed by resending")
    XCTAssertNotNil(notice?.text.range(of: "Plan and Usage"), "The marker keeps the classifier's fix path")
  }

  /// Stop and supersession are cancellations, never errors (desktop
  /// analytics-integrity contract). Nothing went wrong, so nothing is marked.
  func testCancelledEndingsLeaveNoMarker() {
    XCTAssertNil(
      ChatTurnFailureNotice.forFailure(
        errorDescription: "connection error",
        presentsUserError: false
      ),
      "A cancelled turn must not be marked as a failure"
    )
    XCTAssertNil(
      ChatTurnFailureNotice.forFailure(errorDescription: "Response stopped", presentsUserError: true),
      "An interrupted turn is the reader's own doing and needs no explanation"
    )
  }

  /// `.unknown` makes the classifier echo the provider's raw string back. A
  /// dismissible banner can afford that; a row that stays in the transcript
  /// cannot.
  func testUnclassifiedFailureNeverPersistsRawTransportText() {
    let raw = "ECONN_WEIRD_9931: upstream frobnicator desynchronized"
    let notice = ChatTurnFailureNotice.forFailure(errorDescription: raw, presentsUserError: true)

    XCTAssertEqual(notice?.text, ChatTurnFailureNotice.unclassifiedText)
    XCTAssertFalse(
      notice?.text.contains("frobnicator") ?? true,
      "A durable transcript row must not carry raw transport text"
    )
    XCTAssertEqual(notice?.retryable, true, "An unclassified failure is still worth one more try")
  }

  /// Copy that is already written for the reader must survive verbatim —
  /// re-classifying it would collapse "Response took too long" into the
  /// generic sentence and lose the one useful fact.
  func testStatedCopyIsNotReclassified() {
    let notice = ChatTurnFailureNotice.stating("Response took too long. Try again.", retryable: true)

    XCTAssertEqual(notice?.text, "Response took too long. Try again.")
    XCTAssertEqual(notice?.retryable, true)
    XCTAssertNil(ChatTurnFailureNotice.stating("   ", retryable: true), "Blank copy is not a marker")
  }

  /// The row must never be left empty: an empty `.failed` row is exactly what
  /// the journal projection deletes, and deleting it is what orphaned the
  /// question.
  func testTranscriptContentIsNeverEmptyAndKeepsPartialOutput() {
    guard let notice = ChatTurnFailureNotice.stating("Ran out of credit.", retryable: false) else {
      return XCTFail("expected a marker")
    }

    XCTAssertEqual(notice.transcriptContent(partialText: ""), "Ran out of credit.")
    XCTAssertEqual(notice.transcriptContent(partialText: "   \n "), "Ran out of credit.")
    XCTAssertEqual(
      notice.transcriptContent(partialText: "Here is what I found so far"),
      "Here is what I found so far\n\nRan out of credit.",
      "A partial answer is kept, and still says it did not finish"
    )
  }

  /// A card that only repeats the row is the second wording this type exists
  /// to remove. A card that carries a recovery the transcript cannot offer
  /// stays.
  func testOnlyCardsWithARecoveryTheTranscriptCannotOfferSurvive() {
    XCTAssertEqual(ChatTurnFailureNotice.retainedCard(.authRequired), .authRequired)
    XCTAssertEqual(
      ChatTurnFailureNotice.retainedCard(.bridgeUnavailable(reason: .nodeMissing)),
      .bridgeUnavailable(reason: .nodeMissing)
    )
    XCTAssertNil(
      ChatTurnFailureNotice.retainedCard(.timeout(toolName: nil)),
      "Retry is not a recovery the card owns — the question is in the transcript and the text is back in the composer"
    )
    XCTAssertNil(ChatTurnFailureNotice.retainedCard(.noDataFound))
    XCTAssertNil(ChatTurnFailureNotice.retainedCard(nil))
  }

  /// #11464 recycled the poisoned worker and rewrote the user copy to "send
  /// again". The 402 classifier only saw that wrap, so the transcript invited
  /// a retry that cannot work. `forTurn` must classify the technical status.
  func testRecycledWorkerBillingFailureKeepsTheBillingMarker() {
    let error = BridgeError.agentRuntimeFailure(
      AgentRuntimeFailure(
        code: "adapter_execution_failed",
        userMessage: "The local agent reset its session after an error. Send your message again.",
        technicalMessage: "HTTP 402 status code (no body)",
        source: "adapter_execution",
        adapterId: "pi-mono",
        retryable: true,
        recoveryAction: "worker_recycled",
        recoveryOutcome: "recovered",
        retryDisposition: "next_send"
      )
    )
    let notice = ChatTurnFailureNotice.forTurn(
      error: error,
      watchdogFired: false,
      toolStallAbortFired: false,
      timeoutMessage: nil,
      providerAuthMessage: "Reconnect Claude in Settings."
    )

    XCTAssertEqual(
      notice?.text,
      AgentErrorClassifier.classify("HTTP 402 status code (no body)").userMessage
    )
    XCTAssertEqual(notice?.retryable, false)
    XCTAssertFalse(
      notice?.text.contains("Send your message again") ?? true,
      "the recycled-worker wrap must not reach the transcript"
    )
  }
}
