import XCTest

@testable import Omi_Computer

final class UserFacingErrorPresentationTests: XCTestCase {
  func testHidesRawBackendDetailOnNonChatSurfaces() {
    let message = UserFacingErrorPresentation.message(
      for: APIError.httpError(statusCode: 404, detail: "route v1/internal-control was not found"),
      while: .dashboard
    )

    XCTAssertEqual(message, "Couldn't refresh the dashboard. Try again.")
    XCTAssertFalse(message.contains("internal-control"))
  }

  func testUsesSignInRecoveryForUnauthorizedRequests() {
    XCTAssertEqual(
      UserFacingErrorPresentation.message(for: APIError.unauthorized, while: .memories),
      "Please sign in again, then try once more."
    )
  }

  func testHidesDecodingDiagnostics() {
    let decodingError = DecodingError.keyNotFound(
      CodingKeys.example,
      .init(codingPath: [], debugDescription: "unexpected backend field")
    )

    XCTAssertEqual(
      UserFacingErrorPresentation.message(for: APIError.decodingError(decodingError), while: .screenshots),
      "Omi received an unexpected response. Try again."
    )
  }

  func testSanitizesStoredErrorCopyAtDisplayTime() {
    XCTAssertEqual(
      UserFacingErrorPresentation.message(
        from: "route v1/internal-control was not found (404)",
        while: .chatSessions
      ),
      "Couldn't load chats. Try again."
    )
    XCTAssertEqual(
      UserFacingErrorPresentation.message(
        from: "Didn't hear back from X. If you approved access, try again.",
        while: .integration("X")
      ),
      "Didn't hear back from X. If you approved access, try again."
    )
  }

  /// The connector sheet stores an operation's user-facing message as a plain
  /// String and re-sanitizes it at display time, so any connector error whose
  /// copy the sanitizer rejects reaches the user as "Couldn't connect to
  /// <name>. Try again." — the next step the taxonomy exists to give is lost.
  ///
  /// Driven off the production enums rather than copied literals: editing a
  /// message into a shape the sanitizer drops fails here instead of shipping.
  func testEveryGoogleConnectorErrorSurvivesDisplaySanitization() {
    let calendarErrors: [CalendarReaderError] = [
      .noBrowserFound,
      .notSignedIn,
      .sessionExpired,
      .cookieDecryptionFailed("browser session could not be decrypted"),
      .networkError("connection reset"),
      .configurationError("API key is invalid or unavailable"),
      .pythonNotFound,
    ]
    let gmailErrors: [GmailReaderError] = [
      .noBrowserFound,
      .noGmailCookies,
      .notSignedIn,
      .sessionExpired,
      .cookieDecryptionFailed("browser session could not be decrypted"),
      .networkError("connection reset"),
      .authFailed,
      .pythonNotFound,
    ]

    for description in calendarErrors.compactMap(\.errorDescription) {
      XCTAssertEqual(
        UserFacingErrorPresentation.message(from: description, while: .integration("Calendar")),
        description,
        "Calendar copy was replaced by the generic fallback"
      )
    }
    for description in gmailErrors.compactMap(\.errorDescription) {
      XCTAssertEqual(
        UserFacingErrorPresentation.message(from: description, while: .integration("Gmail")),
        description,
        "Gmail copy was replaced by the generic fallback"
      )
    }
  }

  /// The other direction: widening the sanitizer must not start leaking the raw
  /// system text it exists to hide.
  func testStillHidesRawSystemErrorText() {
    let raw = [
      "The operation couldn't be completed. (NSURLErrorDomain error -1009.)",
      "The operation couldn't be completed. (NSPOSIXErrorDomain error 2.)",
      "Error Domain=kCFErrorDomainCFNetwork Code=310",
      "GET https://api.omi.me/v1/dev/user/memories failed",
      "upstream returned 503 while reading the response",
      "sqlite: prepare: step: no such table: cookies",
    ]

    for text in raw {
      XCTAssertEqual(
        UserFacingErrorPresentation.message(from: text, while: .integration("Calendar")),
        "Couldn't connect to Calendar. Try again.",
        "raw system text leaked to the user: \(text)"
      )
    }
  }

  func testProvidesNetworkRecovery() {
    XCTAssertEqual(
      UserFacingErrorPresentation.message(
        for: URLError(.notConnectedToInternet),
        while: .integration("Gmail")
      ),
      "Check your connection and try again."
    )
  }
}

private enum CodingKeys: String, CodingKey {
  case example
}
