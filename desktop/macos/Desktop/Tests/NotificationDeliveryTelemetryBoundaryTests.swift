import XCTest

@testable import Omi_Computer

/// `NotificationDeliveryTelemetry` is the only place the `Notification Delivery
/// Skipped` event name and payload are constructed in production. Asserting on
/// the payload builder alone would not catch `AnalyticsManager.notificationDeliverySkipped`
/// being wired to the wrong event name or dropping a dimension on the way
/// through — so this drives the real `AnalyticsManager` method through its
/// scoped capture seam, mirroring `IntegrationNudgeAnalyticsBoundaryTests`.
@MainActor
final class NotificationDeliveryTelemetryBoundaryTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setNotificationDeliveryTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setNotificationDeliveryTelemetryCaptureForTests(nil)
      }
    }
  }

  func testSkippedEmitsItsNameAndBoundedPayload() throws {
    startCapturing()

    AnalyticsManager.shared.notificationDeliverySkipped(authStatus: .notDetermined, surface: .task)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, NotificationDeliveryTelemetry.skippedEventName)
    XCTAssertEqual(event.1["auth_status"] as? String, "not_determined")
    XCTAssertEqual(event.1["surface"] as? String, "task")
  }

  func testSkippedCarriesADeniedStatusDistinctFromNotDetermined() throws {
    startCapturing()

    AnalyticsManager.shared.notificationDeliverySkipped(authStatus: .denied, surface: .insight)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.1["auth_status"] as? String, "denied")
    XCTAssertEqual(event.1["surface"] as? String, "insight")
  }

  /// Nothing an emitter passes may escape the allow-list, whatever a future
  /// caller adds to a payload builder — this must never carry a notification
  /// title, body, assistant id, or window/app identity.
  func testEveryEmittedKeyIsOnTheAllowList() throws {
    startCapturing()

    AnalyticsManager.shared.notificationDeliverySkipped(authStatus: .notDetermined, surface: .general)
    AnalyticsManager.shared.notificationDeliverySkipped(authStatus: .denied, surface: .task)

    XCTAssertEqual(capturedBox.value.count, 2)
    for event in capturedBox.value {
      for key in event.1.keys {
        XCTAssertTrue(
          NotificationDeliveryTelemetry.allowedKeys.contains(key),
          "'\(key)' escaped the allow-list in \(event.0)"
        )
      }
    }
  }

  final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
  }
}
