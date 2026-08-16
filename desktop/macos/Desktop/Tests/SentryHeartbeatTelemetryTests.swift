import Sentry
import XCTest

@testable import Omi_Computer

final class SentryHeartbeatTelemetryTests: XCTestCase {
  func testSessionHeartbeatBreadcrumbShape() {
    let breadcrumb = SentryHeartbeatTelemetry.makeSessionHeartbeatBreadcrumb()
    XCTAssertEqual(breadcrumb.message, "Session Heartbeat")
    XCTAssertEqual(breadcrumb.category, "session")
    XCTAssertEqual(breadcrumb.level, .info)
    XCTAssertEqual(breadcrumb.data?["event_type"] as? String, "heartbeat")
  }

  func testHeartbeatIssueEventIsRejectedByProductionBeforeSendPolicy() {
    XCTAssertTrue(
      AppDelegate.shouldDropSentryEvent(
        isUserReport: false,
        isDev: false,
        urlTag: nil,
        messageFormatted: "Session Heartbeat",
        exceptions: []))
  }
}
