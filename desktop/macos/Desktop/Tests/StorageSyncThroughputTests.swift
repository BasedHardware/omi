import XCTest

@testable import Omi_Computer

/// Regression coverage for SD-card sync throughput reporting.
///
/// `updateProgress` previously reassigned `lastProgressUpdate = now` *before* computing
/// `elapsed = now - lastProgressUpdate`, so `elapsed` was always 0 and the reported
/// speed was always 0 B/s. The rate math is now a pure function over an explicit
/// (bytesDelta, interval); these tests pin that it produces a real, non-zero rate.
final class StorageSyncThroughputTests: XCTestCase {
  func testBytesPerSecondComputesRealRate() {
    // 500 KB downloaded over a 0.5s interval → 1,000,000 B/s.
    XCTAssertEqual(
      StorageSyncService.bytesPerSecond(bytesDelta: 500_000, interval: 0.5),
      1_000_000,
      accuracy: 1e-6
    )
  }

  func testBytesPerSecondIsNonZeroForNonZeroDelta() {
    XCTAssertGreaterThan(
      StorageSyncService.bytesPerSecond(bytesDelta: 1, interval: 0.5), 0)
  }

  func testBytesPerSecondGuardsZeroAndNegativeInterval() {
    XCTAssertEqual(StorageSyncService.bytesPerSecond(bytesDelta: 100, interval: 0), 0)
    XCTAssertEqual(StorageSyncService.bytesPerSecond(bytesDelta: 100, interval: -1), 0)
  }
}
