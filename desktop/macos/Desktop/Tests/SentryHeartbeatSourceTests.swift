import XCTest

/// Regression guard for #9191: the periodic session heartbeat must be recorded
/// as a Sentry breadcrumb, never captured as an event/message. Capturing it as
/// an event created millions of unresolved Sentry issues that buried real crashes.
final class SentryHeartbeatSourceTests: XCTestCase {
  func testHeartbeatUsesBreadcrumbNotCapturedEvent() throws {
    let source = try readSource("Sources/OmiApp.swift")

    // The heartbeat timer must add a breadcrumb, not capture a Sentry event.
    XCTAssertTrue(
      source.contains("Breadcrumb(level: .info, category: \"heartbeat\")"),
      "Session heartbeat should be recorded as a breadcrumb")
    XCTAssertFalse(
      source.contains("SentrySDK.capture(message: \"Session Heartbeat\")"),
      "Session heartbeat must not be captured as a Sentry event/issue (see #9191)")
  }

  private func readSource(_ relativePath: String) throws -> String {
    let testFile = URL(fileURLWithPath: #filePath)
    let desktopDir = testFile.deletingLastPathComponent().deletingLastPathComponent()
    let file = desktopDir.appendingPathComponent(relativePath)
    return try String(contentsOf: file, encoding: .utf8)
  }
}
