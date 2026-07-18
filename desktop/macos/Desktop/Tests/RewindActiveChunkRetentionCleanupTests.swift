import XCTest

@testable import Omi_Computer

/// Exercises the first-frame interleaving where the encoder has created the
/// active day directory but AVAssetWriter has not created its output file yet.
/// Retention cleanup must keep that directory while still removing unrelated
/// empty day directories.
final class RewindActiveChunkRetentionCleanupTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "rewind-active-chunk-cleanup")
    try await RewindStorage.shared.initialize()
  }

  override func tearDown() async throws {
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testCleanupKeepsEmptyParentOfActiveChunkBeforeWriterCreatesOutput() async throws {
    let maybeVideosDirectory = await RewindStorage.shared.getVideosDirectory()
    let videosDirectory = try XCTUnwrap(maybeVideosDirectory)
    let activeChunkPath = "2030-01-02/chunk_030405.mp4"
    let activeDayDirectory = videosDirectory.appendingPathComponent("2030-01-02", isDirectory: true)
    let staleDayDirectory = videosDirectory.appendingPathComponent("2000-01-01", isDirectory: true)
    let fileManager = FileManager.default

    // This is the exact interval after `startVideoWriter` creates the day
    // directory and before AVAssetWriter creates the chunk file.
    try fileManager.createDirectory(at: activeDayDirectory, withIntermediateDirectories: true)
    try fileManager.createDirectory(at: staleDayDirectory, withIntermediateDirectories: true)
    XCTAssertTrue(fileManager.fileExists(atPath: activeDayDirectory.path), "precondition: active day is empty")
    XCTAssertTrue(fileManager.fileExists(atPath: staleDayDirectory.path), "precondition: stale day is empty")

    try await RewindStorage.shared.cleanupEmptyDirectories(
      protectingActiveVideoChunkPath: activeChunkPath)

    XCTAssertTrue(
      fileManager.fileExists(atPath: activeDayDirectory.path),
      "cleanup must not delete the current encoder chunk's parent before the writer creates its file"
    )
    XCTAssertFalse(
      fileManager.fileExists(atPath: staleDayDirectory.path),
      "the guard must not disable cleanup for unrelated empty video day directories"
    )
  }
}
