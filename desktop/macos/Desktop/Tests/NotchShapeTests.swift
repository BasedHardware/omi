import SwiftUI
import XCTest

@testable import Omi_Computer

final class NotchShapeTests: XCTestCase {
  func testCornerRadiiAreAnimatable() {
    var shape = NotchShape(topCornerRadius: 6, bottomCornerRadius: 14)
    XCTAssertEqual(shape.animatableData.first, 6)
    XCTAssertEqual(shape.animatableData.second, 14)
    shape.animatableData = AnimatablePair(20, 26)
    XCTAssertEqual(shape.animatableData.first, 20)
    XCTAssertEqual(shape.animatableData.second, 26)
  }

  func testPathSpansFullRectAndHugsTopEdge() {
    let rect = CGRect(x: 0, y: 0, width: 300, height: 40)
    let path = NotchShape(topCornerRadius: 6, bottomCornerRadius: 14).path(in: rect)
    let bounds = path.boundingRect
    // The silhouette must reach every edge of the rect: flush with the screen
    // edge on top, flared corners at the bottom.
    XCTAssertEqual(bounds.minX, rect.minX, accuracy: 0.001)
    XCTAssertEqual(bounds.maxX, rect.maxX, accuracy: 0.001)
    XCTAssertEqual(bounds.minY, rect.minY, accuracy: 0.001)
    XCTAssertEqual(bounds.maxY, rect.maxY, accuracy: 0.001)
  }

  func testBodyWallsSitInsetByTopRadius() {
    // The side walls are inset by the top radius: the body is narrower than the
    // top edge, which is what lets the top corners curve inward into the bezel.
    let rect = CGRect(x: 0, y: 0, width: 300, height: 40)
    let path = NotchShape(topCornerRadius: 10, bottomCornerRadius: 14).path(in: rect)
    XCTAssertFalse(path.contains(CGPoint(x: 5, y: 20)), "outside the left wall")
    XCTAssertFalse(path.contains(CGPoint(x: 295, y: 20)), "outside the right wall")
    XCTAssertTrue(path.contains(CGPoint(x: 15, y: 20)), "inside the body")
    XCTAssertTrue(path.contains(CGPoint(x: 150, y: 30)), "center bottom inside")
  }
}
