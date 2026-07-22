import XCTest

@testable import Omi_Computer

final class NotchGeometryTests: XCTestCase {
  func testHiddenCenterWidthFromMeasuredAuxiliaryAreas() {
    // 1512pt screen: left aux ends at 640, right aux starts at 872 -> 232pt gap.
    let width = NotchMetrics.hiddenCenterWidth(
      auxiliaryTopLeftArea: NSRect(x: 0, y: 0, width: 640, height: 38),
      auxiliaryTopRightArea: NSRect(x: 872, y: 0, width: 640, height: 38)
    )
    XCTAssertEqual(width, 232 + NotchMetrics.hiddenCenterSafetyPadding)
  }

  func testHiddenCenterWidthFallsBackWithoutAuxiliaryAreas() {
    let expected = NotchMetrics.fallbackHiddenCenterWidth + NotchMetrics.hiddenCenterSafetyPadding
    XCTAssertEqual(
      NotchMetrics.hiddenCenterWidth(auxiliaryTopLeftArea: nil, auxiliaryTopRightArea: nil), expected)
    XCTAssertEqual(
      NotchMetrics.hiddenCenterWidth(
        auxiliaryTopLeftArea: .zero, auxiliaryTopRightArea: NSRect(x: 1, y: 0, width: 1, height: 1)),
      expected)
  }

  func testHiddenCenterWidthNeverShrinksBelowFallback() {
    // A tiny measured gap must not produce chrome narrower than the fallback.
    let width = NotchMetrics.hiddenCenterWidth(
      auxiliaryTopLeftArea: NSRect(x: 0, y: 0, width: 750, height: 38),
      auxiliaryTopRightArea: NSRect(x: 760, y: 0, width: 750, height: 38)
    )
    XCTAssertEqual(width, NotchMetrics.fallbackHiddenCenterWidth + NotchMetrics.hiddenCenterSafetyPadding)
  }

  func testClosedHeightUsesPhysicalNotchWhenPresent() {
    let height = NotchMetrics.closedHeight(topSafeAreaInset: 38, frameMaxY: 982, visibleFrameMaxY: 944)
    XCTAssertEqual(height, 38)
  }

  func testClosedHeightFallsBackToMenuBarStrip() {
    let height = NotchMetrics.closedHeight(topSafeAreaInset: 0, frameMaxY: 1080, visibleFrameMaxY: 1043)
    XCTAssertEqual(height, 36)
  }

  func testClosedHeightNeverBelowFallback() {
    let height = NotchMetrics.closedHeight(topSafeAreaInset: 0, frameMaxY: 1080, visibleFrameMaxY: 1079)
    XCTAssertEqual(height, NotchMetrics.fallbackClosedSize.height)
  }

  func testClosedSizeOnNotchedDisplayStraddlesCameraWithSideLobes() {
    let size = NotchMetrics.closedSize(
      hasCameraHousing: true,
      auxiliaryTopLeftArea: NSRect(x: 0, y: 0, width: 640, height: 38),
      auxiliaryTopRightArea: NSRect(x: 872, y: 0, width: 640, height: 38),
      topSafeAreaInset: 38,
      frameMaxY: 982,
      visibleFrameMaxY: 944
    )
    XCTAssertEqual(
      size.width, 232 + NotchMetrics.hiddenCenterSafetyPadding + NotchMetrics.closedSideWidth * 2)
    XCTAssertEqual(size.height, 38)
  }

  func testClosedSizeOnPlainDisplayUsesFallbackWidth() {
    let size = NotchMetrics.closedSize(
      hasCameraHousing: false,
      auxiliaryTopLeftArea: nil,
      auxiliaryTopRightArea: nil,
      topSafeAreaInset: 0,
      frameMaxY: 1080,
      visibleFrameMaxY: 1043
    )
    XCTAssertEqual(size.width, NotchMetrics.fallbackClosedSize.width)
    XCTAssertEqual(size.height, 36)
  }
}
