import XCTest

@testable import Omi_Computer

@MainActor
final class IntegrationNudgeCardPresentationTests: XCTestCase {
  /// The card is rendered from the notification's action payload alone, which
  /// carries only the telemetry id. An id the catalog cannot resolve would
  /// silently fall back to the generic notification view — an offer with no
  /// Connect button. Guard the round-trip for every entry that can nudge.
  func testEveryNudgeableEntryProducesAResolvableAction() {
    XCTAssertFalse(IntegrationNudgeCatalog.nudgeable.isEmpty)
    for entry in IntegrationNudgeCatalog.nudgeable {
      let action = FloatingBarNotificationAction.connectIntegration(
        telemetryID: entry.telemetryID,
        triggerID: entry.triggers[0].id
      )
      guard case .connectIntegration(let telemetryID, let triggerID) = action else {
        return XCTFail("action did not round-trip for \(entry.telemetryID)")
      }
      XCTAssertEqual(
        IntegrationNudgeCatalog.all.first { $0.telemetryID == telemetryID }?.route,
        entry.route
      )
      XCTAssertEqual(triggerID, entry.triggers[0].id)
    }
  }

  /// The two floating-bar actions must stay distinguishable: the card view and
  /// the tap router both switch on this enum, and a case that pattern-matched
  /// the other would send the user to the wrong destination.
  func testConnectActionIsDistinctFromTheRecommendationAction() {
    let connect = FloatingBarNotificationAction.connectIntegration(
      telemetryID: "import:email", triggerID: "gmail_web")
    let recommendation = FloatingBarNotificationAction.openWhatMattersNow(recommendationID: "import:email")
    XCTAssertNotEqual(connect, recommendation)
  }
}
