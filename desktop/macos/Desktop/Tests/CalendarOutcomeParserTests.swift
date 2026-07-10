import XCTest

@testable import Omi_Computer

/// Fixture-driven tests for the calendar fetch outcome classifier.
///
/// These are the "captured observations as fixtures" the integrations
/// philosophy (§7) asks for: the JSON payloads below mirror what the Python
/// cookie helper emits for each real-world failure mode, so we can prove the
/// classification without a browser, cookies, or Python. When a new failure
/// shape shows up in the wild, add its payload here.
final class CalendarOutcomeParserTests: XCTestCase {

  func testSuccessParsesEventsAndBrowser() {
    let json: [String: Any] = [
      "ok": true,
      "browser": "Arc",
      "events": [["id": "1", "summary": "Standup"]],
      "attempts": [["browser": "Arc", "stage": "ok", "reason": "ok", "had_auth": true]],
    ]
    guard case let .success(events, browser) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected success")
    }
    XCTAssertEqual(browser, "Arc")
    XCTAssertEqual(events.count, 1)
  }

  func testSuccessWithZeroEventsStillMeansConnectedSurfaceWorked() {
    let json: [String: Any] = [
      "ok": true,
      "browser": "Chrome (Default)",
      "events": [],
      "attempts": [["browser": "Chrome (Default)", "stage": "ok", "reason": "ok", "had_auth": true]],
    ]
    guard case let .success(events, browser) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected success")
    }
    XCTAssertEqual(browser, "Chrome (Default)")
    XCTAssertTrue(events.isEmpty)
  }

  /// The exact bug from the screenshot: cookies decrypt fine but no profile is
  /// signed into Google. This must classify as `notSignedIn` (an actionable
  /// login prompt), NOT the old catch-all "Network error".
  func testNotSignedInWhenNoProfileHasAuthCookies() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "not_signed_in",
      "summary": "No browser is signed into Google. Sign into calendar.google.com and try again.",
      "attempts": [
        ["browser": "Chrome (Default)", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false],
        ["browser": "Chrome (Profile 3)", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false],
      ],
    ]
    guard case let .failure(cls, _, attempts) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .notSignedIn)
    XCTAssertEqual(cls.asError(), .notSignedIn)
    // Every attempt is retained — not just the last one (no last-writer-wins).
    XCTAssertEqual(attempts.count, 2)
  }

  func testSessionExpiredMapsToReloginError() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "session_expired",
      "summary": "Your Google session expired. Reload calendar.google.com to refresh it.",
      "attempts": [
        ["browser": "Chrome (Default)", "stage": "fetch", "reason": "HTTP 401", "had_auth": true, "http": 401]
      ],
    ]
    guard case let .failure(cls, _, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .sessionExpired)
    XCTAssertEqual(cls.asError(), .sessionExpired)
  }

  func testInvalidCalendarAPIKeyMapsToConfigurationError() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "configuration",
      "summary": "Calendar API key is invalid or unavailable.",
      "attempts": [
        [
          "browser": "Chrome",
          "stage": "fetch",
          "reason": "HTTP 400: INVALID_ARGUMENT: API key not valid. Please pass a valid API key.: badRequest",
          "had_auth": true,
          "http": 400,
        ]
      ],
    ]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .configuration)
    XCTAssertEqual(cls.asError(summary: summary), .configurationError("Calendar API key is invalid or unavailable."))
  }

  func testMissingCalendarAPIKeyMapsToConfigurationError() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "configuration",
      "summary": "Calendar API key is invalid or unavailable.",
      "attempts": [
        [
          "browser": "Chrome",
          "stage": "fetch",
          "reason": "HTTP 403: PERMISSION_DENIED: Method doesn't allow unregistered callers.",
          "had_auth": true,
          "http": 403,
        ]
      ],
    ]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .configuration)
    XCTAssertEqual(cls.asError(summary: summary).errorDescription, "Couldn't use Google Calendar: Calendar API key is invalid or unavailable.")
  }

  func testNetworkSummaryAvoidsDoublePrefix() {
    let error = CalendarFailureClass.network.asError(summary: "Could not reach Google Calendar (HTTP 500).")
    XCTAssertEqual(error.errorDescription, "Couldn't reach Google Calendar: (HTTP 500).")
  }

  func testNoBrowserWhenNothingScanned() {
    let json: [String: Any] = [
      "ok": false, "error_class": "no_browser",
      "summary": "No supported browser with a readable session was found.", "attempts": [],
    ]
    guard case let .failure(cls, _, attempts) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .noBrowser)
    XCTAssertTrue(attempts.isEmpty)
  }

  func testUnknownErrorClassFallsBackGracefully() {
    let json: [String: Any] = ["ok": false, "error_class": "something_new", "attempts": []]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .unknown)
    XCTAssertEqual(summary, cls.plainFallbackSummary)
    let error = cls.asError(summary: summary)
    XCTAssertEqual(error.errorDescription, "Couldn't reach Google Calendar: unexpected error")
  }

  func testUnknownErrorClassPreservesPythonSummary() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "something_new",
      "summary": "New failure mode from Python helper.",
      "attempts": [],
    ]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .unknown)
    let error = cls.asError(summary: summary)
    XCTAssertEqual(error, .networkError("New failure mode from Python helper."))
    XCTAssertEqual(
      error.errorDescription,
      "Couldn't reach Google Calendar: New failure mode from Python helper."
    )
  }

  func testNetworkSummarySurvivesFinalErrorMapping() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "network",
      "summary": "Could not reach Google Calendar (HTTP 500).",
      "attempts": [
        ["browser": "Chrome (Default)", "stage": "fetch", "reason": "HTTP 500", "had_auth": true, "http": 500]
      ],
    ]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(cls, .network)
    let error = cls.asError(summary: summary)
    XCTAssertEqual(error, .networkError("(HTTP 500)."))
    XCTAssertEqual(error.errorDescription, "Couldn't reach Google Calendar: (HTTP 500).")
  }

  func testNetworkFailureWithoutSummaryAvoidsDoublePrefix() {
    let json: [String: Any] = [
      "ok": false,
      "error_class": "network",
      "attempts": [],
    ]
    guard case let .failure(cls, summary, _) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    XCTAssertEqual(summary, cls.plainFallbackSummary)
    let error = cls.asError(summary: summary)
    XCTAssertEqual(
      error.errorDescription,
      "Couldn't reach Google Calendar: please check your connection and try again"
    )
  }

  /// Diagnostics must be safe to log and upload: browser names, stages, and
  /// reasons only — never a cookie value (philosophy §7 sanitization).
  func testDiagnosticsLineCarriesOnlyNonSensitiveFields() {
    let json: [String: Any] = [
      "ok": false, "error_class": "not_signed_in", "summary": "x",
      "attempts": [
        ["browser": "Arc", "stage": "auth", "reason": "no Google auth cookies", "had_auth": false]
      ],
    ]
    guard case let .failure(_, _, attempts) = CalendarOutcomeParser.parse(json) else {
      return XCTFail("expected failure")
    }
    let line = CalendarOutcomeParser.diagnosticsLine(attempts)
    XCTAssertEqual(line, "Arc[auth:no Google auth cookies]")
  }

  func testConnectionStatusIsConnectedHelper() {
    XCTAssertTrue(CalendarConnectionStatus.connected(verifiedAt: Date()).isConnected)
    XCTAssertFalse(CalendarConnectionStatus.needsSignIn(message: "x").isConnected)
    XCTAssertFalse(CalendarConnectionStatus.error(message: "x").isConnected)
  }

  func testFetchParameterNormalizationClampsProbeBoundaries() {
    XCTAssertEqual(
      CalendarFetchParameters.normalized(daysBack: -7, daysForward: -1, maxResults: 0),
      CalendarFetchParameters(daysBack: 0, daysForward: 0, maxResults: 1)
    )
    XCTAssertEqual(
      CalendarFetchParameters.normalized(daysBack: 9999, daysForward: 9999, maxResults: 9999),
      CalendarFetchParameters(daysBack: 3650, daysForward: 3650, maxResults: 2500)
    )
  }

  func testCalendarReadsWaitForBackendServedAPIKeys() throws {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL = testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/CalendarReaderService.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    guard let readRange = source.range(of: "func readEvents("),
      let keyWaitRange = source.range(of: "await APIKeyService.shared.waitForKeys()", range: readRange.upperBound..<source.endIndex),
      let fetchRange = source.range(of: "fetchCalendarViaCookies(", range: readRange.upperBound..<source.endIndex)
    else {
      return XCTFail("Calendar reads must wait for backend-served API keys before fetching")
    }

    XCTAssertLessThan(
      keyWaitRange.lowerBound,
      fetchRange.lowerBound,
      "Calendar reads must not hit Google before GOOGLE_CALENDAR_API_KEY has loaded"
    )
  }
}
