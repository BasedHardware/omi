import XCTest

@testable import Omi_Computer

final class SendMessageResultTests: XCTestCase {
  private let outcome = MessageSendOutcome(handle: "+14155550123", service: "iMessage", attachedFile: nil)

  private func result(
    _ status: MessageSendOutcomeStatus,
    _ reason: MessageSendConfirmation.UnconfirmedReason? = nil,
    afterError: Bool = false,
    timedOut: Bool = false
  ) throws -> [String: Any] {
    let json = ChatToolExecutor.sendMessageResult(
      outcome,
      confirmation: MessageSendConfirmation(
        status: status, unconfirmedReason: reason, succeededAfterError: afterError, checks: 1, waitedMilliseconds: 0),
      sendTimedOut: timedOut,
      charactersSent: 2)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
  }

  func testDeliveredAndSentAreSuccesses() throws {
    let delivered = try result(.delivered)
    XCTAssertEqual(delivered["ok"] as? Bool, true)
    XCTAssertEqual(delivered["status"] as? String, "delivered")
    XCTAssertNil(delivered["outcome_unknown"])

    let sent = try result(.sent)
    XCTAssertEqual(sent["status"] as? String, "sent")
    XCTAssertNil(sent["outcome_unknown"])
    XCTAssertTrue((sent["summary"] as? String ?? "").contains("not yet delivered"))
  }

  func testUnconfirmedIsAnUnknownOutcomeWithPlainWords() throws {
    for reason in [
      MessageSendConfirmation.UnconfirmedReason.noMatchingRow, .notYetSent, .ambiguous, .historyUnreadable,
      .checkStopped,
    ] {
      let unconfirmed = try result(.unconfirmed, reason)
      XCTAssertEqual(unconfirmed["ok"] as? Bool, true, "an unknown outcome is not a failure")
      XCTAssertNil(unconfirmed["error"], "an error key would record the call as failed")
      XCTAssertEqual(unconfirmed["outcome_unknown"] as? Bool, true, "the ledger must not record it as succeeded")
      XCTAssertEqual(unconfirmed["unconfirmed_reason"] as? String, reason.rawValue)
      let summary = unconfirmed["summary"] as? String ?? ""
      XCTAssertTrue(summary.contains("may or may not have been sent"))
      XCTAssertTrue(summary.contains("check Messages"))
      XCTAssertTrue(summary.contains("Do not send it again"))
    }
  }

  func testNotDeliveredIsAFailureThatIsNotRetried() throws {
    let notDelivered = try result(.notDelivered)
    XCTAssertEqual(notDelivered["ok"] as? Bool, false)
    XCTAssertEqual(notDelivered["status"] as? String, "not_delivered")
    XCTAssertEqual(notDelivered["reason"] as? String, "not_delivered")
    XCTAssertTrue((notDelivered["summary"] as? String ?? "").contains("only if they ask"))
  }

  func testSuccessAfterAnErrorSaysSo() throws {
    let delivered = try result(.delivered, afterError: true)
    XCTAssertEqual(delivered["succeeded_after_error"] as? Bool, true)
    XCTAssertTrue((delivered["summary"] as? String ?? "").contains("error on one attempt first"))
    XCTAssertNil(try result(.delivered)["succeeded_after_error"])
  }

  func testATimedOutSendReportsTheCheckedOutcome() throws {
    let timedOut = try result(.delivered, timedOut: true)
    XCTAssertEqual(timedOut["send_timed_out"] as? Bool, true)
    XCTAssertEqual(timedOut["status"] as? String, "delivered")
    XCTAssertTrue((timedOut["summary"] as? String ?? "").hasPrefix("Messages did not answer in time"))
  }
}
