import XCTest

@testable import Omi_Computer

/// Regression coverage for window-capture sizing.
///
/// The capture path previously computed `configHeight = min(width, maxSize) / (width / height)`
/// inline. A zero-width window frame makes that expression NaN (0/0); NaN fails the
/// `configHeight > maxSize` clamp, so `Int(NaN)` executed and trapped — crashing the app
/// from the background screen-capture loop. Sizing is now a pure function that refuses
/// degenerate frames; these tests pin that.
final class ScreenCaptureDimensionsTests: XCTestCase {
    private let maxSize: CGFloat = 3000

    func testPreservesAspectRatioForNormalWindow() {
        let size = ScreenCaptureService.captureDimensions(width: 1440, height: 900, maxSize: maxSize)
        XCTAssertEqual(size?.width, 1440)
        XCTAssertEqual(size?.height, 900)
    }

    func testClampsOversizedWindowToMaxSize() {
        // 6000x3000 → width clamps to 3000, height follows the 2:1 aspect ratio.
        let size = ScreenCaptureService.captureDimensions(width: 6000, height: 3000, maxSize: maxSize)
        XCTAssertEqual(size?.width, 3000)
        XCTAssertEqual(size?.height, 1500)
    }

    func testClampsTallWindowByHeight() {
        // 1000x9000 → height clamps to 3000, width follows the 1:9 aspect ratio.
        let size = ScreenCaptureService.captureDimensions(width: 1000, height: 9000, maxSize: maxSize)
        XCTAssertEqual(size?.height, 3000)
        XCTAssertEqual(size?.width, 333)
    }

    /// The crash: width 0 produced NaN, and `Int(NaN)` traps.
    func testReturnsNilForZeroWidthFrame() {
        XCTAssertNil(ScreenCaptureService.captureDimensions(width: 0, height: 900, maxSize: maxSize))
    }

    func testReturnsNilForZeroHeightFrame() {
        XCTAssertNil(ScreenCaptureService.captureDimensions(width: 1440, height: 0, maxSize: maxSize))
    }

    func testReturnsNilForFullyDegenerateFrame() {
        XCTAssertNil(ScreenCaptureService.captureDimensions(width: 0, height: 0, maxSize: maxSize))
    }

    func testReturnsNilForNegativeFrame() {
        XCTAssertNil(ScreenCaptureService.captureDimensions(width: -100, height: 900, maxSize: maxSize))
    }
}
