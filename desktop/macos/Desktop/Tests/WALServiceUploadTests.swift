import OmiWAL
import XCTest

@testable import Omi_Computer

private actor SequencedFrameWriter {
  enum Step: Sendable {
    case fail
    case succeed
    case pauseThenSucceed
  }

  private enum WriteError: Error {
    case expectedFailure
    case unexpectedCall
  }

  private struct CallWaiter {
    let expectedCount: Int
    let continuation: CheckedContinuation<Void, Never>
  }

  private let steps: [Step]
  private var callCount = 0
  private var callWaiters: [CallWaiter] = []
  private var pausedCalls: [Int: CheckedContinuation<Void, Never>] = [:]

  init(_ steps: [Step]) {
    self.steps = steps
  }

  func write(_ request: WALService.FramePersistenceRequest) async throws -> WALService.FrameRecoveryRecord {
    callCount += 1
    let call = callCount
    resumeSatisfiedCallWaiters()

    guard steps.indices.contains(call - 1) else {
      throw WriteError.unexpectedCall
    }

    switch steps[call - 1] {
    case .fail:
      throw WriteError.expectedFailure
    case .pauseThenSucceed:
      await withCheckedContinuation { continuation in
        pausedCalls[call] = continuation
      }
    case .succeed:
      break
    }
    return try await WALService.writeFrameTransaction(request)
  }

  func waitForCall(_ expectedCount: Int) async {
    guard callCount < expectedCount else { return }
    await withCheckedContinuation { continuation in
      callWaiters.append(CallWaiter(expectedCount: expectedCount, continuation: continuation))
    }
  }

  func releaseCall(_ call: Int) {
    pausedCalls.removeValue(forKey: call)?.resume()
  }

  func recordedCallCount() -> Int {
    callCount
  }

  private func resumeSatisfiedCallWaiters() {
    let satisfied = callWaiters.filter { callCount >= $0.expectedCount }
    callWaiters.removeAll { callCount >= $0.expectedCount }
    for waiter in satisfied {
      waiter.continuation.resume()
    }
  }
}

private final class SequencedMetadataWriter: @unchecked Sendable {
  enum Step {
    case fail
    case succeed
  }

  private enum WriteError: Error {
    case expectedFailure
    case unexpectedCall
  }

  private let lock = NSLock()
  private let steps: [Step]
  private var nextStep = 0
  private var writeModes: [WALService.MetadataWriteMode] = []

  init(_ steps: [Step]) {
    self.steps = steps
  }

  func write(
    data: Data,
    file: URL,
    backup: URL,
    mode: WALService.MetadataWriteMode
  ) throws {
    lock.lock()
    guard steps.indices.contains(nextStep) else {
      lock.unlock()
      throw WriteError.unexpectedCall
    }
    let step = steps[nextStep]
    nextStep += 1
    writeModes.append(mode)
    lock.unlock()

    switch step {
    case .fail:
      throw WriteError.expectedFailure
    case .succeed:
      try WALService.writeMetadataFiles(data: data, file: file, backup: backup, mode: mode)
    }
  }

  func recordedModes() -> [WALService.MetadataWriteMode] {
    lock.lock()
    defer { lock.unlock() }
    return writeModes
  }
}

private final class MutableTimestampProvider: @unchecked Sendable {
  private let lock = NSLock()
  private var value: Int

  init(_ value: Int) {
    self.value = value
  }

  func now() -> Int {
    lock.lock()
    defer { lock.unlock() }
    return value
  }

  func set(_ value: Int) {
    lock.lock()
    self.value = value
    lock.unlock()
  }
}

@MainActor
final class WALServiceUploadTests: XCTestCase {

  private var walDir: URL!
  private var service: WALService!

  override func setUp() async throws {
    walDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("wal-upload-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: walDir, withIntermediateDirectories: true)

    DesktopDiagnosticsManager.shared.resetForTests()
    service = makeService()
  }

  override func tearDown() async throws {
    service.uploadLocalFilesHandler = nil
    DesktopDiagnosticsManager.shared.resetForTests()
    try? FileManager.default.removeItem(at: walDir)
  }

  private func makeMockSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    return URLSession(configuration: config)
  }

