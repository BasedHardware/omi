import GRDB
import XCTest

@testable import Omi_Computer

final class RewindVideoRebuildIntegrityTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(
      userIdPrefix: "rewind-video-rebuild-integrity")
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testReplacingSameChunkTwiceKeepsExactlyOneRowPerFrameOffset() async throws {
    let path = "2026-04-09/chunk_143022.mp4"
    let baseDate = Date(timeIntervalSince1970: 1_776_000_000)
    let screenshots = makeScreenshots(path: path, baseDate: baseDate, frameCount: 3)

    let firstCommitted = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
      path: path,
      screenshots: screenshots)
    let secondCommitted = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
      path: path,
      screenshots: screenshots)

    XCTAssertEqual(firstCommitted, 3)
    XCTAssertEqual(secondCommitted, 3)

    let rows = try await fetchScreenshots(path: path)
    XCTAssertEqual(rows.count, 3)
    XCTAssertEqual(rows.compactMap(\.frameOffset), [0, 1, 2])
    XCTAssertEqual(Set(rows.compactMap(\.frameOffset)).count, rows.count)
    XCTAssertTrue(rows.allSatisfy { $0.appName == "Unknown" })
    XCTAssertTrue(rows.allSatisfy { $0.windowTitle == nil })
  }

  func testFailedReplacementRollsBackDeletionAndPreservesOriginalRows() async throws {
    let path = "2026-04-10/chunk_090000.mp4"
    let originalDate = Date(timeIntervalSince1970: 1_776_100_000)
    let originals = makeScreenshots(
      path: path,
      baseDate: originalDate,
      frameCount: 2,
      appName: "Original")
    _ = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
      path: path,
      screenshots: originals)

    let pool = try await databasePool()
    try await pool.write { db in
      try db.execute(
        sql: """
          CREATE TRIGGER inject_rebuild_insert_failure
          BEFORE INSERT ON screenshots
          WHEN NEW.videoChunkPath = '2026-04-10/chunk_090000.mp4'
          BEGIN
            SELECT RAISE(ABORT, 'injected rebuild insert failure');
          END
          """)
    }

    let replacements = makeScreenshots(
      path: path,
      baseDate: originalDate.addingTimeInterval(100),
      frameCount: 3,
      appName: "Replacement")
    do {
      _ = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
        path: path,
        screenshots: replacements)
      XCTFail("the injected insert failure should abort the replacement")
    } catch {
      // Expected: the important assertion is that the preceding DELETE rolled back too.
    }

    let rows = try await fetchScreenshots(path: path)
    XCTAssertEqual(rows.count, 2)
    XCTAssertEqual(rows.compactMap(\.frameOffset), [0, 1])
    XCTAssertEqual(rows.map(\.appName), ["Original", "Original"])
    XCTAssertEqual(rows.map(\.timestamp), [originalDate, originalDate.addingTimeInterval(1)])
  }

  func testReplacementRejectsForeignEmptyAndDuplicateFrameSetsBeforeDeleting() async throws {
    let path = "2026-04-11/chunk_100000.mp4"
    let baseDate = Date(timeIntervalSince1970: 1_776_200_000)
    let originals = makeScreenshots(path: path, baseDate: baseDate, frameCount: 2)
    _ = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
      path: path,
      screenshots: originals)

    var foreignFrames = originals
    foreignFrames[1].videoChunkPath = "2026-04-11/chunk_other.mp4"
    await assertReplacementFails(path: path, screenshots: foreignFrames)
    await assertReplacementFails(path: path, screenshots: [])

    var duplicateOffsets = originals
    duplicateOffsets[1].frameOffset = duplicateOffsets[0].frameOffset
    await assertReplacementFails(path: path, screenshots: duplicateOffsets)

    let rows = try await fetchScreenshots(path: path)
    XCTAssertEqual(rows.count, 2)
    XCTAssertEqual(rows.compactMap(\.frameOffset), [0, 1])
  }

  func testFailureSummaryHasFixedCardinalityAndNoRawChunkDetails() {
    var summary = RewindRebuildFailureSummary(totalChunks: 10_005)
    for _ in 0..<10_000 {
      summary.record(.videoRead)
    }
    summary.record(.unparseablePath)
    summary.record(.zeroFrames)
    summary.record(.invalidTimeline)
    summary.record(.databaseWrite)

    XCTAssertEqual(summary.failedChunkCount, 10_004)
    XCTAssertEqual(
      summary.message,
      "Rebuild committed 1 of 10005 video chunks; 10004 failed "
        + "(unparseable_path=1, zero_frames=1, invalid_timeline=1, "
        + "video_read=10000, database_write=1)")
    XCTAssertLessThan(summary.message.utf8.count, 180)
    XCTAssertFalse(summary.message.contains("2026-04-09/chunk_143022.mp4"))
  }

  private func makeScreenshots(
    path: String,
    baseDate: Date,
    frameCount: Int,
    appName: String = "Unknown"
  ) -> [Screenshot] {
    (0..<frameCount).map { offset in
      Screenshot(
        timestamp: baseDate.addingTimeInterval(Double(offset)),
        appName: appName,
        windowTitle: nil,
        imagePath: "",
        videoChunkPath: path,
        frameOffset: offset,
        isIndexed: false)
    }
  }

  private func databasePool() async throws -> DatabasePool {
    guard let pool = await RewindDatabase.shared.getDatabaseQueue() else {
      throw RewindError.databaseNotInitialized
    }
    return pool
  }

  private func fetchScreenshots(path: String) async throws -> [Screenshot] {
    let pool = try await databasePool()
    return try await pool.read { db in
      try Screenshot.fetchAll(
        db,
        sql: """
          SELECT * FROM screenshots
          WHERE videoChunkPath = ?
          ORDER BY frameOffset
          """,
        arguments: [path])
    }
  }

  private func assertReplacementFails(path: String, screenshots: [Screenshot]) async {
    do {
      _ = try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
        path: path,
        screenshots: screenshots)
      XCTFail("invalid replacement input should fail")
    } catch RewindError.storageError {
      // Expected validation failure.
    } catch {
      XCTFail("expected storage validation error, got \(error)")
    }
  }
}
