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

  func testForbiddenAndPermissionDeniedRouteToAuthNotLeakSuspicion() {
    // 403 / permission errors are authorization failures, not credential leaks.
    // The leak bucket's copy ("AI service authentication error") is dropped by
    // SentryBeforeSendPolicy, so mislabeling here misdirects the user AND hides
    // a real forbidden-class bug from triage.
    for raw in ["Provider returned 403 Forbidden", "permission denied by upstream"] {
      let classified = AgentErrorClassifier.classify(raw)
      XCTAssertEqual(classified.code, .providerAuthExpired, raw)
      XCTAssertFalse(classified.retryable, raw)
      XCTAssertFalse(
        classified.userMessage.lowercased().contains("ai service authentication error"),
        "must not carry the Sentry-dropped leak copy — \(raw)")
    }
  }

  func testDisabledOrLeakedKeyStillClassifiesAsLeakSuspicion() {
    for raw in ["This key has been disabled", "API key leaked in a public repo", "invalid key"] {
      XCTAssertEqual(AgentErrorClassifier.classify(raw).code, .credentialLeakSuspected, raw)
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

  func testPlanLimitIsNotRetryable() {
    // Live corpus, exact string (~79 events/30d across variants). Retrying just
    // re-hits the cap — the retry-storm pathology the classifier exists to stop.
    let classified = AgentErrorClassifier.classify(
      "You've hit your Free plan limit (30 chat questions per month; 30 used). Upgrade in Settings → Plan and Usage, or wait until the next reset."
    )
    XCTAssertEqual(classified.code, .planLimitReached)
    XCTAssertFalse(classified.retryable)
    XCTAssertFalse(classified.userMessage.lowercased().contains("try again"))
  }

  func testProviderOrModeMisconfigIsNotRetryable() {
    for raw in [
      "Local Claude is available only when the User Claude mode is selected.",
      "Managed Omi agents can only use Omi cloud routing.",
      "Local provider mode is pinned to acp.",
      "Hermes is not available. Make sure Hermes is installed first, then try again.",
    ] {
      let classified = AgentErrorClassifier.classify(raw)
      XCTAssertEqual(classified.code, .agentModeUnavailable, raw)
      XCTAssertFalse(classified.retryable, raw)
    }
  }

  func testAuthRequiredAndByokRouteToAuth() {
    for raw in ["Authentication required", "403 \"byok_validation_failed\""] {
      XCTAssertEqual(AgentErrorClassifier.classify(raw).code, .providerAuthExpired, raw)
    }
  }

  func testRemainingToolSchemaAndLocalDataStringsFromCorpus() {
    XCTAssertEqual(AgentErrorClassifier.classify("400 tools: Tool names must be unique.").code, .toolSchemaRejected)
    XCTAssertEqual(
      AgentErrorClassifier.classify("table adapter_bindings has no column named last_delivered_turn_created_at_ms")
        .code, .localDataError)
  }

  func testUserStopIsNotARetryableError() {
    let classified = AgentErrorClassifier.classify("Response stopped.")
    XCTAssertEqual(classified.code, .userInterrupted)
    XCTAssertFalse(classified.retryable, "a user Stop is not a failure to retry")
  }

  /// Data-driven guard over the live 30-day chat_agent_error corpus (PostHog,
  /// project 302298, pulled 2026-07-22). No production error string may land in
  /// `.unknown` while also being marked retryable when retrying cannot help.
  /// Each tuple: (raw string, mustNotBeUnknown, expectedRetryable).
  func testLiveCorpusIsClassifiedAndRetryabilityIsHonest() {
    let corpus: [(String, Bool, Bool)] = [
      ("Response stopped.", true, false),
      ("AI not available: bridge failed to start", false, true),  // bridge retry can help
      ("AI service is temporarily unavailable. Please try again later.", false, true),
      (
        "You've hit your Free plan limit (30 chat questions per month; 32 used). Upgrade in Settings → Plan and Usage, or wait until the next reset.",
        true, false
      ),
      ("Local Claude is available only when the User Claude mode is selected.", true, false),
      ("Managed Omi agents can only use Omi cloud routing.", true, false),
      ("Authentication required", true, false),
      (
        "400 tool_choice.name 'web_search' cannot be used because this tool only allows calls from ['code_execution_20260120'].",
        true, false
      ),
      ("Local provider mode is pinned to acp.", true, false),
      ("400 Your credit balance is too low to access the Anthropic API.", true, false),
      ("400 tools: Tool names must be unique.", true, false),
      ("pi-mono process exited (code 1)", true, true),
      ("table adapter_bindings has no column named last_delivered_turn_created_at_ms", true, false),
      ("403 \"byok_validation_failed\"", true, false),
      ("Connection error.", true, true),
    ]
    for (raw, mustNotBeUnknown, expectedRetryable) in corpus {
      let c = AgentErrorClassifier.classify(raw)
      if mustNotBeUnknown {
        XCTAssertNotEqual(c.code, .unknown, "should be classified: \(raw)")
      }
      XCTAssertEqual(c.retryable, expectedRetryable, "retryability wrong for: \(raw)")
    }
  }
}
