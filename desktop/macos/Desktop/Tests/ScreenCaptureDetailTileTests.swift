import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Regression coverage for capture_screen detail tiles.
///
/// Vision APIs downscale images whose long edge exceeds ~1568 px, so a full-Retina
/// screenshot arrives at the model too blurry to read dense UI text — it then guesses
/// (e.g. conflating two similar product listings and citing the wrong size). The tool
/// now emits native-resolution tiles the model can Read for exact text. These tests pin
/// the partition math and the tool-result contract.
final class ScreenCaptureDetailTileTests: XCTestCase {

  // MARK: - Partition math

  func testNoTilesWhenImageAlreadyFits() {
    XCTAssertEqual(ScreenCaptureManager.detailTileRects(width: 1440, height: 900), [])
    XCTAssertEqual(ScreenCaptureManager.detailTileRects(width: 1568, height: 1568), [])
  }

  func testDegenerateInputsProduceNoTiles() {
    XCTAssertEqual(ScreenCaptureManager.detailTileRects(width: 0, height: 900), [])
    XCTAssertEqual(ScreenCaptureManager.detailTileRects(width: 3000, height: -1), [])
    XCTAssertEqual(ScreenCaptureManager.detailTileRects(width: 3000, height: 2000, maxLongEdge: 0), [])
  }

  func testRetinaLaptopDisplayTilesIntoLabeledQuadrants() {
    // 14" MBP Retina: 3024x1964 -> 2x2 grid of 1512x982 native-resolution quadrants.
    let tiles = ScreenCaptureManager.detailTileRects(width: 3024, height: 1964)
    XCTAssertEqual(tiles.count, 4)
    XCTAssertEqual(tiles.map(\.label), ["top-left", "top-right", "bottom-left", "bottom-right"])
    for tile in tiles {
      XCTAssertEqual(tile.rect.width, 1512)
      XCTAssertEqual(tile.rect.height, 982)
    }
  }

  func testWideDisplayTilesIntoLeftRightHalves() {
    // 2560x1440: only the width exceeds the cap -> left/right halves, full height.
    let tiles = ScreenCaptureManager.detailTileRects(width: 2560, height: 1440)
    XCTAssertEqual(tiles.map(\.label), ["left", "right"])
    XCTAssertEqual(tiles.map { Int($0.rect.width) }, [1280, 1280])
    XCTAssertEqual(tiles.map { Int($0.rect.height) }, [1440, 1440])
  }

  func testTilesExactlyCoverTheImageAndRespectTheLongEdgeCap() {
    // Property check across realistic display sizes, including odd dimensions and 5K.
    let sizes = [(3024, 1964), (2560, 1440), (5120, 2880), (3456, 2234), (3137, 2001), (1569, 900)]
    for (width, height) in sizes {
      let tiles = ScreenCaptureManager.detailTileRects(width: width, height: height)
      XCTAssertFalse(tiles.isEmpty, "\(width)x\(height) exceeds the cap and must tile")

      var coveredArea = 0
      for tile in tiles {
        XCTAssertLessThanOrEqual(
          Int(max(tile.rect.width, tile.rect.height)), ScreenCaptureManager.maxVisionTileLongEdge,
          "tile \(tile.label) of \(width)x\(height) exceeds the vision long-edge cap")
        XCTAssertGreaterThanOrEqual(tile.rect.minX, 0)
        XCTAssertGreaterThanOrEqual(tile.rect.minY, 0)
        XCTAssertLessThanOrEqual(Int(tile.rect.maxX), width)
        XCTAssertLessThanOrEqual(Int(tile.rect.maxY), height)
        coveredArea += Int(tile.rect.width) * Int(tile.rect.height)
      }
      // No gaps: within-bounds tiles whose areas sum to the full image, plus the
      // pairwise-disjointness below, is an exact cover.
      XCTAssertEqual(coveredArea, width * height, "\(width)x\(height) tiles must cover the image exactly")
      for i in tiles.indices {
        for j in tiles.indices where j > i {
          let overlap = tiles[i].rect.intersection(tiles[j].rect)
          XCTAssertTrue(
            overlap.isNull || overlap.width == 0 || overlap.height == 0,
            "tiles \(tiles[i].label) and \(tiles[j].label) overlap for \(width)x\(height)")
        }
      }
    }
  }

  // MARK: - Tool-result contract

  func testToolResultIsBarePathWhenThereAreNoTiles() {
    // Small displays keep the original single-line contract exactly.
    let result = ChatToolExecutor.captureScreenToolResult(fullPath: "/tmp/shot.webp", tiles: [])
    XCTAssertEqual(result, "/tmp/shot.webp")
  }

  func testToolResultListsTilesWithPositionsAndLegibilityGuidance() {
    let result = ChatToolExecutor.captureScreenToolResult(
      fullPath: "/tmp/shot.webp",
      tiles: [
        (label: "top-left", rect: CGRect(x: 0, y: 0, width: 1512, height: 982), path: "/tmp/shot-top-left.webp"),
        (label: "top-right", rect: CGRect(x: 1512, y: 0, width: 1512, height: 982), path: "/tmp/shot-top-right.webp"),
      ]
    )
    let lines = result.components(separatedBy: "\n")
    XCTAssertEqual(lines.first, "/tmp/shot.webp", "full-screen path must stay the first line")
    XCTAssertTrue(result.contains("- top-left (x 0-1512, y 0-982): /tmp/shot-top-left.webp"))
    XCTAssertTrue(result.contains("- top-right (x 1512-3024, y 0-982): /tmp/shot-top-right.webp"))
    // The guidance that makes the model re-read small text from a tile instead of guessing.
    XCTAssertTrue(result.contains("Read the tile"))
    XCTAssertTrue(result.contains("titles, prices, sizes, labels"))
  }
}