  private func makeService(
    frameWriter: WALService.FrameWriter? = nil,
    metadataWriter: WALService.MetadataWriter? = nil,
    resetWals: Bool = true,
    walDirectoryAvailable: Bool = true,
    timestampProvider: WALService.TimestampProvider? = nil
  ) -> WALService {
    let service = WALService(
      apiClient: APIClient(session: makeMockSession()),
      frameWriter: frameWriter,
      metadataWriter: metadataWriter,
      walDirectoryForTesting: walDir,
      walDirectoryUnavailableForTesting: !walDirectoryAvailable,
      timestampProvider: timestampProvider
    )
    if resetWals {
      service.setWalsForTesting([])
    }
    service.uploadLocalFilesHandler = nil
    return service
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

  func testCleanupRemovesOldSyncedWalButKeepsYoungAndUnsynced() throws {
    let now = 2_000_000_000
    service = makeService(timestampProvider: { now })
    let cutoff = now - 7 * 24 * 60 * 60

    // Distinct (device, timerStart) per entry so WAL ids (device_timerStart) don't
    // collide — cleanupOldWals removes by id, and a shared id would collaterally
    // remove the wrong entry. Production reserves unique timerStarts.
    func makeWal(device: String, timerStart: Int, status: WALStatus, file: String) throws -> WALEntry {
      try Data([0x01]).write(to: walDir.appendingPathComponent(file))
      return WALEntry(
        timerStart: timerStart, codec: "opus", status: status, storage: .disk,
        filePath: file, seconds: 60, device: device, deviceModel: "Omi")
    }
    let oldSynced = try makeWal(device: "dev1", timerStart: cutoff - 10, status: .synced, file: "audio_old.bin")
    let youngSynced = try makeWal(
      device: "dev1", timerStart: cutoff + 10, status: .synced, file: "audio_young.bin")
    let oldMiss = try makeWal(device: "dev2", timerStart: cutoff - 10, status: .miss, file: "audio_miss.bin")
    service.setWalsForTesting([oldSynced, youngSynced, oldMiss])
    service.saveWals()

    service.cleanupOldWals()
    service.waitForWalMetadataWritesForTesting()

    let fm = FileManager.default
    XCTAssertFalse(
      fm.fileExists(atPath: walDir.appendingPathComponent("audio_old.bin").path),
      "an old synced WAL's audio file must be reclaimed")
    XCTAssertTrue(fm.fileExists(atPath: walDir.appendingPathComponent("audio_young.bin").path))
    XCTAssertTrue(
      fm.fileExists(atPath: walDir.appendingPathComponent("audio_miss.bin").path),
      "an unsynced (.miss) WAL must never be deleted, even when old")

    XCTAssertEqual(Set(service.wals.map { $0.id }), [youngSynced.id, oldMiss.id])
    let metadataURL = walDir.appendingPathComponent("wals.json")
    let persisted = try JSONDecoder().decode(WALMetadata.self, from: Data(contentsOf: metadataURL))
    XCTAssertEqual(
      Set(persisted.wals.map { $0.id }), [youngSynced.id, oldMiss.id],
      "persisted metadata must be pruned to the survivors")
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

  func testWalMetadataPersistsLatestQueuedSnapshot() throws {
    var wal = try seedWalOnDisk()
    service.saveWals()

    wal.status = .synced
    service.setWalsForTesting([wal])
    service.saveWals()
    service.waitForWalMetadataWritesForTesting()

    let metadataURL = walDir.appendingPathComponent("wals.json")
    let metadata = try JSONDecoder().decode(WALMetadata.self, from: Data(contentsOf: metadataURL))
    XCTAssertEqual(metadata.wals.first?.status, .synced)
  }

  func testDegradedDirectoryRetainsCurrentFramesAndRecordsHealth() throws {
    service = makeService(walDirectoryAvailable: false)
    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(Data([0x01, 0x02]))

    service.createWalFromCurrentFramesForTesting()

    XCTAssertEqual(service.currentFrameCountForTesting, 1)
    XCTAssertEqual(service.persistenceState, .degraded(reason: "wal_directory_unavailable"))
    XCTAssertNotNil(service.errorMessage)

    let snapshot = try latestHealthSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
    XCTAssertEqual(snapshot["area"] as? String, "wal_persistence")
    XCTAssertEqual(snapshot["recovery_action"] as? String, "retain_frames")
  }

  func testStopRecordingRetainsFramesWhenPersistFails() throws {
    service = makeService(walDirectoryAvailable: false)
    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(Data([0x0A, 0x0B]))

    service.stopRecording()

    XCTAssertEqual(service.currentFrameCountForTesting, 1)
    XCTAssertEqual(service.persistenceState, .degraded(reason: "wal_directory_unavailable"))
  }

  func testStartRecordingRetainsFramesWhenRetryFails() throws {
    service = makeService(walDirectoryAvailable: false)
    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(Data([0x0A, 0x0B]))

    // stopRecording retains frames because the WAL directory is nil.
    service.stopRecording()
    XCTAssertEqual(service.currentFrameCountForTesting, 1)

    // startRecording attempts a best-effort flush, which also fails. The
    // retained frames must survive so they can be retried later.
    service.startRecording(device: "dev2", codec: "opus")
    XCTAssertEqual(service.currentFrameCountForTesting, 1)
  }

  func testFailedNewFrameWriteLeavesRecordingStateUnchanged() async throws {
    let writer = SequencedFrameWriter([.fail])
    let fixedTime = 1_700_000_000
    service = makeService(
      frameWriter: { request in
        try await writer.write(request)
      },
      timestampProvider: { fixedTime }
    )
    let frame = Data([0x10, 0x11])

    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(frame, synced: true)
    let recordingStartTime = try XCTUnwrap(service.recordingStartTimeForTesting)

    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    XCTAssertTrue(service.wals.isEmpty)
    XCTAssertEqual(service.currentFramesForTesting, [frame])
    XCTAssertEqual(service.currentFramesSyncedForTesting, [true])
    XCTAssertEqual(service.recordingStartTimeForTesting, recordingStartTime)
    let writerCallCount = await writer.recordedCallCount()
    XCTAssertEqual(writerCallCount, 1)
  }

  func testFailedNewFrameWriteRetriesThenCommitsExactlyOnce() async throws {
    let writer = SequencedFrameWriter([.fail, .succeed])
    service = makeService { request in
      try await writer.write(request)
    }
    let frames = [Data([0x20]), Data([0x21])]

    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(frames[0], synced: false)
    service.addFrame(frames[1], synced: true)

    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()
    XCTAssertTrue(service.wals.isEmpty)
    XCTAssertEqual(service.currentFramesForTesting, frames)
    XCTAssertEqual(service.currentFramesSyncedForTesting, [false, true])
    XCTAssertNotNil(service.errorMessage)

    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    let wal = try XCTUnwrap(service.wals.first)
    let filePath = try XCTUnwrap(wal.filePath)
    XCTAssertEqual(service.wals.count, 1)
    XCTAssertEqual(wal.totalFrames, frames.count)
    XCTAssertEqual(wal.storage, .disk)
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(filePath)),
      WALService.encodeFrames(frames)
    )
    XCTAssertTrue(service.currentFramesForTesting.isEmpty)
    XCTAssertTrue(service.currentFramesSyncedForTesting.isEmpty)
    XCTAssertEqual(service.persistenceState, .ready)
    XCTAssertNil(service.errorMessage)
    let writerCallCount = await writer.recordedCallCount()
    XCTAssertEqual(writerCallCount, 2)
  }

