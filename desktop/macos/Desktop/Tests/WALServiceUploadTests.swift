import XCTest
@testable import Omi_Computer
import OmiWAL

@MainActor
final class WALServiceUploadTests: XCTestCase {

  private var walDir: URL!
  private var service: WALService!

  override func setUp() async throws {
    walDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("wal-upload-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)

    service = WALService(apiClient: APIClient(session: makeMockSession()))
    service.setWalDirectoryForTesting(walDir)
    service.setWalsForTesting([])
    service.uploadLocalFilesHandler = nil
  }

  override func tearDown() async throws {
    service.uploadLocalFilesHandler = nil
    try? FileManager.default.removeItem(at: walDir)
  }

  private func makeMockSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    return URLSession(configuration: config)
  }

  private func seedWalOnDisk(fileName: String = "audio_dev1_opus_16000_1_fs80_1700000000.bin") throws -> WALEntry {
    let wal = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      status: .miss,
      storage: .disk,
      filePath: fileName,
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi"
    )
    let fileURL = walDir.appendingPathComponent(fileName)
    try Data([0x01, 0x02, 0x03]).write(to: fileURL)
    service.setWalsForTesting([wal])
    return wal
  }

  func testUploadWithoutServerAckDoesNotMarkSynced() async throws {
    _ = try seedWalOnDisk()
    service.uploadLocalFilesHandler = { _ in
      throw APIError.syncUploadRejected(reason: "Server error")
    }

    await service.syncToCloud()

    XCTAssertEqual(service.wals.first?.status, .miss)
  }

  func testUploadMock202MarksUploadedNotSynced() async throws {
    let wal = try seedWalOnDisk()
    service.uploadLocalFilesHandler = { _ in .queued(jobId: "job-xyz") }

    try await service.uploadWalToCloudForTesting(wal)

    XCTAssertEqual(service.wals.first?.status, .uploaded)
    XCTAssertEqual(service.wals.first?.jobId, "job-xyz")
    XCTAssertNotEqual(service.wals.first?.status, .synced)
  }

  func testUploadMock200MarksSynced() async throws {
    let wal = try seedWalOnDisk()
    service.uploadLocalFilesHandler = { _ in
      .done(
        SyncLocalFilesResultResponse(
          newMemories: [],
          updatedMemories: [],
          failedSegments: 0,
          totalSegments: 0,
          errors: []
        ))
    }

    try await service.uploadWalToCloudForTesting(wal)

    XCTAssertEqual(service.wals.first?.status, .synced)
  }

  func testUpload429StaysMiss() async throws {
    _ = try seedWalOnDisk()
    service.uploadLocalFilesHandler = { _ in throw APIError.syncRateLimited(retryAfterSeconds: 60) }

    await service.syncToCloud()

    XCTAssertEqual(service.wals.first?.status, .miss)
  }

  // #9240: flush must not promote a `.memory` WAL to `.disk` when its frames were
  // never persisted — doing so loses the recording and sends a filePath-less entry
  // into the sync path where it fails with fileNotFound.
  func testFlushDoesNotPromoteMemoryWalWithoutBackingFile() throws {
    let wal = WALEntry(
      timerStart: 1_700_000_100,
      codec: "opus",
      status: .miss,
      storage: .memory,
      filePath: nil,
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi"
    )
    service.setWalsForTesting([wal])

    service.flushToDiskForTesting()

    XCTAssertEqual(service.wals.first?.storage, .memory)
  }

  func testFlushPromotesMemoryWalOnceFileIsOnDisk() throws {
    let fileName = "audio_dev1_opus_16000_1_fs80_1700000200.bin"
    try Data([0x01, 0x02, 0x03]).write(to: walDir.appendingPathComponent(fileName))
    let wal = WALEntry(
      timerStart: 1_700_000_200,
      codec: "opus",
      status: .miss,
      storage: .memory,
      filePath: fileName,
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi"
    )
    service.setWalsForTesting([wal])

    service.flushToDiskForTesting()

    XCTAssertEqual(service.wals.first?.storage, .disk)
  }
}
