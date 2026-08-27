import XCTest

@testable import Omi_Computer

private final class Box<T>: @unchecked Sendable {
  var value: T
  init(_ value: T) { self.value = value }
}

/// Contract tests for `floating_bar_query_sent` source attribution. The capture
/// seam lives on `AnalyticsManager`'s main-actor boundary so tests observe the
/// real event name and payload without initializing PostHog.
@MainActor
final class FloatingBarQueryAnalyticsTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  override func tearDown() async throws {
    AnalyticsManager.shared.setFloatingBarQueryTelemetryCaptureForTests(nil)
    try await super.tearDown()
  }

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setFloatingBarQueryTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
  }

  func testVisibleQuerySourceSelectsTypedVsPtt() {
    XCTAssertEqual(FloatingBarQuerySource.visibleQuery(fromVoice: false), .typed)
    XCTAssertEqual(FloatingBarQuerySource.visibleQuery(fromVoice: true), .ptt)
  }

  func testSourceRawValuesAreStableAndDistinct() {
    XCTAssertEqual(FloatingBarQuerySource.typed.rawValue, "typed")
    XCTAssertEqual(FloatingBarQuerySource.ptt.rawValue, "ptt")
    XCTAssertEqual(FloatingBarQuerySource.pttVoiceOnly.rawValue, "ptt_voice_only")
    XCTAssertEqual(FloatingBarQuerySource.pttRealtime.rawValue, "ptt_realtime")
    XCTAssertEqual(Set(FloatingBarQuerySource.allCases.map(\.rawValue)).count, FloatingBarQuerySource.allCases.count)
  }

  func testQuerySentIncludesSourceAndExistingShape() {
    startCapturing()

    AnalyticsManager.shared.floatingBarQuerySent(
      messageLength: 12,
      hasScreenshot: true,
      source: .typed
    )
    AnalyticsManager.shared.floatingBarQuerySent(
      messageLength: 0,
      hasScreenshot: false,
      source: .pttRealtime
    )

    XCTAssertEqual(capturedBox.value.count, 2)
    XCTAssertEqual(capturedBox.value[0].0, "floating_bar_query_sent")
    XCTAssertEqual(capturedBox.value[0].1["message_length"] as? Int, 12)
    XCTAssertEqual(capturedBox.value[0].1["has_screenshot"] as? Bool, true)
    XCTAssertEqual(capturedBox.value[0].1["source"] as? String, "typed")
    XCTAssertEqual(Set(capturedBox.value[0].1.keys), Set(["message_length", "has_screenshot", "source"]))

    XCTAssertEqual(capturedBox.value[1].1["message_length"] as? Int, 0)
    XCTAssertEqual(capturedBox.value[1].1["has_screenshot"] as? Bool, false)
    XCTAssertEqual(capturedBox.value[1].1["source"] as? String, "ptt_realtime")
  }
}
