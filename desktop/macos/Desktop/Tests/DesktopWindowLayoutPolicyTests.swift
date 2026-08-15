import AppKit
import XCTest

@testable import Omi_Computer

final class DesktopWindowLayoutPolicyTests: XCTestCase {
  func testMainWindowMinimumFitsA1024PointWideDisplay() {
    XCTAssertLessThanOrEqual(
      DesktopWindowLayoutPolicy.minimumContentSize.width,
      1024,
      "The responsive main window must fit common compact desktop displays."
    )
    XCTAssertEqual(DesktopWindowLayoutPolicy.minimumContentSize.height, 680)
  }
}
