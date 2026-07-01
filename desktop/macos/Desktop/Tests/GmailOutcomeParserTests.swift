import XCTest

@testable import Omi_Computer

final class GmailOutcomeParserTests: XCTestCase {
  func testNotSignedInRetainsAllBrowserAttempts() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "not_signed_in",
      "summary": "No browser is signed into Gmail. Sign into mail.google.com and try again.",
      "attempts": [
        ["browser": "Chrome (Default)", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false],
        ["browser": "Chrome (Profile 3)", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false],
      ],
    ]

    let (cls, _, attempts) = GmailOutcomeParser.failure(from: json)
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
        ["browser": "Arc", "stage": "fetch", "reason": "atom HTTP 401", "had_auth": true, "http": 401]
      ],
    ]

    let (cls, summary, attempts) = GmailOutcomeParser.failure(from: json)
    XCTAssertEqual(cls, .sessionExpired)
    XCTAssertEqual(cls.asError.errorDescription, GmailReaderError.sessionExpired.errorDescription)
    XCTAssertEqual(summary, "Your Gmail session expired. Reload mail.google.com to refresh it.")
    XCTAssertEqual(attempts.first?.hadAuthCookies, true)
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
}
