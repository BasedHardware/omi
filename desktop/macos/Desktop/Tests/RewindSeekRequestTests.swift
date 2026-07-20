import XCTest

@testable import Omi_Computer

@MainActor
final class RewindSeekRequestTests: XCTestCase {

  func testSeekRequestIsOneShot() {
    let store = RewindSeekRequestStore.shared
    let target = Date(timeIntervalSince1970: 500_000)
    store.request(target)
    XCTAssertEqual(store.consume(), target)
    XCTAssertNil(store.consume())
  }

  func testNearestScreenshotIndexPicksClosestFrame() {
    func frame(_ seconds: TimeInterval) -> Screenshot {
      Screenshot(timestamp: Date(timeIntervalSince1970: seconds), appName: "Test")
    }
    let frames = [frame(100), frame(200), frame(400)]

    // Exact hit, midpoints on both sides, and out-of-range clamps.
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 200), in: frames), 1)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 130), in: frames), 0)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 180), in: frames), 1)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 390), in: frames), 2)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 50), in: frames), 0)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(timeIntervalSince1970: 900), in: frames), 2)
    XCTAssertEqual(RewindPage.nearestScreenshotIndex(to: Date(), in: []), 0)
  }
}
