import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the bounded agent-error classifier. Cases mirror the
/// observed 30-day chat_agent_error corpus that motivated it.
final class AgentErrorClassifierTests: XCTestCase {

  func testBillingExhaustionIsNotRetryableAndNamesTheFix() {
    let classified = AgentErrorClassifier.classify(
      "400 Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."
    )
    XCTAssertEqual(classified.code, .providerBillingExhausted)
    XCTAssertFalse(classified.retryable, "retrying an exhausted balance produced measured retry storms")
    XCTAssertFalse(
      classified.userMessage.lowercased().contains("try again"),
      "copy must not prescribe retries for an unretryable billing error")
    XCTAssertTrue(classified.userMessage.contains("credit balance"))
  }

  func testAuthExpiryRoutesToReconnectNotGenericError() {
    for raw in [
      "401 \"invalid_token\"",
      "Internal error: Failed to authenticate. API Error: 401 {\"type\":\"error\",\"error\":{\"type\":\"authentication_error\"}}",
    ] {
      let classified = AgentErrorClassifier.classify(raw)
      XCTAssertEqual(classified.code, .providerAuthExpired, raw)
      XCTAssertFalse(classified.retryable, raw)
    }
  }

  func testConnectionErrorsAreRetryable() {
    let classified = AgentErrorClassifier.classify("Connection error.")
    XCTAssertEqual(classified.code, .connectionFailed)
    XCTAssertTrue(classified.retryable)
  }

  func testRuntimeCrashesAreRetryable() {
    for raw in ["Error: pi-mono process exited (code 1)", "Uncaught: pi-mono process not running"] {
      let classified = AgentErrorClassifier.classify(raw)
      XCTAssertEqual(classified.code, .runtimeCrashed, raw)
      XCTAssertTrue(classified.retryable, raw)
    }
  }

  func testLocalDataErrorsAreClassifiedForBugTracking() {
    for raw in ["cannot start a transaction within a transaction", "database disk image is malformed"] {
      XCTAssertEqual(AgentErrorClassifier.classify(raw).code, .localDataError, raw)
    }
  }

  func testOversizedPayloadNamesTheCause() {
    let classified = AgentErrorClassifier.classify("413 Failed to buffer the request body: length limit exceeded")
    XCTAssertEqual(classified.code, .payloadTooLarge)
    XCTAssertFalse(classified.retryable)
  }

  func testToolSchemaRejectionDoesNotBlameTheUser() {
    let classified = AgentErrorClassifier.classify(
      "400 tools.11.custom.input_schema: input_schema does not support oneOf, allOf, or anyOf at the top level")
    XCTAssertEqual(classified.code, .toolSchemaRejected)
    XCTAssertTrue(classified.userMessage.contains("isn't caused by your message"))
  }

  func testOAuthTimeoutOffersReconnect() {
    let classified = AgentErrorClassifier.classify("OAuth callback timed out (10 minutes)")
    XCTAssertEqual(classified.code, .oauthTimeout)
    XCTAssertTrue(classified.userMessage.contains("reconnect") || classified.userMessage.contains("Reconnect"))
  }

  func testUnknownPreservesReadableMessagesAndCoversEmpty() {
    let readable = AgentErrorClassifier.classify("The model produced malformed output for this request.")
    XCTAssertEqual(readable.code, .unknown)
    XCTAssertEqual(readable.userMessage, "The model produced malformed output for this request.")
    let empty = AgentErrorClassifier.classify("")
    XCTAssertEqual(empty.userMessage, "Something went wrong. Please try again.")
  }
}
