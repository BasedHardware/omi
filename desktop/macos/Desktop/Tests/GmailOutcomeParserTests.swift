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

  func testBootstrapSuccessAfterAtomAuthFailureIsStillSuccess() {
    let json: [String: Any] = [
      "ok": true,
      "browser": "Chrome",
      "source": "bootstrap",
      "emails": [["id": "m1", "subject": "Hello"]],
      "attempts": [
        ["browser": "Chrome", "stage": "fetch", "reason": "HTTP 401", "had_auth": true, "http": 401],
        ["browser": "Chrome", "stage": "ok", "reason": "ok", "had_auth": true],
      ],
    ]

    guard case let .success(emails, browser, source) = GmailOutcomeParser.parse(json) else {
      return XCTFail("expected success")
    }

    XCTAssertEqual(browser, "Chrome")
    XCTAssertEqual(source, "bootstrap")
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
    XCTAssertTrue(cls.needsSignIn)
    XCTAssertEqual(attempts.count, 2)
  }

  func testClassifiedFailurePreservesProviderSummary() {
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
    let error = GmailReaderError.provider(cls, message: summary)
    XCTAssertEqual(error.errorDescription, summary)
    XCTAssertEqual(error.classification, "session_expired")
    XCTAssertTrue(error.needsSignIn)
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
    XCTAssertEqual(summary, GmailFailureClass.unknown.defaultMessage)
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

  func testConnectionStatusIsConnectedHelper() {
    XCTAssertTrue(GmailConnectionStatus.connected(verifiedAt: Date()).isConnected)
    XCTAssertFalse(GmailConnectionStatus.needsSignIn(message: "x").isConnected)
    XCTAssertFalse(GmailConnectionStatus.error(message: "x").isConnected)
  }
}
