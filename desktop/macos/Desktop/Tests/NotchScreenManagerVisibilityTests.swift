import AppKit
import XCTest

@testable import Omi_Computer

/// Regression guard for the disabled/snoozed/deferred launch path: panels must
/// be created hidden and only revealed through showAll (reached via
/// show / snooze-clear / temporary-notification). The bug this pins down is
/// makePanel ordering every panel front on creation, which let the notch appear
/// on launch even when the user had disabled or snoozed the floating bar.
@MainActor final class NotchScreenManagerVisibilityTests: XCTestCase {
  func testPanelsAreCreatedHiddenUntilShowAll() throws {
    try XCTSkipIf(NSScreen.screens.isEmpty, "requires at least one display")

    let manager = NotchScreenManager()
    manager.start(barState: FloatingControlBarState(), chatProvider: ChatProvider())
    defer { manager.stop() }

    XCTAssertEqual(
      manager.visibleWindowCount, 0,
      "panels must not order front on creation — a disabled/snoozed launch would leak the notch")

    manager.showAll()
    XCTAssertEqual(
      manager.visibleWindowCount, NSScreen.screens.count,
      "showAll must reveal one panel per display")

    manager.hideAll()
    XCTAssertEqual(manager.visibleWindowCount, 0, "hideAll must order every panel off screen")
  }

  /// The mechanism the ported `closeAskOmiForAutomation` (bridge action
  /// `close_ask_omi`) relies on: an open panel is dismissed by closeAll. Before
  /// the port this ran against the always-nil legacy window and no-oped.
  func testCloseAllDismissesOpenPanel() throws {
    try XCTSkipIf(NSScreen.screens.isEmpty, "requires at least one display")

    let manager = NotchScreenManager()
    manager.start(barState: FloatingControlBarState(), chatProvider: ChatProvider())
    defer { manager.stop() }

    manager.openPrimary()
    XCTAssertTrue(manager.hasOpenPanel, "openPrimary must open a panel to close")

    manager.closeAll()
    XCTAssertFalse(manager.hasOpenPanel, "close_ask_omi path must dismiss the open panel")
  }

  /// Explicit summon (Ask Omi hotkey / notification) must surface the panel even
  /// while the passive bar is hidden (disabled/snoozed), and closing it must
  /// re-hide — the pre-notch "show temporarily, hide on close" contract.
  func testExplicitOpenSurfacesWhilePassivelyHiddenThenHidesOnClose() throws {
    try XCTSkipIf(NSScreen.screens.isEmpty, "requires at least one display")

    let manager = NotchScreenManager()
    manager.start(barState: FloatingControlBarState(), chatProvider: ChatProvider())
    defer { manager.stop() }

    // Passive bar hidden (disabled/snoozed launch).
    XCTAssertEqual(manager.visibleWindowCount, 0)

    manager.openPrimary()
    XCTAssertGreaterThan(
      manager.visibleWindowCount, 0, "an explicit open must surface even while the passive bar is hidden")

    manager.closeAll()
    XCTAssertEqual(
      manager.visibleWindowCount, 0, "closing an explicitly-summoned panel must re-hide it while disabled")
  }
}
