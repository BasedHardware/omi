import AppKit
import XCTest

@testable import Omi_Computer

/// Regression coverage for `RewindStorage.downsampledImage`.
///
/// Rewind search rows load a screenshot for a 120×80 view. They used to decode
/// the full-resolution image and retain it, so a long results list held many
/// full-size NSImages in memory. The rows now decode a bounded thumbnail via
/// this pure ImageIO helper.
final class RewindStorageDownsampleTests: XCTestCase {
  func testDownsampleBoundsTheLongestEdge() throws {
    let data = try makeJPEGData(width: 1000, height: 600)
    let thumb = try XCTUnwrap(RewindStorage.downsampledImage(from: data, maxPixelSize: 120))
    let cg = try XCTUnwrap(thumb.cgImage(forProposedRect: nil, context: nil, hints: nil))
    XCTAssertLessThanOrEqual(max(cg.width, cg.height), 120, "Longest edge must be capped at maxPixelSize")
    XCTAssertGreaterThan(min(cg.width, cg.height), 0)
  }

  func testDownsampleRejectsNonImageData() {
    XCTAssertNil(RewindStorage.downsampledImage(from: Data([0, 1, 2, 3]), maxPixelSize: 120))
  }

  func testDownsampleRejectsNonPositiveMaxSize() throws {
    let data = try makeJPEGData(width: 64, height: 64)
    XCTAssertNil(RewindStorage.downsampledImage(from: data, maxPixelSize: 0))
  }

  private func makeJPEGData(width: Int, height: Int) throws -> Data {
    let rep = try XCTUnwrap(
      NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0))
    return try XCTUnwrap(rep.representation(using: .jpeg, properties: [:]))
  }
}
