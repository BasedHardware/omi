import AppKit
import XCTest

@testable import Omi_Computer

@MainActor
final class DesktopWindowLayoutPolicyTests: XCTestCase {
  func testMainWindowMinimumFitsA1024PointWideDisplay() {
    XCTAssertLessThanOrEqual(
      DesktopWindowLayoutPolicy.minimumContentSize.width,
      1024,
      "The responsive main window must fit common compact desktop displays."
    )
    XCTAssertEqual(DesktopWindowLayoutPolicy.minimumContentSize.height, 680)
  }

  func testMaximumContentSizeUsesTheVisibleDisplayInsteadOfTheContentLane() throws {
    guard let screen = NSScreen.main else { throw XCTSkip("No display is available") }
    guard screen.visibleFrame.width > ChatComposerLayout.contentLaneMaxWidth else {
      throw XCTSkip("The test display is not wider than the content lane")
    }

    let window = NSWindow(
      contentRect: screen.visibleFrame,
      styleMask: .borderless,
      backing: .buffered,
      defer: true)
    let maximum = DesktopWindowLayoutPolicy.maximumContentSize(for: window)

    let expected = window.contentRect(forFrameRect: screen.visibleFrame).size
    XCTAssertEqual(maximum.width, expected.width, accuracy: 0.01)
    XCTAssertEqual(maximum.height, expected.height, accuracy: 0.01)
    XCTAssertGreaterThan(maximum.width, ChatComposerLayout.contentLaneMaxWidth)
  }
}
