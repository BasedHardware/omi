import AppKit
import XCTest

@testable import Omi_Computer

/// Regression guard for the notch's always-on-top contract: third-party notch
/// companions (e.g. Clicky) park windows at .popUpMenu (101) and full-screen
/// overlays at .screenSaver (1000). A notch buried at .statusBar (25) is the
/// bug this pins down — its level must clear every common overlay level.
@MainActor final class NotchWindowLevelTests: XCTestCase {
  func testNotchLevelClearsCommonOverlayLevels() {
    let level = NotchWindow.normalLevel
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.statusBar.rawValue)
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.popUpMenu.rawValue)
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.screenSaver.rawValue)
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.mainMenu.rawValue, "must cover the menu-bar strip")
  }

  func testNotchLevelStaysBelowCursorAndShield() {
    let level = NotchWindow.normalLevel
    XCTAssertLessThan(level.rawValue, Int(CGWindowLevelForKey(.cursorWindow)))
    XCTAssertLessThan(level.rawValue, Int(CGShieldingWindowLevel()))
  }
}
