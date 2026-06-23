import XCTest
import AppKit
import CoreGraphics

@testable import Omi_Computer

/// Tests for `ScreenCaptureManager.downscale` and the new `maxLongEdge`
/// parameter on `captureScreenData` — Track 2 PR 4's downscale-to-1280px
/// optimization. The downscale saves 50-150ms of CPU on 5K displays by
/// avoiding full-Retina WebP encoding.
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

    // MARK: - defaultMaxLongEdge

    func testDefaultMaxLongEdgeIs1280() {
        // Pinned: the default is the contract. If a future change tries
        // to bump it back to full resolution, this test fails.
        XCTAssertEqual(ScreenCaptureManager.defaultMaxLongEdge, 1280)
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
}
