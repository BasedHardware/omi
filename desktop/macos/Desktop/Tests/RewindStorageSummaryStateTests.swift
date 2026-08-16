import XCTest

@testable import Omi_Computer

/// Settings → Rewind → Storage read "Loading..." forever whenever
/// `RewindIndexer.getStats()` returned `nil`, because `nil` is both "no read has
/// finished yet" and "the Rewind database could not be read". The card now
/// resolves its caption from the stats *and* whether a read completed, so an
/// unavailable store says so and offers a retry instead of pretending to load.
final class RewindStorageSummaryStateTests: XCTestCase {
  func testShowsLoadingBeforeTheFirstReadCompletes() {
    XCTAssertEqual(
      RewindStorageSummaryState.resolve(stats: nil, didCompleteRead: false),
      .loading)
  }

  func testFailedReadIsReportedRatherThanLeftLoading() {
    XCTAssertEqual(
      RewindStorageSummaryState.resolve(stats: nil, didCompleteRead: true),
      .unavailable,
      "a completed read that produced no stats is a failure, not a pending load")
  }

  func testStatsRenderFrameCountAndFormattedSize() {
    XCTAssertEqual(
      RewindStorageSummaryState.resolve(
        stats: (total: 1234, indexed: 1200, storageSize: 5_368_709_120),
        didCompleteRead: true),
      .loaded(caption: "1234 frames • \(RewindStorage.formatBytes(5_368_709_120))"))
  }

  func testAnEmptyStoreIsLoadedRatherThanUnavailable() {
    XCTAssertEqual(
      RewindStorageSummaryState.resolve(
        stats: (total: 0, indexed: 0, storageSize: 0),
        didCompleteRead: true),
      .loaded(caption: "0 frames • \(RewindStorage.formatBytes(0))"),
      "a Rewind profile with nothing captured yet is readable, just empty")
  }
}

/// A Rewind store whose roots have not been resolved yet holds an unknown number
/// of bytes, not zero. Summing the two unresolved optionals to `0` made the
/// Storage card state a confident "Zero KB" for a store that actually held tens
/// of megabytes — seen live as one bundle reporting `total_frames: 328` with
/// `storage_bytes: 0` while two siblings on the same account reported ~44–48 MB.
final class RewindStorageRootResolutionTests: XCTestCase {
  private let screenshots = URL(fileURLWithPath: "/tmp/omi-test/Screenshots", isDirectory: true)
  private let videos = URL(fileURLWithPath: "/tmp/omi-test/Videos", isDirectory: true)

  func testUninitializedStorageHasNoMeasurableRoots() {
    XCTAssertNil(
      RewindStorage.resolvedStorageRoots(screenshots: nil, videos: nil),
      "before initialize() — and after resetForUserSwitch() — size is unknown, not zero")
  }

  func testBothRootsAreMeasuredWhenResolved() {
    XCTAssertEqual(
      RewindStorage.resolvedStorageRoots(screenshots: screenshots, videos: videos),
      [screenshots, videos])
  }

  func testAPartiallyResolvedStoreStillMeasuresWhatItHas() {
    XCTAssertEqual(
      RewindStorage.resolvedStorageRoots(screenshots: nil, videos: videos),
      [videos],
      "the video root alone is a real, measurable total")
    XCTAssertEqual(
      RewindStorage.resolvedStorageRoots(screenshots: screenshots, videos: nil),
      [screenshots])
  }
}
