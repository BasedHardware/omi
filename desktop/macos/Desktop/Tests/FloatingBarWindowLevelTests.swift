import AppKit
import XCTest

@testable import Omi_Computer

/// Regression guard for the bar's always-on-top contract: third-party notch
/// companions (e.g. Clicky) park windows at .popUpMenu (101) and full-screen
/// overlays at .screenSaver (1000). The bar buried at .statusBar (25) is the
/// bug this pins down — its level must clear every common overlay level.
@MainActor final class FloatingBarWindowLevelTests: XCTestCase {
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

  /// **The app-switcher / deactivate guard for the notch.** NSPanel defaults
  /// `hidesOnDeactivate` to true, so focusing another app ordered the island out
  /// until Push-to-Talk called `show()`. The shell already writes this false in
  /// `ShellWindowChrome`; the notch is an always-on overlay and must do the same.
  func testTheNotchStaysOnScreenWhenAnotherAppTakesFocus() {
    let window = FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    defer { window.close() }

    XCTAssertFalse(
      window.hidesOnDeactivate,
      "AppKit orders a hidesOnDeactivate panel out as soon as another app activates")
    XCTAssertTrue(window.isFloatingPanel, "the notch is an always-on overlay, not a document window")
    XCTAssertEqual(window.level, FloatingControlBarWindow.alwaysOnTopLevel)
    XCTAssertTrue(window.collectionBehavior.contains(.canJoinAllSpaces))
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
    XCTAssertTrue(window.collectionBehavior.contains(.stationary))
    XCTAssertTrue(window.collectionBehavior.contains(.ignoresCycle))
    XCTAssertFalse(window.collectionBehavior.contains(.transient))
  }

  func testShowPathsKeepTheNotchFromHidingOnDeactivate() {
    let window = FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    defer { window.close() }

    window.hidesOnDeactivate = true
    window.isFloatingPanel = false
    window.applySurfaceLevel()

    XCTAssertFalse(window.hidesOnDeactivate, "a later surface pass must not restore NSPanel's default hide")
    XCTAssertTrue(window.isFloatingPanel)
    XCTAssertEqual(window.level, FloatingControlBarWindow.alwaysOnTopLevel)

    window.hidesOnDeactivate = true
    window.orderFrontRegardless()
    XCTAssertFalse(window.hidesOnDeactivate)
    window.orderOut(nil)
  }
}
