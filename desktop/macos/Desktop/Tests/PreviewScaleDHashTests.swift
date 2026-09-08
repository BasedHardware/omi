import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Regression coverage for the preview-hash representation bug: `markCaptured` used to
/// store a full-resolution dHash into the same history the ≤80px preview grabs are
/// compared against. A hash of a full frame and a hash of a small preview of the same
/// screen must land close enough to clear the strictest preview-similarity threshold,
/// or every preview reads as "changed" and the preview-skip never fires.
final class PreviewScaleDHashTests: XCTestCase {

  /// Renders the same synthetic "desktop window" scene at an arbitrary pixel size.
  /// Vector drawing in normalized coordinates, so every size shows identical content.
  private func renderScene(width: Int, height: Int) throws -> CGImage {
    let ctx = try XCTUnwrap(
      CGContext(
        data: nil, width: width, height: height,
        bitsPerComponent: 8, bytesPerRow: width * 4,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      ))
    ctx.scaleBy(x: CGFloat(width), y: CGFloat(height))
    // Background, title bar, sidebar, and a column of "text lines" with varying
    // gray levels — enough horizontal luminance structure to exercise all 64 bits.
    ctx.setFillColor(CGColor(gray: 0.95, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: 1, height: 1))
    ctx.setFillColor(CGColor(gray: 0.20, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0.92, width: 1, height: 0.08))
    ctx.setFillColor(CGColor(gray: 0.75, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: 0.22, height: 0.92))
    for row in 0..<9 {
      let shade = 0.30 + 0.05 * Double(row % 4)
      ctx.setFillColor(CGColor(gray: shade, alpha: 1))
      let y = 0.06 + Double(row) * 0.09
      let lineWidth = 0.45 + 0.25 * Double((row * 7) % 3) / 2.0
      ctx.fill(CGRect(x: 0.26, y: y, width: lineWidth, height: 0.035))
    }
    ctx.setFillColor(CGColor(gray: 0.55, alpha: 1))
    ctx.fill(CGRect(x: 0.03, y: 0.10, width: 0.16, height: 0.55))
    return try XCTUnwrap(ctx.makeImage())
  }

  private func hammingDistance(_ a: UInt64, _ b: UInt64) -> Int {
    (a ^ b).nonzeroBitCount
  }

  func testFullCaptureHashMatchesPreviewHashOfTheSameScreen() throws {
    // Production shapes: a typical full window capture and the 80px preview grab.
    let full = try renderScene(width: 1638, height: 1072)
    let preview = try renderScene(width: 80, height: 52)

    let fullHash = RewindOCRService.previewScaleDHash(of: full)
    let previewHash = RewindOCRService.dHash(of: preview)

    // The strictest threshold in PreviewSimilarityThresholdPolicy is 0.99 (notes),
    // i.e. at most 1 differing bit would still skip. Same-representation hashing of
    // identical content must comfortably clear the default 0.95 tier (≤3 bits).
    XCTAssertLessThanOrEqual(
      hammingDistance(fullHash, previewHash), 3,
      "full-capture hash diverged from the preview hash of identical content — "
        + "cross-scale hashing defeats the preview-similarity skip")
  }

  func testPreviewScaleDHashIsAPassThroughAtOrBelowPreviewSize() throws {
    let preview = try renderScene(width: 80, height: 52)
    XCTAssertEqual(
      RewindOCRService.previewScaleDHash(of: preview),
      RewindOCRService.dHash(of: preview),
      "images already inside the preview envelope must hash identically on both paths")
  }

  func testPreviewScaleDHashIsDeterministic() throws {
    let full = try renderScene(width: 1638, height: 1072)
    XCTAssertEqual(
      RewindOCRService.previewScaleDHash(of: full),
      RewindOCRService.previewScaleDHash(of: full))
  }
}
