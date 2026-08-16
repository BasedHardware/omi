import OmiTheme
import XCTest

@testable import Omi_Computer

/// Regression: the transparent shell window (`ShellWindowChrome`) accepted clicks across its whole
/// frame — the reserved title-bar band, lane margins, and gaps between panels swallowed clicks
/// aimed at other apps, which never activated (the shell-window dead zone). The policy passes the
/// pointer through everywhere except visible content, the modal barrier's host, and the resize rim.
final class ShellClickThroughPolicyTests: XCTestCase {
  private let windowSize = NSSize(width: 960, height: 712)

  func testDeadAirPassesClicksThrough() {
    XCTAssertFalse(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 480, y: 690),
        windowSize: windowSize,
        isResizable: true,
        contentContains: { _ in false }),
      "air that is not glass must not swallow clicks")
    XCTAssertFalse(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 480, y: 350),
        windowSize: windowSize,
        isResizable: true,
        contentContains: { _ in false }),
      "a gap between panels must not swallow clicks")
  }

  func testVisibleContentOwnsThePointer() {
    let panel = NSRect(x: 100, y: 100, width: 760, height: 400)
    XCTAssertTrue(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 480, y: 300),
        windowSize: windowSize,
        isResizable: true,
        contentContains: panel.contains))
    XCTAssertFalse(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 480, y: 550),
        windowSize: windowSize,
        isResizable: false,
        contentContains: panel.contains))
  }

  func testResizableWindowKeepsAnInteractiveEdgeRim() {
    XCTAssertEqual(DesktopWindowLayoutPolicy.windowInset, 0)
    XCTAssertTrue(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 4, y: 350),
        windowSize: windowSize,
        isResizable: true,
        contentContains: { _ in false }),
      "the frame edge stays grabbable for resizing")
    XCTAssertFalse(
      ShellClickThroughPolicy.acceptsMouseHit(
        localPoint: NSPoint(x: 4, y: 350),
        windowSize: windowSize,
        isResizable: false,
        contentContains: { _ in false }),
      "a fixed-size window has no resize affordance to preserve")
  }
}
