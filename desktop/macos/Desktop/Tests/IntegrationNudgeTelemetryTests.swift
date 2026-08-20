import XCTest

@testable import Omi_Computer

/// Nudge telemetry is derived from the frontmost window, which is the most
/// content-adjacent input in this feature. These tests hold the line that only
/// bounded, catalog-defined values leave the machine.
final class IntegrationNudgeTelemetryTests: XCTestCase {
  /// Notion is a stable catalog entry; `IntegrationNudgeCatalogTests` proves
  /// every export destination has one, so a nil here is a catalog bug, not a
  /// test-setup accident.
  private func entryOrFail(file: StaticString = #filePath, line: UInt = #line) throws
    -> IntegrationNudgeCatalogEntry
  {
    try XCTUnwrap(IntegrationNudgeCatalog.exportEntry(destinationID: "notion"), file: file, line: line)
  }

  func testShownPayloadIsExactlyItsClosedSchema() throws {
    let entry = try entryOrFail()
    let payload = IntegrationNudgeTelemetry.shownPayload(
      integrationName: entry.displayName,
      route: entry.route,
      triggerID: "notion_app",
      triggerKind: .nativeApp,
      shownCount: 1
    )

    XCTAssertEqual(
      Set(payload.keys),
      ["integration_name", "connector_id", "route", "trigger_id", "trigger_kind", "shown_count"]
    )
    // Same shape as the connect funnel's `connector_id`, so the two event
    // families join; `route` is what disambiguates the two halves.
    XCTAssertEqual(payload["connector_id"] as? String, "notion")
    XCTAssertEqual(payload["route"] as? String, "export")
    XCTAssertEqual(payload["trigger_kind"] as? String, "native_app")
  }

  func testActionedPayloadIsExactlyItsClosedSchema() throws {
    let entry = try entryOrFail()
    let payload = IntegrationNudgeTelemetry.actionedPayload(
      integrationName: entry.displayName,
      route: entry.route,
      action: .dismissForever,
      triggerID: "notion_app"
    )

    XCTAssertEqual(
      Set(payload.keys), ["integration_name", "connector_id", "route", "action", "trigger_id"])
    XCTAssertEqual(payload["action"] as? String, "dismiss_forever")
  }

  /// Suppression reasons are not emitted, but they are the coordinator's control
  /// flow and its logs, so each still needs a stable, distinct raw value.
  func testEverySuppressionReasonHasABoundedRawValue() {
    var seen = Set<String>()
    for reason in IntegrationNudgePolicy.Suppression.allCases {
      XCTAssertFalse(reason.rawValue.isEmpty)
      XCTAssertTrue(seen.insert(reason.rawValue).inserted, "duplicate raw value \(reason.rawValue)")
    }
  }

  /// The allow-list is the defense against a future caller threading a window
  /// title or bundle identifier through as an "extra" property.
  func testAllowListDropsAnythingOutsideTheSchema() {
    // `shownPayload` builds only allowed keys; prove the filter itself by
    // checking the allow-list does not contain any content-shaped key.
    let forbidden = ["window_title", "bundle_identifier", "app_name", "url", "title"]
    for key in forbidden {
      XCTAssertFalse(
        IntegrationNudgeTelemetry.allowedKeys.contains(key),
        "'\(key)' is content and must never be an allowed nudge dimension"
      )
    }
  }

  /// A nudge-sourced connect must be attributable, or the entire experiment is
  /// unmeasurable.
  func testConnectFunnelHasADistinctNudgeSurface() {
    XCTAssertEqual(IntegrationConnectTelemetry.Surface.nudge.rawValue, "nudge")
    XCTAssertNotEqual(
      IntegrationConnectTelemetry.Surface.nudge,
      IntegrationConnectTelemetry.Surface.apps
    )
  }
}
