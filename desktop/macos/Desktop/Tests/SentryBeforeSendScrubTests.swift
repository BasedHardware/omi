import XCTest

@testable import Omi_Computer

/// SET-05: the Sentry `beforeSend` drop list must scrub known-noisy / non-actionable
/// events — dev-build events, localhost/tunnel-tagged HTTP errors, transient network
/// codes, backend key-expiry messages, and transient `AuthError.notSignedIn` — while
/// letting genuine production errors and user feedback through.
///
/// Pins `AppDelegate.shouldDropSentryEvent`, the pure decision extracted from the
/// SDK `options.beforeSend` closure. `true` = the event is dropped (`beforeSend`
/// returns nil).
final class SentryBeforeSendScrubTests: XCTestCase {

  private func drop(
    isUserReport: Bool = false,
    isDev: Bool = false,
    url: String? = nil,
    message: String? = nil,
    exceptions: [(type: String, value: String)] = []
  ) -> Bool {
    AppDelegate.shouldDropSentryEvent(
      isUserReport: isUserReport,
      isDev: isDev,
      urlTag: url,
      messageFormatted: message,
      exceptions: exceptions)
  }

  func testKeepsGenuineProductionEvent() {
    XCTAssertFalse(
      drop(message: "TasksStore: failed to persist reorder"),
      "a genuine prod error must reach Sentry")
    XCTAssertFalse(
      drop(exceptions: [("Omi_Computer.SomeError", "boom")]),
      "an unrecognized exception must reach Sentry")
  }

  func testUserReportIsKeptFromEveryBuildIncludingDev() {
    XCTAssertFalse(
      drop(isUserReport: true, isDev: true),
      "user feedback must reach Sentry even from dev builds")
  }

  func testDropsNonReportDevBuildEvents() {
    XCTAssertTrue(
      drop(isDev: true, message: "dev crash noise"),
      "non-report dev events pollute production Sentry data and must be dropped")
  }

  func testDropsHeartbeatIssueEventButKeepsNormalProductionEvents() {
    XCTAssertTrue(drop(message: "Session Heartbeat"))
    XCTAssertTrue(drop(message: "  session heartbeat\n"))
    XCTAssertFalse(drop(message: "Session refresh failed"))
  }

  func testDropsLocalAndTunnelUrlTaggedErrors() {
    for u in [
      "http://localhost:8080/v1/x", "https://127.0.0.1:9000/y",
      "https://abc-def.trycloudflare.com/z",
    ] {
      XCTAssertTrue(drop(url: u), "\(u) is a local/tunnel URL → drop")
    }
    XCTAssertFalse(
      drop(url: "https://api.omi.me/v1/tasks"),
      "a real backend URL must not be dropped")
  }

  func testDropsTransientNetworkExceptionsByDomainAndCode() {
    XCTAssertTrue(drop(exceptions: [("NSURLErrorDomain", "The request timed out. Code=-1001")]))
    XCTAssertTrue(
      drop(exceptions: [("NSURLErrorDomain", "offline (Code: -1009)")]),
      "both `Code=` and `Code: ` spellings must match")
    XCTAssertTrue(drop(exceptions: [("NSPOSIXErrorDomain", "Connection reset Code=54")]))
    XCTAssertFalse(
      drop(exceptions: [("NSURLErrorDomain", "SSL error Code=-1200")]),
      "an unlisted URL error code must not be dropped")
    XCTAssertFalse(
      drop(exceptions: [("NSPOSIXErrorDomain", "Code=-1001")]),
      "a code only counts within its own error domain")
  }

  func testDropsBackendKeyExpiryAndAuthFailureMessages() {
    for m in [
      "Gemini API key expired", "please renew the api key", "reason: API_KEY_INVALID",
      "AI service authentication error", "backend returned invalid_auth on batch",
    ] {
      XCTAssertTrue(drop(message: m), "\"\(m)\" is a server-side key issue → drop")
    }
  }

  func testDropsTransientNotSignedInAuthErrorOnly() {
    XCTAssertTrue(
      drop(exceptions: [("Omi_Computer.AuthError", "notSignedIn")]),
      "notSignedIn is a transient refresh failure the 30s timer recovers")
    XCTAssertFalse(
      drop(exceptions: [("Omi_Computer.AuthError", "keychainWriteFailed")]),
      "other AuthError cases are actionable and must reach Sentry")
  }

  func testDropOrderKeepsUserReportAboveTheDevGate() {
    // User reports are checked before the dev gate, so a dev-build user report survives.
    XCTAssertFalse(drop(isUserReport: true, isDev: true, message: "User Report: broken"))
    // And a dev-build non-report is still dropped even if it looks otherwise genuine.
    XCTAssertTrue(drop(isUserReport: false, isDev: true, message: "genuine-looking error"))
  }
}
