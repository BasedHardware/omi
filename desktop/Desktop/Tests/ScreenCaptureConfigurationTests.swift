import CoreGraphics
import XCTest

@testable import Omi_Computer

final class ScreenCaptureConfigurationTests: XCTestCase {
  func testConfigurationSizeRejectsZeroHeightWindowFrame() {
    let size = ScreenCaptureService.configurationSize(
      forWindowFrame: CGRect(x: 0, y: 0, width: 1440, height: 0),
      maxSize: 3000
    )

    XCTAssertNil(size)
  }

  func testConfigurationSizeRejectsNonFiniteWindowFrame() {
    let size = ScreenCaptureService.configurationSize(
      forWindowFrame: CGRect(x: 0, y: 0, width: CGFloat.nan, height: 900),
      maxSize: 3000
    )

    XCTAssertNil(size)
  }

  func testConfigurationSizePreservesAspectRatioWithinMaxSize() throws {
    let size = try XCTUnwrap(
      ScreenCaptureService.configurationSize(
        forWindowFrame: CGRect(x: 0, y: 0, width: 6000, height: 3000),
        maxSize: 3000
      )
    )

    XCTAssertEqual(size.width, 3000)
    XCTAssertEqual(size.height, 1500)
  }
}
