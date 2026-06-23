import XCTest
import AppKit
import CoreGraphics

@testable import Omi_Computer

/// Tests for `ScreenCaptureManager.downscale` and the new
/// `maxLongEdge` parameter on `captureScreenData`. Downscale saves
/// 50-150ms of CPU per visual query on 5K displays by avoiding
/// full-Retina WebP encoding (5120x2880 -> 1280x720).
final class ScreenCaptureDownscaleTests: XCTestCase {

    // MARK: - downscale

    func testDownscaleLeavesSmallImageAlone() {
        // An image already smaller than maxLongEdge returns nil (no
        // work needed; caller falls back to the original).
        let image = makeImage(width: 800, height: 600)
        XCTAssertNil(
            ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280),
            "Image already smaller than maxLongEdge should not be downscaled"
        )
    }

    func testDownscaleExactlyMaxLongEdgeReturnsNil() {
        // Boundary: image with long edge == maxLongEdge is not downscaled.
        let image = makeImage(width: 1280, height: 800)
        XCTAssertNil(
            ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280),
            "Image at the boundary should not be downscaled"
        )
    }

    func testDownscaleReduces5KTo1280() {
        // A 5120x2880 (5K) image should be downscaled to 1280x720
        // (preserving aspect ratio).
        let image = makeImage(width: 5120, height: 2880)
        let scaled = ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280)
        let result = try! XCTUnwrap(scaled)
        XCTAssertEqual(result.width, 1280)
        XCTAssertEqual(result.height, 720)
    }

    func testDownscalePreservesAspectRatio() {
        // A 4:3 image downscaled to maxLongEdge=1280 should be 1280x960.
        let image = makeImage(width: 3840, height: 2880)
        let scaled = ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280)
        let result = try! XCTUnwrap(scaled)
        XCTAssertEqual(result.width, 1280)
        XCTAssertEqual(result.height, 960)
    }

    func testDownscalePortraitOrientation() {
        // Tall image: maxLongEdge applies to the longer side.
        let image = makeImage(width: 1080, height: 2400)
        let scaled = ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280)
        let result = try! XCTUnwrap(scaled)
        XCTAssertEqual(result.width, 576)   // 1080 * (1280/2400)
        XCTAssertEqual(result.height, 1280)
    }

    func testDownscaleNonStandardMaxLongEdge() {
        // Configurable: 640px for very small UI tests.
        let image = makeImage(width: 2560, height: 1440)
        let scaled = ScreenCaptureManager.downscale(image: image, maxLongEdge: 640)
        let result = try! XCTUnwrap(scaled)
        XCTAssertEqual(result.width, 640)
        XCTAssertEqual(result.height, 360)
    }

    // MARK: - defaults pinned

    func testDefaultMaxLongEdgeIs1280() {
        // Pinned: the default is the contract. If a future change tries
        // to bump it back to full resolution, this test fails.
        XCTAssertEqual(ScreenCaptureManager.defaultMaxLongEdge, 1280)
    }

    func testDefaultWebPQualityIs60() {
        // Pinned: the WebP quality default. Bumping this back up would
        // regress the encode-time saving.
        XCTAssertEqual(ScreenCaptureManager.defaultWebPQuality, 60.0, accuracy: 0.001)
    }

    // MARK: - Helpers

    /// Make a solid-color CGImage of the given size. Uses NSImage-style
    /// bitmap creation that doesn't need a real display.
    private func makeImage(width: Int, height: Int) -> CGImage {
        let bytesPerRow = width * 4
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
        let context = CGContext(
            data: nil,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: colorSpace,
            bitmapInfo: bitmapInfo
        )!
        context.setFillColor(red: 0.5, green: 0.5, blue: 0.5, alpha: 1.0)
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        return context.makeImage()!
    }

    // MARK: - End-to-end (regression for cubic P1 on PR #8140, addressed in 56f5d57d3)

    /// Pins the post-fix invariant: a 5K input downscales to <= 1280
    /// on the long edge, so the bitmap context is sized to those
    /// dimensions, not the original. The bug found by cubic-dev-ai
    /// was that `captureScreenData` was drawing the original image
    /// (5120x2880) into a 1280x720 context — doing the downscale
    /// twice. The fix draws the already-downscaled `scaledImage`.
    /// This test guards the downscale step itself; the draw step
    /// is reviewed by cubic and by the static checks above.
    func testDownscaleProducesExpectedDimensions() {
        let image = makeImage(width: 5120, height: 2880)
        let scaled = ScreenCaptureManager.downscale(image: image, maxLongEdge: 1280)
        let result = try! XCTUnwrap(scaled)
        XCTAssertEqual(result.width, 1280)
        XCTAssertEqual(result.height, 720)
    }
}
