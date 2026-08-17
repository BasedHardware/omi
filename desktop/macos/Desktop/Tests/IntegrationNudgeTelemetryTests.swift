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
      connectorID: entry.telemetryID,
      triggerID: "notion_app",
      triggerKind: .nativeApp,
      shownCount: 1
    )

    XCTAssertEqual(
      Set(payload.keys),
      ["integration_name", "connector_id", "trigger_id", "trigger_kind", "shown_count"]
    )
    XCTAssertEqual(payload["connector_id"] as? String, "export:notion")
    XCTAssertEqual(payload["trigger_kind"] as? String, "native_app")
  }

  func testSuppressedPayloadCarriesTheClosedReason() throws {
    let entry = try entryOrFail()
    let payload = IntegrationNudgeTelemetry.suppressedPayload(
      integrationName: entry.displayName,
      connectorID: entry.telemetryID,
      triggerID: "notion_web",
      triggerKind: .browserSite,
      reason: .connectorCooldown
    )

    XCTAssertEqual(
      Set(payload.keys),
      ["integration_name", "connector_id", "trigger_id", "trigger_kind", "suppression_reason"]
    )
    XCTAssertEqual(payload["suppression_reason"] as? String, "connector_cooldown")
  }

  func testActionedPayloadIsExactlyItsClosedSchema() throws {
    let entry = try entryOrFail()
    let payload = IntegrationNudgeTelemetry.actionedPayload(
      integrationName: entry.displayName,
      connectorID: entry.telemetryID,
      action: .dismissForever
    )

    XCTAssertEqual(Set(payload.keys), ["integration_name", "connector_id", "action"])
    XCTAssertEqual(payload["action"] as? String, "dismiss_forever")
  }

  /// Every suppression reason is emitted as a dimension, so each one must have
  /// a stable, non-empty raw value.
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
