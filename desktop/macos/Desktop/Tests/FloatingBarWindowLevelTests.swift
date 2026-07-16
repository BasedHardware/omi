import AppKit
import XCTest

@testable import Omi_Computer

/// Regression guard for the bar's always-on-top contract: third-party notch
/// companions (e.g. Clicky) park windows at .popUpMenu (101) and full-screen
/// overlays at .screenSaver (1000). The bar buried at .statusBar (25) is the
/// bug this pins down — its level must clear every common overlay level.
final class FloatingBarWindowLevelTests: XCTestCase {
  func testBarLevelClearsCommonOverlayLevels() {
    let level = FloatingControlBarWindow.alwaysOnTopLevel
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.statusBar.rawValue)
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.popUpMenu.rawValue)
    XCTAssertGreaterThan(level.rawValue, NSWindow.Level.screenSaver.rawValue)
  }

  func testBarLevelStaysBelowCursorAndShield() {
    let level = FloatingControlBarWindow.alwaysOnTopLevel
    XCTAssertLessThan(level.rawValue, Int(CGWindowLevelForKey(.cursorWindow)))
    XCTAssertLessThan(level.rawValue, Int(CGShieldingWindowLevel()))
  }
}
