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

  func testAppDelegateHeartbeatSourceUsesBreadcrumbNotCaptureMessage() throws {
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/OmiApp.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(source.contains("SentryHeartbeatTelemetry.recordSessionHeartbeat()"))
    XCTAssertFalse(source.contains("SentrySDK.capture(message: \"Session Heartbeat\")"))
  }
}
