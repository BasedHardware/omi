import OmiWAL
import XCTest

@testable import Omi_Computer

/// Regression coverage for orphaned SD-card WAL entries.
///
/// `createSdCardWal` reserves a `.miss` / `.sdcard` entry before any data is
/// downloaded. Every failed/aborted sync path used to leave that entry behind,
/// and it counts toward the persisted "N pending" badge forever.
/// `removeSdCardWalIfEmpty` drops an entry that never received frames while
/// keeping one that did.
@MainActor
final class WALServiceOrphanSdCardTests: XCTestCase {
  private var walDir: URL!
  private var service: WALService!

  override func setUp() async throws {
    walDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("wal-orphan-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)
    service = WALService(
      apiClient: APIClient(session: URLSession(configuration: .ephemeral)),
      walDirectoryForTesting: walDir
    )
    service.setWalsForTesting([])
  }

  override func tearDown() async throws {
    try? FileManager.default.removeItem(at: walDir)
  }

  func testRemovesReservedButEmptySdCardWal() {
    let wal = service.createSdCardWal(
      device: "dev1", deviceModel: "Omi", codec: "opus", totalBytes: 8000, currentOffset: 0)
    XCTAssertEqual(service.pendingWals.count, 1, "the reserved entry counts as pending")

    service.removeSdCardWalIfEmpty(walId: wal.id)

    XCTAssertNil(service.getWal(id: wal.id), "an empty failed sync must not leave a phantom WAL")
    XCTAssertEqual(service.pendingWals.count, 0)
  }

  func testKeepsSdCardWalThatDownloadedData() {
    let wal = service.createSdCardWal(
      device: "dev1", deviceModel: "Omi", codec: "opus", totalBytes: 8000, currentOffset: 0)
    // A WAL with a persisted file path represents real downloaded audio.
    var downloaded = wal
    downloaded.status = .miss
    downloaded.filePath = "audio_dev1_opus_16000_1_fs80_1700000000.bin"
    service.setWalsForTesting([downloaded])

    service.removeSdCardWalIfEmpty(walId: wal.id)

    XCTAssertNotNil(service.getWal(id: wal.id), "a WAL with downloaded frames must be kept")
  }
}
