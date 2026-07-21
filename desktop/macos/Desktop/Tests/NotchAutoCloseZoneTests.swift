import XCTest

@testable import Omi_Computer

@MainActor
final class NotchAutoCloseZoneTests: XCTestCase {
  private let body = CGRect(x: 500, y: 900, width: 480, height: 200)
  private let tray = CGRect(x: 500, y: 806, width: 480, height: 84)

  func testCloseZoneCoversBodyTrayAndTheGapBetween() {
    let zone = NotchScreenManager.closeZone(body: body, tray: tray)
    XCTAssertTrue(zone.contains(CGPoint(x: 740, y: 1000)), "inside body")
    XCTAssertTrue(zone.contains(CGPoint(x: 740, y: 850)), "inside tray")
    XCTAssertTrue(zone.contains(CGPoint(x: 740, y: 895)), "the body-tray gap")
    XCTAssertTrue(zone.contains(CGPoint(x: 470, y: 1000)), "generous horizontal inset")
    XCTAssertFalse(zone.contains(CGPoint(x: 200, y: 500)), "clearly outside")
  }

  func testAimingTowardZoneHoldsClose() {
    let zone = NotchScreenManager.closeZone(body: body, tray: tray)
    // Moving straight toward the zone center from below-left.
    XCTAssertTrue(
      NotchScreenManager.isAiming(toward: zone, from: CGPoint(x: 100, y: 100), to: CGPoint(x: 150, y: 170)))
  }

  func testRecedingPointerIsNotAiming() {
    let zone = NotchScreenManager.closeZone(body: body, tray: tray)
    XCTAssertFalse(
      NotchScreenManager.isAiming(toward: zone, from: CGPoint(x: 150, y: 170), to: CGPoint(x: 100, y: 100)))
  }

  func testStationaryPointerIsNotAiming() {
    let zone = NotchScreenManager.closeZone(body: body, tray: tray)
    XCTAssertFalse(
      NotchScreenManager.isAiming(toward: zone, from: CGPoint(x: 100, y: 100), to: CGPoint(x: 100, y: 100)))
  }

  func testPerpendicularMovementIsNotAiming() {
    let zone = NotchScreenManager.closeZone(body: body, tray: tray)
    // Skimming sideways far below the zone: distance barely changes and the
    // movement vector points away from the zone center's direction cone.
    XCTAssertFalse(
      NotchScreenManager.isAiming(toward: zone, from: CGPoint(x: 740, y: 100), to: CGPoint(x: 741, y: 40)))
  }
}
