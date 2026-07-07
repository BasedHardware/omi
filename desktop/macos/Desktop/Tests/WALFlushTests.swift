import XCTest
@testable import Omi_Computer
import OmiWAL

@MainActor
final class WALFlushTests: XCTestCase {

  private var walDir: URL!
  private var service: WALService!

  override func setUp() async throws {
    walDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("wal-flush-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)

    service = WALService(apiClient: APIClient(session: makeMockSession()))
    service.setWalDirectoryForTesting(walDir)
    service.setWalsForTesting([])
    service.diskWriteDelayForTesting = nil
  }

  override func tearDown() async throws {
    service.diskWriteDelayForTesting = nil
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

  func testFlushWaitsForInFlightWriteAndSetsFilePath() throws {
    service.diskWriteDelayForTesting = 0.2
    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(validOpusFrame())
    service.chunkCurrentFramesForTesting()

    XCTAssertEqual(service.wals.first?.storage, .memory)

    service.flushToDiskForTesting()

    let wal = try XCTUnwrap(service.wals.first)
    XCTAssertEqual(wal.storage, .disk)
    XCTAssertNotNil(wal.filePath)
    let fileURL = walDir.appendingPathComponent(try XCTUnwrap(wal.filePath))
    XCTAssertTrue(FileManager.default.fileExists(atPath: fileURL.path))
  }

  func testFlushSkipsEmptyMemoryWal() {
    let emptyWal = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      status: .miss,
      storage: .memory,
      seconds: 0,
      device: "dev1",
      deviceModel: "Omi",
      totalFrames: 0
    )
    service.setWalsForTesting([emptyWal])

    service.flushToDiskForTesting()

    XCTAssertEqual(service.wals.first?.storage, .memory)
    XCTAssertNil(service.wals.first?.filePath)
  }

  func testLoadMarksDiskWithoutFilePathCorrupted() throws {
    let wal = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      status: .miss,
      storage: .disk,
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi",
      totalFrames: 100
    )
    let metadata = WALMetadata(wals: [wal])
    let metadataURL = walDir.appendingPathComponent("wals.json")
    try JSONEncoder().encode(metadata).write(to: metadataURL)

    let reloaded = WALService(apiClient: APIClient(session: makeMockSession()))
    reloaded.setWalDirectoryForTesting(walDir)
    reloaded.reloadWalsFromDiskForTesting()

    XCTAssertEqual(reloaded.wals.first?.status, .corrupted)
  }

  func testLoadMarksMissingDiskFileCorrupted() throws {
    let fileName = "audio_dev1_opus_16000_1_fs160_1700000000.bin"
    let wal = WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      status: .miss,
      storage: .disk,
      filePath: fileName,
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi",
      totalFrames: 100
    )
    let metadata = WALMetadata(wals: [wal])
    let metadataURL = walDir.appendingPathComponent("wals.json")
    try JSONEncoder().encode(metadata).write(to: metadataURL)

    let reloaded = WALService(apiClient: APIClient(session: makeMockSession()))
    reloaded.setWalDirectoryForTesting(walDir)
    reloaded.reloadWalsFromDiskForTesting()

    XCTAssertEqual(reloaded.wals.first?.status, .corrupted)
  }
}
