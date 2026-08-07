import XCTest

@testable import Omi_Computer

/// Regression test for the Rewind data-retention bug: `RewindIndexer.runCleanup()`
/// existed and was correct, but was never called from anywhere, so screen
/// recordings accumulated forever regardless of the "Data Retention" setting.
///
/// This exercises the real cleanup path (DB delete → orphaned-chunk detection →
/// on-disk file deletion) against an isolated throwaway user directory and asserts
/// that chunks older than the retention window are physically removed while
/// in-window chunks are kept.
final class RewindRetentionCleanupTests: XCTestCase {

  private var testUserId: String!
  private var userDir: URL!
  private var savedRetentionDays: Int = 7

  override func setUp() async throws {
    try await super.setUp()

    // Isolate all Rewind storage to a unique throwaway user so we never touch
    // real recordings (storage is keyed by userId, not bundle id).
    testUserId = "retention-test-\(UUID().uuidString)"
    RewindDatabase.currentUserId = testUserId
    try await RewindDatabase.shared.initialize()
    try await RewindStorage.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)

    // Pin retention to a known value so the test is deterministic.
    savedRetentionDays = RewindSettings.shared.retentionDays
    RewindSettings.shared.retentionDays = 7
  }

  override func tearDown() async throws {
    RewindSettings.shared.retentionDays = savedRetentionDays
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  func testRunCleanupDeletesChunksOlderThanRetentionAndKeepsRecentOnes() async throws {
    let fm = FileManager.default
    let videosDir = userDir.appendingPathComponent("Videos", isDirectory: true)

    let retentionDays = RewindSettings.shared.retentionDays
    let oldDate = Calendar.current.date(byAdding: .day, value: -(retentionDays + 30), to: Date())!
    let recentDate = Date()

    let oldChunkRel = "2000-01-01/chunk_old.mp4"
    let recentChunkRel = "2099-01-01/chunk_recent.mp4"

    // Lay down two real on-disk chunk files.
    for rel in [oldChunkRel, recentChunkRel] {
      let full = videosDir.appendingPathComponent(rel)
      try fm.createDirectory(
        at: full.deletingLastPathComponent(), withIntermediateDirectories: true)
      try Data("fake-mp4-bytes".utf8).write(to: full)
    }
    let oldPath = videosDir.appendingPathComponent(oldChunkRel).path
    let recentPath = videosDir.appendingPathComponent(recentChunkRel).path
    XCTAssertTrue(fm.fileExists(atPath: oldPath), "precondition: old chunk written")
    XCTAssertTrue(fm.fileExists(atPath: recentPath), "precondition: recent chunk written")

    // Reference each chunk from a screenshot row with the matching timestamp.
    _ = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: oldDate, appName: "RetentionTest", videoChunkPath: oldChunkRel,
        frameOffset: 0, isIndexed: true))
    _ = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: recentDate, appName: "RetentionTest", videoChunkPath: recentChunkRel,
        frameOffset: 0, isIndexed: true))

    // Exercise the exact production cleanup that the fix now schedules.
    await RewindIndexer.shared.runCleanup()

    XCTAssertFalse(
      fm.fileExists(atPath: oldPath),
      "retention cleanup must delete the chunk whose frames are older than the retention window")
    XCTAssertTrue(
      fm.fileExists(atPath: recentPath),
      "retention cleanup must keep chunks within the retention window")
  }

  /// "Keep everything" is what makes an all-time Rewind possible.
  ///
  /// The page can only ever show what the database still holds, so this asserts the *absence* of a
  /// deletion through the same production entry point as the test above: a year-old frame and its
  /// chunk both survive a real cleanup pass. Without this the timeline work above it is a view over
  /// data the app deletes out from under it every six hours.
  func testKeepEverythingRetentionDeletesNothing() async throws {
    let fm = FileManager.default
    let videosDir = userDir.appendingPathComponent("Videos", isDirectory: true)

    RewindSettings.shared.retentionDays = RewindSettings.unlimitedRetentionDays

    let ancientDate = Calendar.current.date(byAdding: .day, value: -365, to: Date())!
    let ancientChunkRel = "1999-01-01/chunk_ancient.mp4"
    let full = videosDir.appendingPathComponent(ancientChunkRel)
    try fm.createDirectory(at: full.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data("fake-mp4-bytes".utf8).write(to: full)

    let inserted = try await RewindDatabase.shared.insertScreenshot(
      Screenshot(
        timestamp: ancientDate, appName: "RetentionTest", videoChunkPath: ancientChunkRel,
        frameOffset: 0, isIndexed: true))
    let rowID = try XCTUnwrap(inserted.id)

    await RewindIndexer.shared.runCleanup()

    XCTAssertTrue(
      fm.fileExists(atPath: full.path),
      "keep-everything retention must not delete a year-old chunk")
    let survivor = try await RewindDatabase.shared.getScreenshot(id: rowID)
    XCTAssertNotNil(
      survivor,
      "keep-everything retention must leave the frame's row in place so Rewind can still reach it")
  }

}

/// The retention setting decides whether an all-time Rewind is possible at all: every value other
/// than unlimited is a `DELETE FROM screenshots` window, so a UI able to draw a year of history
/// still cannot show one. These pin the boundary itself, without a database or a clock.
final class RewindRetentionCutoffTests: XCTestCase {

  func testUnlimitedRetentionHasNoCutoff() {
    XCTAssertNil(
      RewindSettings.retentionCutoff(retentionDays: RewindSettings.unlimitedRetentionDays),
      "Keep-everything must produce no cutoff at all — a very old cutoff is still a promise to delete")
  }

  func testNonPositiveRetentionFailsSafeRatherThanDeletingEverything() {
    // A negative day count from an older build or a hand-edited plist would otherwise compute a
    // cutoff in the *future* and delete the entire capture history on the next frame.
    XCTAssertNil(RewindSettings.retentionCutoff(retentionDays: -5))
    XCTAssertTrue(RewindSettings.isUnlimited(retentionDays: -5))
  }

  func testLimitedRetentionCutsOffAtTheRequestedWindow() throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let cutoff = try XCTUnwrap(RewindSettings.retentionCutoff(retentionDays: 7, now: now))

    let days = Calendar.current.dateComponents([.day], from: cutoff, to: now).day
    XCTAssertEqual(days, 7)
    XCTAssertLessThan(cutoff, now)
  }
}
