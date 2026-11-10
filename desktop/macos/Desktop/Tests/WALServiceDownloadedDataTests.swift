import OmiWAL
import XCTest

@testable import Omi_Computer

/// Regression coverage for the SD-card download persistence path.
///
/// `updateWalWithDownloadedData` used to block the main actor with
/// `DispatchGroup.wait()` while a large download was written to disk, freezing
/// the whole UI. It is now `async` and awaits an off-main write, so the caller
/// suspends instead of blocking.
@MainActor
final class WALServiceDownloadedDataTests: XCTestCase {
  private let walDir = FileManager.default.temporaryDirectory
    .appendingPathComponent("wal-downloaded-data-test-\(UUID().uuidString)", isDirectory: true)
  private lazy var service = WALService(
    apiClient: APIClient(session: URLSession(configuration: .ephemeral)),
    walDirectoryForTesting: walDir
  )

  override func setUp() async throws {
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)
    service.setWalsForTesting([])
  }

  override func tearDown() async throws {
    try? FileManager.default.removeItem(at: walDir)
  }

  func testPersistsFramesAndSetsFilePath() async throws {
    let frames = [Data([0xAA, 0xBB]), Data([0xCC, 0xDD, 0xEE])]
    let wal = service.createSdCardWal(
      device: "dev1", deviceModel: "Omi", codec: "opus", totalBytes: 5, currentOffset: 0)

    await service.updateWalWithDownloadedData(
      walId: wal.id, downloadedBytes: 5, frames: frames)

    let updated = try XCTUnwrap(service.getWal(id: wal.id))
    let fileName = try XCTUnwrap(updated.filePath, "filePath must be set before the caller uploads")
    XCTAssertEqual(updated.storage, .disk, "a fully downloaded WAL is promoted to disk")
    XCTAssertEqual(updated.totalFrames, frames.count)

    let fileURL = walDir.appendingPathComponent(fileName)
    let onDisk = try Data(contentsOf: fileURL)
    XCTAssertEqual(onDisk, WALService.encodeFrames(frames))
  }

  func testPartialDownloadPersistsFramesAndOffset() async throws {
    let wal = service.createSdCardWal(
      device: "dev1", deviceModel: "Omi", codec: "opus", totalBytes: 100, currentOffset: 0)

    await service.updateWalWithDownloadedData(
      walId: wal.id, downloadedBytes: 10, frames: [Data([0x01])])

    let updated = try XCTUnwrap(service.getWal(id: wal.id))
    XCTAssertNotNil(updated.filePath)
    XCTAssertEqual(updated.storageOffset, 10)
    XCTAssertEqual(updated.totalFrames, 1)
  }

  func testMissingWalIsIgnored() async {
    await service.updateWalWithDownloadedData(
      walId: "does-not-exist", downloadedBytes: 1, frames: [Data([0x01])])
    XCTAssertTrue(service.wals.isEmpty)
  }

  /// Source guard: the persistence path must not reintroduce a blocking wait on
  /// the main actor. `WALService` is `@MainActor`, so `group.wait()` or a
  /// synchronous `DispatchQueue.sync` here freezes the UI for the whole write.
  func testWritePathDoesNotBlockTheMainActor() throws {
    // omi-test-quality: source-inspection -- static contract: forbids a blocking wait on the main actor
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/WAL/WALService.swift"))

    XCTAssertFalse(
      source.contains("group.wait()"),
      "WALService must not block the main actor with DispatchGroup.wait()")
    XCTAssertFalse(
      source.contains("DispatchQueue.global(qos: .utility).sync"),
      "WALService must await the off-main write instead of DispatchQueue.sync")
    XCTAssertTrue(
      source.contains("func updateWalWithDownloadedData(walId: String, downloadedBytes: Int, frames: [Data]) async"),
      "updateWalWithDownloadedData must be async so callers suspend rather than block")
  }
}
