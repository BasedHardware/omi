import OmiWAL
import XCTest

@testable import Omi_Computer

/// Regression coverage for the finish/stop interleaving in the BLE SD-card sync.
///
/// `finishSync` snapshots the attempt's frames/bytes, records them, and then
/// suspends on the off-main WAL write. A user-initiated `stopSync` landing in
/// that suspension used to see the same `currentWal`/frames/bytes and persist
/// them a second time, advancing `storageOffset` twice for one download and
/// racing two writes onto one WAL. The post-await generation guard could not
/// repair that: the duplicate accounting happens *inside*
/// `updateWalWithDownloadedData`, before it suspends.
///
/// These tests hold the frame write open, invoke `stopSync` while `finishSync`
/// is suspended, and assert exactly-once persistence/offset plus a correct
/// resume from the persisted offset. Reaching the stop call while the write is
/// still gated also proves the main actor stayed responsive.
@MainActor
final class StorageSyncStopDuringFinishTests: XCTestCase {

  private let walDir = FileManager.default.temporaryDirectory
    .appendingPathComponent("storage-sync-stop-finish-\(UUID().uuidString)", isDirectory: true)

  override func setUp() async throws {
    AccountCutoverControlManager.shared.resetForTesting()
    // Pending bootstrap closes upload admission: this is a local persistence test.
    XCTAssertFalse(AccountCutoverOfflineUploadAdmission.allowsUpload())

    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)
  }

  override func tearDown() async throws {
    AccountCutoverControlManager.shared.resetForTesting()
    try? FileManager.default.removeItem(at: walDir)
  }

  // MARK: - Fixtures

  /// A frame write that blocks until the test releases it, counting how many
  /// times the persistence path actually reached the writer.
  private actor GatedFrameWriter {
    private var count = 0
    private var gate: CheckedContinuation<Void, Never>?
    private var released = false
    private let startedContinuation: AsyncStream<Void>.Continuation
    nonisolated let started: AsyncStream<Void>

    init() {
      let (started, continuation) = AsyncStream<Void>.makeStream()
      self.started = started
      startedContinuation = continuation
    }

    func writes() -> Int { count }

    func write(_ data: Data, to url: URL) async throws {
      count += 1
      if count == 1 {
        startedContinuation.yield()
        // Cancellation must not open the disk gate. Later writes proceed so a
        // duplicate stop write fails assertions rather than hanging the test.
        if !released {
          await withCheckedContinuation { gate = $0 }
        }
      }
      try data.write(to: url, options: .atomic)
    }

    func release() {
      released = true
      gate?.resume()
      gate = nil
    }
  }

  @MainActor
  private final class FakeStorageTransport: StorageSyncTransport {
    var storageList: [Int32]
    private var streams: [AsyncThrowingStream<Data, Error>]
    private(set) var readOffsets: [Int] = []

    init(storageList: [Int32], streams: [AsyncThrowingStream<Data, Error>]) {
      self.storageList = storageList
      self.streams = streams
    }

    func enqueue(_ stream: AsyncThrowingStream<Data, Error>) { streams.append(stream) }

    func getStorageList() async -> [Int32] { storageList }

    func writeToStorage(fileNum: Int, command: Int, offset: Int) async -> Bool {
      if command == StorageCommand.read.rawValue {
        readOffsets.append(offset)
      }
      return true
    }

    func getStorageStream() -> AsyncThrowingStream<Data, Error> {
      guard !streams.isEmpty else {
        return AsyncThrowingStream { $0.finish() }
      }
      return streams.removeFirst()
    }
  }

  private func validOpusFrame() -> Data {
    var frame = Data(repeating: 0, count: 80)
    frame[0] = 0xb8
    return frame
  }

  /// A standard 83-byte packet: 3 header bytes followed by one 80-byte frame.
  private func standardPacket() -> Data {
    var packet = Data([0x00, 0x00, 0x00])
    packet.append(validOpusFrame())
    return packet
  }

  private func stream(_ packets: [Data]) -> AsyncThrowingStream<Data, Error> {
    AsyncThrowingStream { continuation in
      for packet in packets {
        continuation.yield(packet)
      }
      continuation.finish()
    }
  }

  private func makeWalService(writer: GatedFrameWriter) -> WALService {
    let service = WALService(
      apiClient: APIClient(session: URLSession(configuration: .ephemeral)),
      walDirectoryForTesting: walDir,
      frameWriteOverride: { data, url in
        try await writer.write(data, to: url)
      }
    )
    service.setWalsForTesting([])
    return service
  }

  private func makeDevice() -> BtDevice {
    BtDevice(id: "dev1", name: "Omi", type: .omi, rssi: -40)
  }

  // MARK: - Regression

  func testStopDuringFinishPersistsExactlyOnceAndResumes() async throws {
    try await exerciseStopDuringFinish(resumeBeforeCompletion: false)
  }

  func testOldFinishDoesNotResetSyncStartedWhileWriteIsPending() async throws {
    try await exerciseStopDuringFinish(resumeBeforeCompletion: true)
  }

  private func exerciseStopDuringFinish(resumeBeforeCompletion: Bool) async throws {
    let writer = GatedFrameWriter()
    let walService = makeWalService(writer: writer)

    // Enough bytes for both attempts to pass the minimum download threshold.
    let transport = FakeStorageTransport(
      storageList: [160_000, 0],
      streams: [stream([standardPacket(), standardPacket(), Data([0x64])])]
    )
    let service = StorageSyncService(
      walService: walService,
      transportProvider: { transport }
    )

    try await service.startSync(device: makeDevice(), codec: "opus")

    // Wait until `finishSync` has claimed the attempt and is suspended inside
    // the gated frame write.
    var started = writer.started.makeAsyncIterator()
    let startedSignal: Void? = await started.next()
    XCTAssertNotNil(startedSignal, "finishSync should have started persisting frames")

    let walId = try XCTUnwrap(walService.wals.first?.id)
    XCTAssertEqual(
      walService.getWal(id: walId)?.storageOffset, 160,
      "the first persistence records the two downloaded frames once")

    // `stopSync` clears `syncTask`; keep the in-flight finish task so the test
    // can await the gated write it is suspended on.
    let finishTask = try XCTUnwrap(service.syncTaskForTesting)

    // Stop while the write is still gated. Reaching this line proves the main
    // actor was not blocked by the in-flight write.
    await service.stopSync()

    XCTAssertEqual(
      walService.getWal(id: walId)?.storageOffset, 160,
      "stop during finish must not add the same bytes to storageOffset again")
    let writesAfterStop = await writer.writes()
    XCTAssertEqual(
      writesAfterStop, 1,
      "stop during finish must not write the same frames a second time")

    let (resumeStream, resumePackets) = AsyncThrowingStream<Data, Error>.makeStream()
    transport.storageList = [160_000, 160]
    transport.enqueue(resumeStream)
    if resumeBeforeCompletion {
      try await service.startSync(device: makeDevice(), codec: "opus")
    }

    // This continuation remains held even though stop cancelled the finish task.
    // Completing the old write must leave a newer generation's state intact.
    XCTAssertNil(walService.getWal(id: walId)?.filePath)
    await writer.release()
    await finishTask.value

    XCTAssertEqual(walService.getWal(id: walId)?.storageOffset, 160)
    let writesAfterCompletion = await writer.writes()
    XCTAssertEqual(writesAfterCompletion, 1)
    XCTAssertNotNil(walService.getWal(id: walId)?.filePath)
    XCTAssertEqual(service.isSyncing, resumeBeforeCompletion)

    if !resumeBeforeCompletion {
      try await service.startSync(device: makeDevice(), codec: "opus")
    }
    let resumeTask = try XCTUnwrap(service.syncTaskForTesting)
    resumePackets.yield(standardPacket())
    resumePackets.yield(Data([0x64]))
    resumePackets.finish()
    await resumeTask.value
    XCTAssertFalse(service.isSyncing)

    XCTAssertEqual(
      transport.readOffsets, [0, 160],
      "the resumed attempt must read from the persisted offset")
    let resumedWal = try XCTUnwrap(walService.wals.last)
    XCTAssertNotEqual(resumedWal.id, walId)
    let firstFile = try XCTUnwrap(walService.getWal(id: walId)?.filePath)
    let resumedFile = try XCTUnwrap(resumedWal.filePath)
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(firstFile)),
      WALService.encodeFrames([validOpusFrame(), validOpusFrame()]))
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(resumedFile)),
      WALService.encodeFrames([validOpusFrame()]))
    XCTAssertEqual(
      resumedWal.storageOffset, 240,
      "resume adds only the newly downloaded frame to the persisted offset")
    let writesAfterResume = await writer.writes()
    XCTAssertEqual(writesAfterResume, 2, "one write per attempt, never a duplicate")
  }
}
