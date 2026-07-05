import XCTest

@testable import Omi_Computer

final class GmailOutcomeParserTests: XCTestCase {

  func testSuccessParsesEmailsBrowserAndSource() {
    let json: [String: Any] = [
      "ok": true,
      "browser": "Arc",
      "source": "atom",
      "emails": [["id": "m1", "subject": "Hello"]],
      "attempts": [["browser": "Arc", "stage": "ok", "reason": "ok", "had_auth": true]],
    ]

    guard case let .success(emails, browser, source) = GmailOutcomeParser.parse(json) else {
      return XCTFail("expected success")
    }

    XCTAssertEqual(browser, "Arc")
    XCTAssertEqual(source, "atom")
    XCTAssertEqual(emails.count, 1)
  }

  func testNotSignedInRetainsEveryProfileAttempt() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "not_signed_in",
      "summary": "No browser is signed into Gmail. Sign into mail.google.com and try again.",
      "attempts": [
        ["browser": "Chrome", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false],
        [
          "browser": "Chrome (Profile 3)", "stage": "auth",
          "reason": "no Google auth cookies", "had_auth": false,
        ],
      ],
    ]

    guard case let .failure(cls, _, attempts) = GmailOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }

    XCTAssertEqual(cls, .notSignedIn)
    XCTAssertEqual(cls.asError.errorDescription, GmailReaderError.notSignedIn.errorDescription)
    XCTAssertEqual(attempts.count, 2)
  }

  func testSessionExpiredMapsToReloginError() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "session_expired",
      "summary": "Your Gmail session expired. Reload mail.google.com to refresh it.",
      "attempts": [
        ["browser": "Chrome", "stage": "fetch", "reason": "HTTP 401", "had_auth": true, "http": 401]
      ],
    ]

    guard case let .failure(cls, summary, _) = GmailOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }

    XCTAssertEqual(cls, .sessionExpired)
    XCTAssertEqual(cls.asError(summary: summary).errorDescription, GmailReaderError.sessionExpired.errorDescription)
  }

  func testNoBrowserAndUnknownFallbacks() {
    guard
      case let .failure(noBrowserClass, _, noBrowserAttempts) = GmailOutcomeParser.parse([
        "ok": false,
        "error_class": "no_browser",
        "summary": "No supported browser with a readable Gmail session was found.",
        "attempts": [],
      ])
    else {
      return XCTFail("expected no browser failure")
    }

    XCTAssertEqual(noBrowserClass, .noBrowser)
    XCTAssertTrue(noBrowserAttempts.isEmpty)

    guard
      case let .failure(unknownClass, summary, _) = GmailOutcomeParser.parse([
        "ok": false, "error_class": "new_shape", "attempts": [],
      ])
    else {
      return XCTFail("expected unknown failure")
    }

    XCTAssertEqual(unknownClass, .unknown)
    XCTAssertFalse(summary.isEmpty)
  }

  func testDiagnosticsLineCarriesOnlyNonSensitiveFields() {
    let attempts = [
      GmailAttempt(
        browser: "Arc",
        stage: "auth",
        reason: "no Google auth cookies",
        hadAuthCookies: false
      )
    ]

    XCTAssertEqual(GmailOutcomeParser.diagnosticsLine(attempts), "Arc[auth:no Google auth cookies]")
  }

  func testBatchSuccessParsesResponsesInOrder() {
    let json: [String: Any] = [
      "ok": true,
      "browser": "Chrome",
      "source": "batch",
      "responses": [
        [
          "id": "query",
          "browser": "Chrome",
          "source": "atom",
          "emails": [["id": "q1", "subject": "Query result"]],
        ],
        [
          "id": "label:atom/inbox",
          "browser": "Chrome",
          "source": "atom",
          "emails": [["id": "l1", "subject": "Inbox result"]],
        ],
      ],
    ]

    guard case let .success(responses) = GmailAtomBatchParser.parse(json) else {
      return XCTFail("expected batch success")
    }

    XCTAssertEqual(responses.map(\.requestID), ["query", "label:atom/inbox"])
    XCTAssertEqual(responses[0].browser, "Chrome")
    XCTAssertEqual(responses[0].source, "atom")
    XCTAssertEqual(responses[0].emails.count, 1)
  }

  func testBatchSuccessWithEmptyResponsesIsSuccessNotFailure() {
    let json: [String: Any] = ["ok": true, "browser": "none", "source": "batch", "responses": []]

    guard case let .success(responses) = GmailAtomBatchParser.parse(json) else {
      return XCTFail("expected batch success for empty responses")
    }
    XCTAssertTrue(responses.isEmpty)
  }

  func testBatchOkWithoutResponsesIsTreatedAsContractFailure() {
    // The helper always emits `responses` on success; its absence is a
    // contract violation, not a single-response payload to synthesize.
    let json: [String: Any] = ["ok": true, "browser": "Chrome", "emails": [["id": "x"]]]

    guard case let .failure(cls, summary, _) = GmailAtomBatchParser.parse(json) else {
      return XCTFail("expected contract failure when responses is missing")
    }
    XCTAssertEqual(cls, .unknown)
    XCTAssertEqual(summary, "Gmail batch response missing responses")
  }

  func testBatchFailureUsesExistingFailureClassification() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "network",
      "summary": "Could not reach Gmail (HTTP 500).",
      "attempts": [
        ["browser": "Chrome", "stage": "fetch", "reason": "HTTP 500", "had_auth": true, "http": 500]
      ],
    ]

    guard case let .failure(cls, summary, attempts) = GmailAtomBatchParser.parse(json) else {
      return XCTFail("expected batch failure")
    }

    XCTAssertEqual(cls, .network)
    XCTAssertEqual(summary, "Could not reach Gmail (HTTP 500).")
    XCTAssertEqual(attempts.count, 1)
  }

  func testConnectionStatusIsConnectedHelper() {
    XCTAssertTrue(GmailConnectionStatus.connected(verifiedAt: Date()).isConnected)
    XCTAssertFalse(GmailConnectionStatus.needsSignIn(message: "x").isConnected)
    XCTAssertFalse(GmailConnectionStatus.error(message: "x").isConnected)
  }
}
