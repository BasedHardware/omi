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
  private var storageRoot: URL!
  private var userDir: URL!
  private var savedRetentionDays: Int = 7
  private var previousLocalProfile: String?
  private var previousStorageName: String?

  override func setUp() async throws {
    try await super.setUp()

    // Isolate all Rewind storage to a throwaway *root*, not just a throwaway user id: this suite
    // writes real video chunk files, and anything that ends a test before `tearDown` would
    // otherwise leave them inside the user's own `~/Library/Application Support/Omi` tree.
    previousLocalProfile = ProcessInfo.processInfo.environment["OMI_DESKTOP_LOCAL_PROFILE"]
    previousStorageName = ProcessInfo.processInfo.environment["OMI_LOCAL_PROFILE_STORAGE_NAME"]
    let storageName = "OmiTests-retention-\(UUID().uuidString)"
    setenv("OMI_DESKTOP_LOCAL_PROFILE", "1", 1)
    setenv("OMI_LOCAL_PROFILE_STORAGE_NAME", storageName, 1)

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    storageRoot = appSupport.appendingPathComponent(storageName, isDirectory: true)

    // Same lifecycle `RewindStorageTestIsolation` uses: the pool has to be closed and *retargeted*
    // to this suite's user. Setting `currentUserId` alone is not enough — a `configuredUserId` left
    // behind by an earlier suite in the same process outranks it, and the database would open for
    // that user instead.
    testUserId = "retention-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await RewindStorageTestIsolation.invalidateAllStorageCaches()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()
    try await RewindStorage.shared.initialize()

    userDir =
      storageRoot
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)

    // Fail loudly rather than quietly writing recordings into the user's real Omi directory if
    // the storage redirection ever stops working.
    let videosDirectory = await RewindStorage.shared.getVideosDirectory()
    XCTAssertEqual(
      videosDirectory?.standardizedFileURL,
      userDir.appendingPathComponent("Videos", isDirectory: true).standardizedFileURL,
      "test recordings must be written under the throwaway storage root, not the user's Omi data")

    // Pin retention to a known value so the test is deterministic.
    savedRetentionDays = RewindSettings.shared.retentionDays
    RewindSettings.shared.retentionDays = 7
  }

  override func tearDown() async throws {
    RewindSettings.shared.retentionDays = savedRetentionDays
    // `VideoChunkEncoder` is a process-wide singleton pinned to one owner's videos directory, so a
    // second test in this process is a storage-owner change and must cross the same boundary the
    // app crosses when the signed-in user changes. Without it the next `RewindStorage.initialize`
    // throws "Video encoder must reset before changing storage owner".
    await RewindStorage.shared.reset()
    await RewindDatabase.shared.close()
    await RewindStorageTestIsolation.invalidateAllStorageCaches()
    await RewindDatabase.shared.configure(userId: nil)
    if let storageRoot { try? FileManager.default.removeItem(at: storageRoot) }
    RewindDatabase.currentUserId = nil
    if let previousLocalProfile {
      setenv("OMI_DESKTOP_LOCAL_PROFILE", previousLocalProfile, 1)
    } else {
      unsetenv("OMI_DESKTOP_LOCAL_PROFILE")
    }
    if let previousStorageName {
      setenv("OMI_LOCAL_PROFILE_STORAGE_NAME", previousStorageName, 1)
    } else {
      unsetenv("OMI_LOCAL_PROFILE_STORAGE_NAME")
    }
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
