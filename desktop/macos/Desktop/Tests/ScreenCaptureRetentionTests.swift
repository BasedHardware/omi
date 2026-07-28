import XCTest

@testable import Omi_Computer

/// Regression coverage for chat-tool screenshot retention.
///
/// `captureScreenWithDetailTiles` (the `capture_screen` chat tool) wrote the
/// full frame plus native-resolution detail tiles into
/// ~/Documents/Omi/Screenshots and nothing ever deleted them — unbounded disk
/// growth. Captures now sweep files older than the retention window.
final class ScreenCaptureRetentionTests: XCTestCase {
  func testStaleFilesBeyondRetentionAreSelected() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let dir = URL(fileURLWithPath: "/tmp/omi-screens")
    let fresh = (url: dir.appendingPathComponent("a.webp"), modified: now.addingTimeInterval(-60))
    let stale = (
      url: dir.appendingPathComponent("b.webp"),
      modified: now.addingTimeInterval(-(ScreenCaptureManager.screenshotRetention + 60))
    )

    let purge = ScreenCaptureManager.staleScreenshotURLs(
      [fresh, stale], now: now, retention: ScreenCaptureManager.screenshotRetention)

    XCTAssertEqual(purge, [stale.url], "only files older than the retention window are swept")
  }

  func testExactlyAtRetentionBoundaryIsKept() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let dir = URL(fileURLWithPath: "/tmp/omi-screens")
    let atBoundary = (
      url: dir.appendingPathComponent("c.webp"),
      modified: now.addingTimeInterval(-ScreenCaptureManager.screenshotRetention)
    )
    let purge = ScreenCaptureManager.staleScreenshotURLs(
      [atBoundary], now: now, retention: ScreenCaptureManager.screenshotRetention)
    XCTAssertTrue(purge.isEmpty, "a file exactly at the boundary is not yet stale")
  }
}