  func testFramesArrivingDuringWriteRemainBufferedWithMatchingSyncFlags() async throws {
    let writer = SequencedFrameWriter([.pauseThenSucceed])
    service = makeService { request in
      try await writer.write(request)
    }
    let writtenFrame = Data([0x40])
    let arrivingFrames = [Data([0x41]), Data([0x42])]

    service.startRecording(device: "dev1", codec: "opus")
    service.addFrame(writtenFrame, synced: false)
    service.createWalFromCurrentFramesForTesting()
    await writer.waitForCall(1)

    service.addFrame(arrivingFrames[0], synced: true)
    service.addFrame(arrivingFrames[1], synced: false)
    XCTAssertTrue(service.wals.isEmpty)
    XCTAssertEqual(service.currentFramesForTesting, [writtenFrame] + arrivingFrames)

    await writer.releaseCall(1)
    await service.waitForFrameWriteForTesting()

    let wal = try XCTUnwrap(service.wals.first)
    let filePath = try XCTUnwrap(wal.filePath)
    XCTAssertEqual(wal.totalFrames, 1)
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(filePath)),
      WALService.encodeFrames([writtenFrame])
    )
    XCTAssertEqual(service.currentFramesForTesting, arrivingFrames)
    XCTAssertEqual(service.currentFramesSyncedForTesting, [true, false])
  }

  func testFailedDeviceABatchCannotMixWithDeviceBFrames() async throws {
    let writer = SequencedFrameWriter([.fail, .pauseThenSucceed, .succeed])
    let fixedTime = 1_700_000_000
    service = makeService(
      frameWriter: { request in
        try await writer.write(request)
      },
      timestampProvider: { fixedTime }
    )
    let frameA = Data([0x50])
    let frameB = Data([0x51, 0x52])

    service.startRecording(device: "device-a", codec: "opus")
    let startA = try XCTUnwrap(service.activeStartTimeForTesting)
    service.addFrame(frameA, synced: false)
    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()
    XCTAssertEqual(service.currentFramesForTesting, [frameA])

    service.startRecording(device: "device-b", codec: "opus_fs320")
    let startB = try XCTUnwrap(service.activeStartTimeForTesting)
    await writer.waitForCall(2)
    service.addFrame(frameB, synced: true)
    XCTAssertEqual(service.activeDeviceForTesting, "device-b")
    XCTAssertEqual(service.activeCodecForTesting, "opus_fs320")
    XCTAssertEqual(service.currentFramesForTesting, [frameA, frameB])

    await writer.releaseCall(2)
    await service.waitForFrameWriteForTesting()
    XCTAssertEqual(service.currentFramesForTesting, [frameB])

    service.stopRecording()
    await service.waitForFrameWriteForTesting()

    let walA = try XCTUnwrap(service.wals.first(where: { $0.device == "device-a" }))
    let walB = try XCTUnwrap(service.wals.first(where: { $0.device == "device-b" }))
    XCTAssertEqual(walA.codec, "opus")
    XCTAssertEqual(walA.timerStart, startA)
    XCTAssertEqual(walA.totalFrames, 1)
    XCTAssertEqual(walB.codec, "opus_fs320")
    XCTAssertEqual(walB.timerStart, startB)
    XCTAssertEqual(walB.totalFrames, 1)
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(try XCTUnwrap(walA.filePath))),
      WALService.encodeFrames([frameA])
    )
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(try XCTUnwrap(walB.filePath))),
      WALService.encodeFrames([frameB])
    )
  }

  func testSameDeviceCodecSwitchInOneSecondUsesSeparateWalIdentitiesAndFiles() async throws {
    let fixedTime = 1_700_000_000
    service = makeService(timestampProvider: { fixedTime })
    let opusFrame = Data([0x55])
    let fs320Frame = Data([0x56, 0x57])

    service.startRecording(device: "same-device", codec: "opus")
    service.addFrame(opusFrame, synced: false)
    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    service.startRecording(device: "same-device", codec: "opus_fs320")
    service.addFrame(fs320Frame, synced: true)
    service.stopRecording()
    await service.waitForFrameWriteForTesting()

    let deviceWals = service.wals.filter { $0.device == "same-device" }
      .sorted { $0.timerStart < $1.timerStart }
    XCTAssertEqual(deviceWals.count, 2)
    let opusWal = try XCTUnwrap(deviceWals.first)
    let fs320Wal = try XCTUnwrap(deviceWals.last)
    XCTAssertEqual(opusWal.timerStart, fixedTime)
    XCTAssertEqual(fs320Wal.timerStart, fixedTime + 1)
    XCTAssertNotEqual(opusWal.id, fs320Wal.id)
    XCTAssertEqual(opusWal.codec, "opus")
    XCTAssertEqual(fs320Wal.codec, "opus_fs320")
    XCTAssertNotEqual(opusWal.filePath, fs320Wal.filePath)
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(try XCTUnwrap(opusWal.filePath))),
      WALService.encodeFrames([opusFrame])
    )
    XCTAssertEqual(
      try Data(contentsOf: walDir.appendingPathComponent(try XCTUnwrap(fs320Wal.filePath))),
      WALService.encodeFrames([fs320Frame])
    )
  }

  func testFreezePreservesCaptureStartWhenClockAdvances() async throws {
    let captureStart = 1_700_000_000
    let clock = MutableTimestampProvider(captureStart)
    service = makeService(timestampProvider: { clock.now() })

    service.startRecording(device: "device-a", codec: "opus")
    service.addFrame(Data([0x58]), synced: false)
    clock.set(captureStart + 100)
    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    XCTAssertEqual(service.wals.first?.timerStart, captureStart)
  }

  func testPendingLocalBatchReservesItsSecondAgainstSdCardWal() async throws {
    let fixedTime = 1_700_000_000
    let writer = SequencedFrameWriter([.pauseThenSucceed])
    service = makeService(
      frameWriter: { request in
        try await writer.write(request)
      },
      timestampProvider: { fixedTime }
    )

    service.startRecording(device: "same-device", codec: "opus")
    service.addFrame(Data([0x59]), synced: false)
    service.createWalFromCurrentFramesForTesting()
    await writer.waitForCall(1)

    let sdWal = service.createSdCardWal(
      device: "same-device",
      deviceModel: "Omi",
      codec: "opus",
      totalBytes: 80,
      currentOffset: 0
    )
    XCTAssertEqual(sdWal.timerStart, fixedTime + 1)

    await writer.releaseCall(1)
    await service.waitForFrameWriteForTesting()

    let localWal = try XCTUnwrap(service.wals.first(where: { $0.storage == .disk }))
    XCTAssertEqual(localWal.timerStart, fixedTime)
    XCTAssertNotEqual(localWal.id, sdWal.id)
    XCTAssertEqual(Set(service.wals.map(\.id)).count, 2)
  }

  func testTwoSdCardWalsAtFixedClockReserveUniqueIdentities() {
    let fixedTime = 1_700_000_000
    service = makeService(timestampProvider: { fixedTime })

    let first = service.createSdCardWal(
      device: "same-device",
      deviceModel: "Omi",
      codec: "opus",
      totalBytes: 80,
      currentOffset: 0
    )
    let second = service.createSdCardWal(
      device: "same-device",
      deviceModel: "Omi",
      codec: "opus",
      totalBytes: 80,
      currentOffset: 0
    )

    XCTAssertEqual(first.timerStart, fixedTime)
    XCTAssertEqual(second.timerStart, fixedTime + 1)
    XCTAssertNotEqual(first.id, second.id)
    XCTAssertEqual(Set(service.wals.map(\.id)).count, 2)
    service.waitForWalMetadataWritesForTesting()
  }

  func testMetadataFailureRetainsBatchAndRestartRecoversAudioTransaction() async throws {
    let metadataWriter = SequencedMetadataWriter([.fail])
    service = makeService(metadataWriter: { data, file, backup, mode in
      try metadataWriter.write(data: data, file: file, backup: backup, mode: mode)
    })
    let frame = Data([0x60, 0x61])

    service.startRecording(device: "device-a", codec: "opus")
    service.addFrame(frame, synced: false)
    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    let stagedWal = try XCTUnwrap(service.wals.first)
    let stagedFile = walDir.appendingPathComponent(try XCTUnwrap(stagedWal.filePath))
    XCTAssertEqual(service.pendingFrameBatchCountForTesting, 1)
    XCTAssertEqual(service.currentFramesForTesting, [frame])
    XCTAssertEqual(try Data(contentsOf: stagedFile), WALService.encodeFrames([frame]))
    XCTAssertEqual((try recoveryFiles()).count, 1)

    let restarted = makeService(resetWals: false)
    let recoveredWal = try XCTUnwrap(restarted.wals.first(where: { $0.id == stagedWal.id }))
    XCTAssertEqual(recoveredWal.totalFrames, 1)
    XCTAssertEqual(recoveredWal.storage, .disk)
    XCTAssertEqual(try Data(contentsOf: stagedFile), WALService.encodeFrames([frame]))
    XCTAssertTrue(try recoveryFiles().isEmpty)
  }

  func testMetadataFailureRetryCommitsWithoutRewritingAudioAndSurvivesRestart() async throws {
    let frameWriter = SequencedFrameWriter([.succeed])
    let metadataWriter = SequencedMetadataWriter([.fail, .succeed])
    service = makeService(
      frameWriter: { request in
        try await frameWriter.write(request)
      },
      metadataWriter: { data, file, backup, mode in
        try metadataWriter.write(data: data, file: file, backup: backup, mode: mode)
      }
    )
    let frame = Data([0x70])

    service.startRecording(device: "device-a", codec: "opus")
    service.addFrame(frame, synced: true)
    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()
    XCTAssertEqual(service.pendingFrameBatchCountForTesting, 1)
    XCTAssertEqual(service.currentFramesForTesting, [frame])

    service.createWalFromCurrentFramesForTesting()
    await service.waitForFrameWriteForTesting()

    XCTAssertEqual(service.pendingFrameBatchCountForTesting, 0)
    XCTAssertTrue(service.currentFramesForTesting.isEmpty)
    XCTAssertTrue(try recoveryFiles().isEmpty)
    let frameWriterCallCount = await frameWriter.recordedCallCount()
    XCTAssertEqual(frameWriterCallCount, 1)

    let metadataURL = walDir.appendingPathComponent("wals.json")
    let metadata = try JSONDecoder().decode(WALMetadata.self, from: Data(contentsOf: metadataURL))
    let persistedWal = try XCTUnwrap(metadata.wals.first)
    let restarted = makeService(resetWals: false)
    XCTAssertEqual(restarted.wals.first?.id, persistedWal.id)
    XCTAssertEqual(restarted.wals.first?.totalFrames, 1)
  }

  func testCorruptPrimaryPreservesValidBackupWhileSidecarRecoveryWriteFails() async throws {
    let baseWal = WALEntry(
      timerStart: 1_700_000_100,
      codec: "opus",
      status: .miss,
      storage: .disk,
      filePath: "base.bin",
      seconds: 1,
      device: "base-device",
      deviceModel: "Omi",
      totalFrames: 1
    )
    let backupURL = walDir.appendingPathComponent("wals_backup.json")
    let primaryURL = walDir.appendingPathComponent("wals.json")
    let validBackupData = try JSONEncoder().encode(WALMetadata(wals: [baseWal]))
    try validBackupData.write(to: backupURL, options: .atomic)
    try Data("corrupt-primary".utf8).write(to: primaryURL, options: .atomic)

    var recoveredWal = WALEntry(
      timerStart: 1_700_000_200,
      codec: "opus_fs320",
      status: .miss,
      storage: .disk,
      seconds: 1,
      device: "recovered-device",
      deviceModel: "Omi",
      totalFrames: 1
    )
    recoveredWal.filePath = recoveredWal.generateFileName()
    let recoveredFileName = try XCTUnwrap(recoveredWal.filePath)
    let recoveryRequest = WALService.FramePersistenceRequest(
      fileURL: walDir.appendingPathComponent(recoveredFileName),
      recoveryURL: walDir.appendingPathComponent(recoveredFileName + ".wal-pending.json"),
      wal: recoveredWal,
      frames: [Data([0x71])]
    )
    _ = try await WALService.writeFrameTransaction(recoveryRequest)

    let failingWriter = SequencedMetadataWriter([.fail, .fail])
    service = makeService(
      metadataWriter: { data, file, backup, mode in
        try failingWriter.write(data: data, file: file, backup: backup, mode: mode)
      },
      resetWals: false
    )

    XCTAssertEqual(Set(service.wals.map(\.id)), Set([baseWal.id, recoveredWal.id]))
    XCTAssertEqual((try recoveryFiles()).count, 1)
    let backupAfterFailures = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: backupURL)
    )
    XCTAssertEqual(backupAfterFailures.wals.map(\.id), [baseWal.id])
    XCTAssertEqual(failingWriter.recordedModes(), [.preserveBackup, .preserveBackup])

    let restarted = makeService(resetWals: false)
    XCTAssertEqual(Set(restarted.wals.map(\.id)), Set([baseWal.id, recoveredWal.id]))
    XCTAssertTrue(try recoveryFiles().isEmpty)
    let backupAfterRecovery = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: backupURL)
    )
    XCTAssertEqual(backupAfterRecovery.wals.map(\.id), [baseWal.id])
    let restoredPrimary = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: primaryURL)
    )
    XCTAssertEqual(Set(restoredPrimary.wals.map(\.id)), Set([baseWal.id, recoveredWal.id]))
  }

  func testSuccessfulBackupRestoreAllowsNextNormalSaveToAdvanceBackup() throws {
    var baseWal = WALEntry(
      timerStart: 1_700_000_300,
      codec: "opus",
      status: .miss,
      storage: .disk,
      filePath: "base.bin",
      seconds: 1,
      device: "base-device",
      deviceModel: "Omi",
      totalFrames: 1
    )
    let backupURL = walDir.appendingPathComponent("wals_backup.json")
    let primaryURL = walDir.appendingPathComponent("wals.json")
    var backupMetadata = WALMetadata(wals: [baseWal])
    backupMetadata.timestamp = 123
    try JSONEncoder().encode(backupMetadata).write(to: backupURL, options: .atomic)
    try Data("corrupt-primary".utf8).write(to: primaryURL, options: .atomic)

    let metadataWriter = SequencedMetadataWriter([.succeed, .succeed])
    service = makeService(
      metadataWriter: { data, file, backup, mode in
        try metadataWriter.write(data: data, file: file, backup: backup, mode: mode)
      },
      resetWals: false
    )
    let restoredPrimary = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: primaryURL)
    )
    XCTAssertEqual(metadataWriter.recordedModes(), [.preserveBackup])

    baseWal.status = .synced
    service.setWalsForTesting([baseWal])
    service.saveWals()
    service.waitForWalMetadataWritesForTesting()

    XCTAssertEqual(metadataWriter.recordedModes(), [.preserveBackup, .rotateBackup])
    let advancedBackup = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: backupURL)
    )
    XCTAssertEqual(advancedBackup.timestamp, restoredPrimary.timestamp)
    XCTAssertNotEqual(advancedBackup.timestamp, 123)
    XCTAssertEqual(advancedBackup.wals.first?.status, .miss)
    let updatedPrimary = try JSONDecoder().decode(
      WALMetadata.self,
      from: Data(contentsOf: primaryURL)
    )
    XCTAssertEqual(updatedPrimary.wals.first?.status, .synced)
  }

  func testUploadFailureRecordsHealthSnapshot() async throws {
    let wal = try seedWalOnDisk()
    service.uploadLocalFilesHandler = { _ in
      throw APIError.syncUploadRejected(reason: "Server error")
    }

    do {
      try await service.uploadWalToCloudForTesting(wal)
      XCTFail("expected upload failure")
    } catch {
      // expected
    }

    let snapshot = try latestHealthSnapshot()
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
    XCTAssertEqual(snapshot["area"] as? String, "wal_upload")
    XCTAssertEqual(snapshot["recovery_action"] as? String, "leave_pending")
  }

  private func latestHealthSnapshot() throws -> [String: Any] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return try XCTUnwrap(snapshots.last)
  }

  private func recoveryFiles() throws -> [URL] {
    try FileManager.default.contentsOfDirectory(
      at: walDir,
      includingPropertiesForKeys: nil
    ).filter { $0.lastPathComponent.hasSuffix(".wal-pending.json") }
  }
}
