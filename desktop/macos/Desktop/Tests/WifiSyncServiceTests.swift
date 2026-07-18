import OmiWAL
import XCTest

@testable import Omi_Computer

@MainActor
final class WifiSyncServiceTests: XCTestCase {

  private var walDir: URL!
  private var walService: WALService!
  private var wifiSync: WifiSyncService!

  override func setUp() async throws {
    walDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("wifi-sync-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)

    walService = WALService(
      apiClient: APIClient(session: makeMockSession()),
      walDirectoryForTesting: walDir
    )
    walService.setWalsForTesting([])
    walService.uploadLocalFilesHandler = nil

    wifiSync = WifiSyncService(walServiceForTesting: walService)
  }

  override func tearDown() async throws {
    walService.uploadLocalFilesHandler = nil
    try? FileManager.default.removeItem(at: walDir)
  }

  private func makeMockSession() -> URLSession {
    URLSession(configuration: .ephemeral)
  }

  private func validOpusFrame() -> Data {
    var frame = Data(repeating: 0, count: 80)
    frame[0] = 0xb8
    return frame
  }

  private func seedCompletedSdCardWal(totalBytes: Int = 80) -> WALEntry {
    walService.createSdCardWal(
      device: "dev1",
      deviceModel: "Omi",
      codec: "opus",
      totalBytes: totalBytes,
      currentOffset: 0
    )
  }

  func testFinishSyncUploadsToCloud() async throws {
    let wal = seedCompletedSdCardWal()
    let frame = validOpusFrame()

    var uploadCalled = false
    walService.uploadLocalFilesHandler = { _ in
      uploadCalled = true
      return .done(
        SyncLocalFilesResultResponse(
          newMemories: [],
          updatedMemories: [],
          failedSegments: 0,
          totalSegments: 1,
          errors: []
        ))
    }

    await wifiSync.finishSyncForTesting(
      wal: wal,
      frames: [frame],
      downloadedBytes: 80
    )

    XCTAssertTrue(uploadCalled, "finishSync must call syncToCloud after download")
    XCTAssertEqual(walService.wals.first?.status, .synced)
  }
}
