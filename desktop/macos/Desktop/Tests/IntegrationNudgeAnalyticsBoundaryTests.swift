import XCTest

@testable import Omi_Computer

/// The three nudge emitters are the only place these event names and payloads
/// are constructed in production. Asserting on the payload builders alone would
/// not catch an emitter wired to the wrong builder, the wrong event name, or a
/// dimension dropped on the way through — so these drive the real
/// `AnalyticsManager` methods through its scoped capture seam.
@MainActor
final class IntegrationNudgeAnalyticsBoundaryTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setIntegrationNudgeTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setIntegrationNudgeTelemetryCaptureForTests(nil)
      }
    }
  }

  private func entry() throws -> IntegrationNudgeCatalogEntry {
    try XCTUnwrap(IntegrationNudgeCatalog.exportEntry(destinationID: "notion"))
  }

  private func trigger() throws -> IntegrationNudgeTrigger {
    try XCTUnwrap(entry().triggers.first)
  }

  func testShownEmitsItsNameAndPayload() throws {
    startCapturing()

    AnalyticsManager.shared.integrationNudgeShown(
      entry: try entry(), trigger: try trigger(), shownCount: 2)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, IntegrationNudgeTelemetry.shownEventName)
    XCTAssertEqual(event.1["connector_id"] as? String, "notion")
    XCTAssertEqual(event.1["route"] as? String, "export")
    XCTAssertEqual(event.1["integration_name"] as? String, "Notion")
    XCTAssertEqual(event.1["shown_count"] as? Int, 2)
  }

  /// Conversion has to be attributable to the trigger that produced the card,
  /// or a native-app nudge and a browser-site nudge for the same integration
  /// are indistinguishable in the funnel.
  func testActionedCarriesTheTriggerThatProducedTheCard() throws {
    startCapturing()

    AnalyticsManager.shared.integrationNudgeActioned(
      entry: try entry(), action: .connect, triggerID: "notion_web")

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, IntegrationNudgeTelemetry.actionedEventName)
    XCTAssertEqual(event.1["action"] as? String, "connect")
    XCTAssertEqual(event.1["trigger_id"] as? String, "notion_web")
  }

  /// Nothing an emitter passes may escape the allow-list, whatever a future
  /// caller adds to a payload builder.
  func testEveryEmittedKeyIsOnTheAllowList() throws {
    startCapturing()

    AnalyticsManager.shared.integrationNudgeShown(
      entry: try entry(), trigger: try trigger(), shownCount: 1)
    AnalyticsManager.shared.integrationNudgeActioned(
      entry: try entry(), action: .notNow, triggerID: "notion_app")

    XCTAssertEqual(capturedBox.value.count, 2)
    for event in capturedBox.value {
      for key in event.1.keys {
        XCTAssertTrue(
          IntegrationNudgeTelemetry.allowedKeys.contains(key),
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
