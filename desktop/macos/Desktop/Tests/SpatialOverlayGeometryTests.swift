import AppKit
import XCTest

@testable import Omi_Computer

final class SpatialOverlayGeometryTests: XCTestCase {
  func testTopLeftFrameNormalizesToAppKitCoordinates() {
    let frame = SpatialOverlayGeometry.appKitFrame(
      topLeftOrigin: CGPoint(x: 120, y: 80),
      size: CGSize(width: 640, height: 480),
      screenFrame: NSRect(x: 0, y: 0, width: 1440, height: 900)
    )

    XCTAssertEqual(frame, NSRect(x: 120, y: 340, width: 640, height: 480))
  }

  func testAnchoredBelowFrameMatchesAgentPillPlacement() {
    let frame = SpatialOverlayGeometry.frameAnchoredBelow(
      anchorFrame: NSRect(x: 500, y: 760, width: 280, height: 42),
      contentSize: NSSize(width: 96, height: 56),
      minimumWidth: 240,
      gap: 8
    )

    XCTAssertEqual(frame, NSRect(x: 520, y: 696, width: 240, height: 56))
  }

  func testGlowEdgeFramesPreserveExistingOutsets() {
    let target = NSRect(x: 100, y: 200, width: 300, height: 180)
    let thickness: CGFloat = 20
    let overlap: CGFloat = 4

    XCTAssertEqual(
      SpatialOverlayGeometry.glowEdgeFrame(
        for: .top, around: target, thickness: thickness, overlap: overlap),
      NSRect(x: 80, y: 376, width: 340, height: 24)
    )
    XCTAssertEqual(
      SpatialOverlayGeometry.glowEdgeFrame(
        for: .bottom, around: target, thickness: thickness, overlap: overlap),
      NSRect(x: 80, y: 180, width: 340, height: 24)
    )
    XCTAssertEqual(
      SpatialOverlayGeometry.glowEdgeFrame(
        for: .left, around: target, thickness: thickness, overlap: overlap),
      NSRect(x: 80, y: 180, width: 24, height: 220)
    )
    XCTAssertEqual(
      SpatialOverlayGeometry.glowEdgeFrame(
        for: .right, around: target, thickness: thickness, overlap: overlap),
      NSRect(x: 396, y: 180, width: 24, height: 220)
    )
  }
}
