import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Coordinate conversion is the whole correctness story of computer use: every
/// other tool is a wrapper around a point that is either right or somewhere else
/// on the user's screen.
final class CuaFrameGeometryTests: XCTestCase {
  /// A 16:10 Retina laptop: 1512x982 points, 3024x1964 backing pixels.
  private let laptop = CGRect(x: 0, y: 0, width: 1512, height: 982)

  func testFittedSizeLeavesASmallCaptureAlone() {
    let size = CuaFrameGeometry.fittedImageSize(
      source: CGSize(width: 800, height: 600), maxLongEdge: 1568)
    XCTAssertEqual(size, CGSize(width: 800, height: 600))
  }

  func testFittedSizeCapsTheLongEdgeAndKeepsTheAspect() {
    let size = CuaFrameGeometry.fittedImageSize(
      source: CGSize(width: 3024, height: 1964), maxLongEdge: 1568)
    XCTAssertEqual(size?.width, 1568)
    XCTAssertEqual(size?.height, 1018)  // 1964 * 1568 / 3024, rounded
  }

  func testFittedSizeCapsTheLongEdgeOfAPortraitSource() {
    let size = CuaFrameGeometry.fittedImageSize(
      source: CGSize(width: 1080, height: 1920), maxLongEdge: 1568)
    XCTAssertEqual(size?.height, 1568)
    XCTAssertEqual(size?.width, 882)
  }

  /// A zero-area source made the old capture path compute a NaN aspect ratio and
  /// trap on `Int(NaN)`. There is no image to deliver, so there is no size.
  func testFittedSizeRefusesAZeroAreaSource() {
    XCTAssertNil(
      CuaFrameGeometry.fittedImageSize(source: CGSize(width: 0, height: 900), maxLongEdge: 1568))
  }

  /// The Retina case: the model sees a 1568-wide image of a 1512-point display,
  /// so its coordinates are neither points nor backing pixels.
  func testImagePointBecomesAGlobalPointThroughTheDownscale() {
    let geometry = CuaFrameGeometry(bounds: laptop, imageSize: CGSize(width: 1568, height: 1018))
    let center = geometry.globalPoint(forImagePoint: CGPoint(x: 784, y: 509))
    XCTAssertEqual(center.x, 756, accuracy: 0.5)
    XCTAssertEqual(center.y, 491, accuracy: 0.5)
  }

  /// The bug this whole type exists to prevent: a second display starts at a
  /// non-zero global origin, so a point in its screenshot is not a point on the
  /// main screen. Aiming without the origin puts every click on the wrong monitor.
  func testSecondDisplayCoordinatesCarryTheirOrigin() {
    let external = CGRect(x: 1512, y: -420, width: 2560, height: 1440)
    let geometry = CuaFrameGeometry(bounds: external, imageSize: CGSize(width: 1280, height: 720))
    let topLeft = geometry.globalPoint(forImagePoint: .zero)
    XCTAssertEqual(topLeft, CGPoint(x: 1512, y: -420))

    let middle = geometry.globalPoint(forImagePoint: CGPoint(x: 640, y: 360))
    XCTAssertEqual(middle, CGPoint(x: 2792, y: 300))
  }

  /// A model pointing one pixel past the edge means the edge. Refusing the turn
  /// teaches it nothing; the clamp keeps the click on the display it named.
  func testOutOfRangePointsClampToTheFrame() {
    let geometry = CuaFrameGeometry(bounds: laptop, imageSize: CGSize(width: 1512, height: 982))
    XCTAssertEqual(
      geometry.globalPoint(forImagePoint: CGPoint(x: -40, y: 5000)),
      CGPoint(x: 0, y: 982))
  }

  func testGlobalPointsComeBackAsImagePoints() {
    let geometry = CuaFrameGeometry(
      bounds: CGRect(x: 100, y: 50, width: 800, height: 600),
      imageSize: CGSize(width: 400, height: 300))
    let image = geometry.imagePoint(forGlobalPoint: CGPoint(x: 500, y: 350))
    XCTAssertEqual(image?.x ?? 0, 200, accuracy: 0.001)
    XCTAssertEqual(image?.y ?? 0, 150, accuracy: 0.001)
  }

  /// The pointer is often not on the display that was captured. Saying so beats
  /// reporting a coordinate that is inside the picture and wrong.
  func testAGlobalPointOutsideTheFrameHasNoImagePoint() {
    let geometry = CuaFrameGeometry(bounds: laptop, imageSize: CGSize(width: 1512, height: 982))
    XCTAssertNil(geometry.imagePoint(forGlobalPoint: CGPoint(x: 2000, y: 300)))
  }

  func testAFrameRegistryKeepsTheLastFourFrames() {
    let registry = CuaFrameRegistry()
    let ids = (0..<6).map { index in
      registry.store(
        CuaFrameGeometry(
          bounds: CGRect(x: CGFloat(index), y: 0, width: 100, height: 100),
          imageSize: CGSize(width: 100, height: 100)))
    }
    XCTAssertNil(registry.geometry(id: ids[0]))
    XCTAssertNil(registry.geometry(id: ids[1]))
    XCTAssertNotNil(registry.geometry(id: ids[2]))
    XCTAssertEqual(registry.latest()?.id, ids[5])
  }
}
