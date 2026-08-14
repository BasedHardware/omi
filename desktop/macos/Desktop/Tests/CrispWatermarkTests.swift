import XCTest

@testable import Omi_Computer

/// Regression test for the Crisp first-launch notification-spam bug: Crisp message
/// timestamps are epoch milliseconds, but the initial polling watermark was seeded
/// with `Date().timeIntervalSince1970` (seconds). A seconds value (~1e9) is ~1000x
/// below any real message timestamp (~1e12), so the first poll's `since` filter
/// matched every historical operator message and fired a notification for each.
final class CrispWatermarkTests: XCTestCase {

  func testInitialWatermarkIsInMilliseconds() {
    // 1_000_000_000 s → 1_000_000_000_000 ms.
    let fixed = Date(timeIntervalSince1970: 1_000_000_000)
    XCTAssertEqual(CrispManager.initialWatermark(now: fixed), 1_000_000_000_000)
  }

  func testInitialWatermarkIsComparableToCrispMillisecondTimestamps() {
    // A message from one hour before "now" must be considered already-seen (its
    // ms timestamp is below the ms watermark), which only holds if both are ms.
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let watermark = CrispManager.initialWatermark(now: now)
    let oneHourAgoMillis = UInt64((now.timeIntervalSince1970 - 3600) * 1000)
    XCTAssertGreaterThan(watermark, oneHourAgoMillis)
    // Guard against the historical seconds bug: the watermark must be far above
    // any seconds-scale value.
    XCTAssertGreaterThan(watermark, 1_000_000_000_000)
  }
}
