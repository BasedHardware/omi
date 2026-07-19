import Combine
import CryptoKit
import Foundation
import OmiSupport
import OmiWAL
import os.log

// MARK: - WAL Persistence State

enum WALPersistenceState: Equatable {
  case ready
  case degraded(reason: String)
}

private final class WALMetadataWriteState: @unchecked Sendable {
  private let lock = NSLock()
  var latestPersistedRevision = 0
  private var preserveValidatedBackup = false

  func markValidatedBackupLoaded() {
    lock.lock()
    preserveValidatedBackup = true
    lock.unlock()
  }

  func writeMode() -> WALService.MetadataWriteMode {
    lock.lock()
    defer { lock.unlock() }
    return preserveValidatedBackup ? .preserveBackup : .rotateBackup
  }

  func markPrimaryWriteSucceeded() {
    lock.lock()
    preserveValidatedBackup = false
    lock.unlock()
  }
}

// MARK: - WAL Service

/// Main coordinator for Write-Ahead Log sync operations
/// Manages local WAL storage and coordinates sync with device and cloud
/// Ported from: omi/app/lib/services/wals/wal_service.dart
@MainActor
final class WALService: ObservableObject {

  struct FrameRecoveryRecord: Codable, @unchecked Sendable {
    let wal: WALEntry
    let fileName: String
    let expectedAudioBytes: Int
    let expectedAudioSHA256: String
  }

  struct FramePersistenceRequest: @unchecked Sendable {
    let fileURL: URL
    let recoveryURL: URL
    let wal: WALEntry
    let frames: [Data]
  }

  enum MetadataWriteMode: Equatable, Sendable {
    case rotateBackup
    case preserveBackup
  }

  typealias FrameWriter = @Sendable (FramePersistenceRequest) async throws -> FrameRecoveryRecord
  typealias MetadataWriter =
    @Sendable (
      _ data: Data,
      _ file: URL,
      _ backup: URL,
      _ mode: MetadataWriteMode
    ) throws -> Void
  typealias TimestampProvider = @Sendable () -> Int

  private struct ActiveFrameBuffer {
    let device: String
    let codec: String
    var startTime: Int
    var frames: [Data] = []
    var syncFlags: [Bool] = []
  }

  private struct PendingFrameBatch {
    let id: UUID
    let device: String
    let codec: String
    let startTime: Int
    let frames: [Data]
    let syncFlags: [Bool]
    var recoveryRecord: FrameRecoveryRecord?
    var recoveryURL: URL?
  }

  private struct MetadataWriteRequest: @unchecked Sendable {
    let revision: Int
    let data: Data
    let file: URL
    let backup: URL
    let mode: MetadataWriteMode
  }

  // MARK: - Singleton

  static let shared = WALService()

  // MARK: - Published Properties

  /// All WAL entries
  @Published private(set) var wals: [WALEntry] = []

  /// WALs pending upload to cloud
  @Published private(set) var pendingWals: [WALEntry] = []

  /// Whether sync is currently in progress
  @Published private(set) var isSyncing = false

  /// Current sync progress
  @Published private(set) var syncProgress: SyncProgress?

  /// Last error message
  @Published var errorMessage: String?

  /// Local WAL directory health — `.degraded` when frames cannot be persisted safely.
  @Published private(set) var persistenceState: WALPersistenceState = .ready

  // MARK: - Constants

  /// Chunk duration in seconds (create WAL every N seconds)
  static let chunkSizeInSeconds = 60

  /// Flush interval in seconds (write in-memory WALs to disk)
  static let flushIntervalInSeconds = 90

  /// Delay before processing new frames
  static let newFrameSyncDelaySeconds = 15

  /// Minimum frames to trigger a WAL creation (10 seconds worth)
  static let lossesThresholdFrames = 10 * 100  // 10 seconds at 100 fps

  /// SD card chunk duration
  static let sdcardChunkSizeSeconds = 60

  // MARK: - Properties

  private let logger = Logger(subsystem: "me.omi.desktop", category: "WALService")
  private let fileManager = FileManager.default
  private let apiClient: APIClient
  private let reconciler: WALSyncReconciler
  private let frameWriter: FrameWriter
  private let metadataWriter: MetadataWriter
  private let timestampProvider: TimestampProvider
  private let walMetadataWriteQueue = DispatchQueue(label: "me.omi.desktop.wal.metadata.write")
  private let walMetadataWriteState = WALMetadataWriteState()
  private var walMetadataRevision = 0
  private var frameWriteTask: Task<Void, Never>?

  /// Test seam — when set, bypasses `APIClient.uploadLocalFilesV2`.
  var uploadLocalFilesHandler: ((URL) async throws -> UploadLocalFilesResult)?

  func setWalsForTesting(_ entries: [WALEntry]) {
    wals = entries
  }

  func uploadWalToCloudForTesting(_ wal: WALEntry) async throws {
    try await uploadWalToCloud(wal)
  }

  func flushToDiskForTesting() {
    flushToDisk()
  }

  func waitForWalMetadataWritesForTesting() {
    walMetadataWriteQueue.sync {}
  }

  func createWalFromCurrentFramesForTesting() {
    createWalFromCurrentFrames()
  }

  func waitForFrameWriteForTesting() async {
    while let task = frameWriteTask {
      await task.value
    }
  }

  var currentFrameCountForTesting: Int {
    currentFramesForTesting.count
  }

  var currentFramesForTesting: [Data] {
    pendingFrameBatches.flatMap(\.frames) + (activeFrameBuffer?.frames ?? [])
  }

  var currentFramesSyncedForTesting: [Bool] {
    pendingFrameBatches.flatMap(\.syncFlags) + (activeFrameBuffer?.syncFlags ?? [])
  }

  var recordingStartTimeForTesting: Int? {
    pendingFrameBatches.first?.startTime ?? activeFrameBuffer?.startTime
  }

  var pendingFrameBatchCountForTesting: Int {
    pendingFrameBatches.count
  }

  var activeDeviceForTesting: String? {
    activeFrameBuffer?.device
  }

  var activeCodecForTesting: String? {
    activeFrameBuffer?.codec
  }

  var activeStartTimeForTesting: Int? {
    activeFrameBuffer?.startTime
  }

  private var walDirectory: URL?
  private var directoryRecreateAttempts = 0
  private let maxDirectoryRecreateAttempts = 3
  private var flushTimer: Timer?
  private var chunkTimer: Timer?

  // Active capture and frozen persistence batches have separate immutable
  // identities so a failed device-A write can never absorb device-B frames.
  private var activeFrameBuffer: ActiveFrameBuffer?
  private var pendingFrameBatches: [PendingFrameBatch] = []

  // MARK: - Initialization

  init(
    apiClient: APIClient = .shared,
    reconciler: WALSyncReconciler? = nil,
    frameWriter: FrameWriter? = nil,
    metadataWriter: MetadataWriter? = nil,
    walDirectoryForTesting: URL? = nil,
    walDirectoryUnavailableForTesting: Bool = false,
    timestampProvider: TimestampProvider? = nil
  ) {
    self.apiClient = apiClient
    self.reconciler = reconciler ?? .shared
    self.frameWriter =
      frameWriter ?? { request in
        try await Self.writeFrameTransaction(request)
      }
    self.metadataWriter =
      metadataWriter ?? { data, file, backup, mode in
        try Self.writeMetadataFiles(data: data, file: file, backup: backup, mode: mode)
      }
    self.timestampProvider = timestampProvider ?? { Int(Date().timeIntervalSince1970) }
    if walDirectoryUnavailableForTesting {
      walDirectory = nil
    } else if let walDirectoryForTesting {
      attemptWalDirectorySetup(at: walDirectoryForTesting)
    } else {
      setupWalDirectory()
    }
    loadWals()
  }

  // MARK: - Directory Setup

  private func setupWalDirectory() {
    let walDir = DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("wals", isDirectory: true)
    attemptWalDirectorySetup(at: walDir)
  }

  private func attemptWalDirectorySetup(at walDir: URL) {
    do {
      try fileManager.createDirectory(at: walDir, withIntermediateDirectories: true)
      walDirectory = walDir
      persistenceState = .ready
      directoryRecreateAttempts = 0
      logger.info("WAL directory: \(walDir.path)")
    } catch {
      directoryRecreateAttempts += 1
      let reason = error.localizedDescription
      persistenceState = .degraded(reason: reason)
      errorMessage = "Audio backup storage unavailable. Recording continues locally in memory."
      log(
        "WALService: failed to create WAL directory "
          + "(failure_class=wal_persistence_degraded recovery_action=recreate_directory "
          + "recovery_result=degraded attempt=\(directoryRecreateAttempts)/\(maxDirectoryRecreateAttempts)): "
          + reason)
      logError("WALService: failed to create WAL directory", error: error)
      DesktopDiagnosticsManager.shared.recordWalPersistenceDegraded(
        reason: reason,
        recoveryAction: "recreate_directory",
        recoveryResult: directoryRecreateAttempts < maxDirectoryRecreateAttempts ? "retrying" : "exhausted"
      )
      guard directoryRecreateAttempts < maxDirectoryRecreateAttempts else { return }
      DispatchQueue.main.asyncAfter(deadline: .now() + Double(directoryRecreateAttempts)) { [weak self] in
        self?.attemptWalDirectorySetup(at: walDir)
      }
    }
  }

  // MARK: - WAL Persistence

  private var walMetadataFile: URL? {
    walDirectory?.appendingPathComponent("wals.json")
  }

  private var walBackupFile: URL? {
    walDirectory?.appendingPathComponent("wals_backup.json")
  }

  /// Load WALs from disk
  private func loadWals() {
    guard let file = walMetadataFile else { return }
    guard fileManager.fileExists(atPath: file.path) else {
      logger.info("No existing WAL metadata found")
      if loadFromBackup() {
        restorePrimaryFromValidatedBackup()
      }
      recoverFrameTransactions()
      return
    }

    do {
      let data = try Data(contentsOf: file)
      let metadata = try JSONDecoder().decode(WALMetadata.self, from: data)
      wals = metadata.wals
      updatePendingWals()
      logger.info("Loaded \(self.wals.count) WALs from disk")
    } catch {
      logger.error("Failed to load WALs: \(error.localizedDescription)")
      if loadFromBackup() {
        restorePrimaryFromValidatedBackup()
      }
    }
    recoverFrameTransactions()
  }

  @discardableResult
  private func loadFromBackup() -> Bool {
    guard let backup = walBackupFile, fileManager.fileExists(atPath: backup.path) else {
      return false
    }

    do {
      let data = try Data(contentsOf: backup)
      let metadata = try JSONDecoder().decode(WALMetadata.self, from: data)
      wals = metadata.wals
      walMetadataWriteState.markValidatedBackupLoaded()
      updatePendingWals()
      logger.info("Loaded \(self.wals.count) WALs from backup")
      return true
    } catch {
      logger.error("Failed to load WALs from backup: \(error.localizedDescription)")
      return false
    }
  }

  private func restorePrimaryFromValidatedBackup() {
    guard let file = walMetadataFile, let backup = walBackupFile else { return }
    do {
      walMetadataRevision += 1
      let data = try JSONEncoder().encode(WALMetadata(wals: wals))
      try metadataWriter(data, file, backup, .preserveBackup)
      walMetadataWriteState.latestPersistedRevision = walMetadataRevision
      walMetadataWriteState.markPrimaryWriteSucceeded()
    } catch {
      logger.error("Failed to restore WAL metadata primary: \(error.localizedDescription)")
    }
  }

  /// Save WALs to disk with backup (file I/O runs on background thread)
  func saveWals() {
    do {
      let request = try makeMetadataWriteRequest(for: wals)
      enqueueMetadataWrite(request) { result in
        if case .failure(let error) = result {
          log("WALService: Failed to save WALs: \(error.localizedDescription)")
        }
      }
      logger.debug("Saved \(self.wals.count) WALs to disk")
    } catch {
      logger.error("Failed to encode WALs: \(error.localizedDescription)")
    }
  }

  private func makeMetadataWriteRequest(for entries: [WALEntry]) throws -> MetadataWriteRequest {
    guard let file = walMetadataFile, let backup = walBackupFile else {
      throw WALError.fileNotFound
    }
    walMetadataRevision += 1
    return MetadataWriteRequest(
      revision: walMetadataRevision,
      data: try JSONEncoder().encode(WALMetadata(wals: entries)),
      file: file,
      backup: backup,
      mode: walMetadataWriteState.writeMode()
    )
  }

  private func enqueueMetadataWrite(
    _ request: MetadataWriteRequest,
    completion: @escaping @Sendable (Result<Void, Error>) -> Void
  ) {
    let writer = metadataWriter
    let state = walMetadataWriteState
    walMetadataWriteQueue.async {
      guard request.revision >= state.latestPersistedRevision else {
        completion(.success(()))
        return
      }
      do {
        try writer(request.data, request.file, request.backup, request.mode)
        state.latestPersistedRevision = request.revision
        state.markPrimaryWriteSucceeded()
        completion(.success(()))
      } catch {
        completion(.failure(error))
      }
    }
  }

  private func persistCurrentWalMetadata() async throws {
    let request = try makeMetadataWriteRequest(for: wals)
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      enqueueMetadataWrite(request) { result in
        continuation.resume(with: result)
      }
    }
  }

  nonisolated static func writeMetadataFiles(
    data: Data,
    file: URL,
    backup: URL,
    mode: MetadataWriteMode
  ) throws {
    if mode == .rotateBackup, FileManager.default.fileExists(atPath: file.path) {
      try? FileManager.default.removeItem(at: backup)
      try FileManager.default.copyItem(at: file, to: backup)
    }
    try data.write(to: file, options: .atomic)
  }

  private func recoverFrameTransactions() {
    guard let walDirectory,
      let recoveryFiles = try? fileManager.contentsOfDirectory(
        at: walDirectory,
        includingPropertiesForKeys: [.fileSizeKey],
        options: [.skipsHiddenFiles]
      )
    else { return }

    let candidates = recoveryFiles.filter { $0.lastPathComponent.hasSuffix(".wal-pending.json") }
    var recoveredFiles: [URL] = []
    for recoveryURL in candidates {
      do {
        let record = try JSONDecoder().decode(
          FrameRecoveryRecord.self,
          from: Data(contentsOf: recoveryURL)
        )
        let audioURL = walDirectory.appendingPathComponent(record.fileName)
        let audioData = try Data(contentsOf: audioURL)
        guard audioData.count == record.expectedAudioBytes,
          Self.sha256Hex(audioData) == record.expectedAudioSHA256
        else {
          try? fileManager.removeItem(at: recoveryURL)
          continue
        }
        mergeRecoveredWal(record.wal)
        recoveredFiles.append(recoveryURL)
      } catch {
        logger.warning("Ignoring incomplete WAL recovery record: \(recoveryURL.lastPathComponent)")
        try? fileManager.removeItem(at: recoveryURL)
      }
    }

    guard !recoveredFiles.isEmpty,
      let file = walMetadataFile,
      let backup = walBackupFile
    else { return }
    updatePendingWals()
    do {
      walMetadataRevision += 1
      let data = try JSONEncoder().encode(WALMetadata(wals: wals))
      let mode = walMetadataWriteState.writeMode()
      try metadataWriter(data, file, backup, mode)
      walMetadataWriteState.latestPersistedRevision = walMetadataRevision
      walMetadataWriteState.markPrimaryWriteSucceeded()
      for recoveryURL in recoveredFiles {
        try? fileManager.removeItem(at: recoveryURL)
      }
    } catch {
      logger.error("Failed to commit recovered WAL metadata: \(error.localizedDescription)")
    }
  }

  private func mergeRecoveredWal(_ recovered: WALEntry) {
    guard let index = wals.firstIndex(where: { $0.id == recovered.id }) else {
      wals.append(recovered)
      return
    }
    var merged = wals[index]
    if recovered.totalFrames > merged.totalFrames {
      merged.totalFrames = recovered.totalFrames
      merged.status = .miss
    }
    merged.storage = .disk
    merged.filePath = recovered.filePath
    wals[index] = merged
  }

  private func updatePendingWals() {
    // `.uploaded` stays pending (in-flight) until reconciler transitions it
    // to `.synced` or back to `.miss`, so it doesn't vanish from the count
    // while a background job is still processing.
    pendingWals = wals.filter { $0.status == .miss || $0.status == .inProgress || $0.status == .uploaded }
  }

  // MARK: - Frame Recording

  /// Start recording frames from a device
  func startRecording(device: String, codec: String) {
    freezeActiveFrameBuffer()
    activeFrameBuffer = ActiveFrameBuffer(
      device: device,
      codec: codec,
      startTime: timestampProvider()
    )

    startTimers()
    startFramePersistenceIfNeeded()
    logger.info("Started recording from device: \(device), codec: \(codec)")
  }

  /// Add a frame to the current recording
  func addFrame(_ frame: Data, synced: Bool = false) {
    guard activeFrameBuffer != nil else {
      logger.warning("Ignoring frame received without an active recording identity")
      return
    }
    activeFrameBuffer?.frames.append(frame)
    activeFrameBuffer?.syncFlags.append(synced)
  }

  /// Stop recording and create final WAL
  func stopRecording() {
    stopTimers()
    freezeActiveFrameBuffer()
    activeFrameBuffer = nil
    startFramePersistenceIfNeeded()

    if !pendingFrameBatches.isEmpty {
      log(
        "WALService: stopRecording retained \(currentFrameCountForTesting) frames in persistence batches")
    }

    logger.info("Stopped recording")
  }

  private func startTimers() {
    // Chunk timer - create WAL every N seconds
    let chunkInterval = TimeInterval(Self.chunkSizeInSeconds + Self.newFrameSyncDelaySeconds)
    chunkTimer = Timer.scheduledTimer(withTimeInterval: chunkInterval, repeats: true) { [weak self] _ in
      Task { @MainActor in
        self?.checkAndChunk()
      }
    }

    // Flush timer - write to disk periodically
    let flushInterval = TimeInterval(Self.flushIntervalInSeconds + Self.newFrameSyncDelaySeconds)
    flushTimer = Timer.scheduledTimer(withTimeInterval: flushInterval, repeats: true) { [weak self] _ in
      Task { @MainActor in
        self?.flushToDisk()
      }
    }
  }

  private func stopTimers() {
    chunkTimer?.invalidate()
    chunkTimer = nil
    flushTimer?.invalidate()
    flushTimer = nil
  }

  private func checkAndChunk() {
    // Check if we have enough unsynced frames to create a WAL
    let unsyncedCount = activeFrameBuffer?.syncFlags.filter { !$0 }.count ?? 0

    if unsyncedCount >= Self.lossesThresholdFrames {
      createWalFromCurrentFrames()
    }
  }

  private func flushToDisk() {
    // Retry the oldest immutable frame batch without coalescing it with the
    // active capture buffer.
    startFramePersistenceIfNeeded()
    // Write any in-memory WALs to disk
    for i in 0..<wals.count {
      if wals[i].storage == .memory {
        writeWalToDisk(at: i)
      }
    }
    saveWals()
  }

  @discardableResult
  private func createWalFromCurrentFrames() -> Bool {
    freezeActiveFrameBuffer()
    return startFramePersistenceIfNeeded()
  }

  private func freezeActiveFrameBuffer() {
    guard var active = activeFrameBuffer, !active.frames.isEmpty else { return }
    precondition(active.frames.count == active.syncFlags.count)
    let timerStart = reserveTimerStart(device: active.device, proposed: active.startTime)
    pendingFrameBatches.append(
      PendingFrameBatch(
        id: UUID(),
        device: active.device,
        codec: active.codec,
        startTime: timerStart,
        frames: active.frames,
        syncFlags: active.syncFlags
      )
    )
    active.frames = []
    active.syncFlags = []
    active.startTime = timestampProvider()
    activeFrameBuffer = active
  }

  private func reserveTimerStart(device: String, proposed: Int) -> Int {
    let occupied = Set(
      wals.lazy
        .filter { $0.device == device }
        .map(\.timerStart)
    ).union(
      pendingFrameBatches.lazy
        .filter { $0.device == device }
        .map(\.startTime)
    )
    var candidate = proposed
    while occupied.contains(candidate) {
      precondition(candidate < Int.max, "WAL timerStart reservation exhausted")
      candidate += 1
    }
    return candidate
  }

  @discardableResult
  private func startFramePersistenceIfNeeded() -> Bool {
    guard frameWriteTask == nil, !pendingFrameBatches.isEmpty else { return true }
    guard walDirectory != nil else {
      let reason = "wal_directory_unavailable"
      persistenceState = .degraded(reason: reason)
      errorMessage = "Audio backup storage unavailable. Recording continues locally in memory."
      log(
        "WALService: skipping WAL chunk — no directory "
          + "(failure_class=wal_persistence_degraded recovery_action=retain_frames recovery_result=degraded)")
      DesktopDiagnosticsManager.shared.recordWalPersistenceDegraded(
        reason: reason,
        recoveryAction: "retain_frames",
        recoveryResult: "degraded"
      )
      return false
    }

    frameWriteTask = Task { [weak self] in
      guard let self else { return }
      await self.persistHeadFrameBatch()
    }
    return true
  }

  private func persistHeadFrameBatch() async {
    guard let batch = pendingFrameBatches.first else {
      frameWriteTask = nil
      return
    }

    if batch.recoveryRecord == nil {
      guard let request = makeFramePersistenceRequest(for: batch) else {
        frameWriteTask = nil
        recordFrameWriteFailure(walId: walID(for: batch), reason: "wal_identity_collision")
        return
      }
      do {
        let record = try await frameWriter(request)
        guard pendingFrameBatches.first?.id == batch.id else {
          frameWriteTask = nil
          return
        }
        pendingFrameBatches[0].recoveryRecord = record
        pendingFrameBatches[0].recoveryURL = request.recoveryURL
        applyPersistedWal(record.wal)
        updatePendingWals()
      } catch {
        frameWriteTask = nil
        let reason = error.localizedDescription
        log(
          "WALService: Failed to write frames to disk "
            + "(failure_class=wal_write_failed recovery_action=retain_batch recovery_result=degraded): "
            + reason)
        recordFrameWriteFailure(walId: walID(for: batch), reason: reason)
        return
      }
    } else if let record = batch.recoveryRecord {
      // Reassert the durable audio identity before every metadata retry.
      // Status changes on an equal/newer in-memory entry are preserved.
      applyPersistedWal(record.wal)
      updatePendingWals()
    }

    do {
      // The in-memory WAL is applied before this awaited write. Any
      // concurrent saveWals snapshot therefore includes the audio, and all
      // metadata writes share one revisioned serial queue.
      try await persistCurrentWalMetadata()
    } catch {
      frameWriteTask = nil
      let reason = error.localizedDescription
      persistenceState = .degraded(reason: reason)
      errorMessage = "Failed to save audio backup metadata. Audio remains recoverable."
      DesktopDiagnosticsManager.shared.recordWalPersistenceDegraded(
        reason: reason,
        recoveryAction: "retain_batch",
        recoveryResult: "degraded"
      )
      return
    }

    guard pendingFrameBatches.first?.id == batch.id else {
      frameWriteTask = nil
      return
    }
    let recoveryURL = pendingFrameBatches[0].recoveryURL
    pendingFrameBatches.removeFirst()
    if let recoveryURL {
      await Self.removeRecoveryFile(recoveryURL)
    }
    persistenceState = .ready
    errorMessage = nil
    frameWriteTask = nil
    startFramePersistenceIfNeeded()
  }

  private func makeFramePersistenceRequest(for batch: PendingFrameBatch) -> FramePersistenceRequest? {
    guard let walDirectory else { return nil }
    let framesPerSecond = batch.codec == "opus_fs320" ? 50 : 100
    var wal = WALEntry(
      timerStart: batch.startTime,
      codec: batch.codec,
      status: .miss,
      storage: .disk,
      seconds: max(1, batch.frames.count / framesPerSecond),
      device: batch.device,
      deviceModel: batch.device,
      totalFrames: batch.frames.count
    )
    guard !wals.contains(where: { $0.id == wal.id }) else { return nil }
    let fileName = wal.generateFileName()
    wal.filePath = fileName
    return FramePersistenceRequest(
      fileURL: walDirectory.appendingPathComponent(fileName),
      recoveryURL: walDirectory.appendingPathComponent(fileName + ".wal-pending.json"),
      wal: wal,
      frames: batch.frames
    )
  }

  private func applyPersistedWal(_ persisted: WALEntry) {
    guard let index = wals.firstIndex(where: { $0.id == persisted.id }) else {
      wals.append(persisted)
      logger.info("Created new WAL: \(persisted.id) with \(persisted.totalFrames) frames")
      return
    }
    var merged = wals[index]
    if persisted.totalFrames > merged.totalFrames {
      merged.totalFrames = persisted.totalFrames
      merged.status = .miss
    }
    merged.seconds = max(merged.seconds, persisted.seconds)
    merged.storage = .disk
    merged.filePath = persisted.filePath
    wals[index] = merged
    logger.debug("Committed persisted WAL \(persisted.id) with \(persisted.totalFrames) frames")
  }

  private func walID(for batch: PendingFrameBatch) -> String {
    "\(batch.device)_\(batch.startTime)"
  }

  nonisolated static func writeFrameTransaction(
    _ request: FramePersistenceRequest
  ) async throws -> FrameRecoveryRecord {
    try await Task.detached(priority: .utility) {
      let fileData = encodeFrames(request.frames)
      let record = FrameRecoveryRecord(
        wal: request.wal,
        fileName: request.fileURL.lastPathComponent,
        expectedAudioBytes: fileData.count,
        expectedAudioSHA256: sha256Hex(fileData)
      )
      let recoveryData = try JSONEncoder().encode(record)
      try recoveryData.write(to: request.recoveryURL, options: .atomic)
      // Foundation traps when `.atomic` and `.withoutOverwriting` are
      // combined. Write an exclusive temporary file in the destination
      // directory, then atomically rename it into place instead.
      let temporaryURL = request.fileURL
        .deletingLastPathComponent()
        .appendingPathComponent(".\(request.fileURL.lastPathComponent).\(UUID().uuidString).tmp")
      defer { try? FileManager.default.removeItem(at: temporaryURL) }
      try fileData.write(to: temporaryURL, options: .withoutOverwriting)
      try FileManager.default.moveItem(at: temporaryURL, to: request.fileURL)
      log("WALService: Wrote \(request.frames.count) frames to \(request.fileURL.lastPathComponent)")
      return record
    }.value
  }

  nonisolated private static func removeRecoveryFile(_ recoveryURL: URL) async {
    _ = await Task.detached(priority: .utility) {
      try? FileManager.default.removeItem(at: recoveryURL)
    }.value
  }

  nonisolated private static func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  /// Length-prefix encode frames into the on-disk WAL chunk byte layout
  /// (`UInt32 little-endian length + frame bytes`, repeated).
  /// `nonisolated`: pure byte transform, no actor state — callable synchronously
  /// from the off-main disk-write path and from tests.
  nonisolated static func encodeFrames(_ frames: [Data]) -> Data {
    var fileData = Data()
    for frame in frames {
      var length = UInt32(frame.count).littleEndian
      fileData.append(Data(bytes: &length, count: 4))
      fileData.append(frame)
    }
    return fileData
  }

  private func writeFramesToDisk(frames: [Data], wal: WALEntry) {
    guard let walDir = walDirectory else {
      recordFrameWriteFailure(walId: wal.id, reason: "wal_directory_unavailable")
      return
    }

    let fileName = wal.generateFileName()
    let fileUrl = walDir.appendingPathComponent(fileName)
    let walId = wal.id

    // Build file data: [uint32 length][frame data][uint32 length][frame data]...
    var fileData = Data()
    for frame in frames {
      var length = UInt32(frame.count).littleEndian
      fileData.append(Data(bytes: &length, count: 4))
      fileData.append(frame)
    }
    let fileDataPayload = fileData

    let frameCount = frames.count

    // Write to disk on background thread to avoid blocking the main actor.
    // The completion handler hops back to main to set filePath — callers that
    // need filePath set before proceeding should use writeFramesToDiskAndWait.
    DispatchQueue.global(qos: .utility).async { [weak self] in
      do {
        try fileDataPayload.write(to: fileUrl, options: .atomic)
        log("WALService: Wrote \(frameCount) frames to \(fileName)")

        DispatchQueue.main.async { [weak self] in
          guard let self else { return }
          if let index = self.wals.firstIndex(where: { $0.id == walId }) {
            self.wals[index].storage = .disk
            self.wals[index].filePath = fileName
            // Persist immediately so the entry isn't orphaned as
            // `.memory` if the app crashes before the next saveWals().
            self.saveWals()
          }
        }
      } catch {
        let reason = error.localizedDescription
        log(
          "WALService: Failed to write frames to disk "
            + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded): "
            + reason)
        DispatchQueue.main.async { [weak self] in
          self?.recordFrameWriteFailure(walId: walId, reason: reason)
        }
      }
    }
  }

  /// Synchronous variant that writes off-main but blocks the caller until the
  /// file is on disk and filePath is set. Returns false when persistence fails.
  @discardableResult
  private func writeFramesToDiskAndWait(frames: [Data], wal: WALEntry) -> Bool {
    guard let walDir = walDirectory else {
      recordFrameWriteFailure(walId: wal.id, reason: "wal_directory_unavailable")
      return false
    }

    let fileName = wal.generateFileName()
    let fileUrl = walDir.appendingPathComponent(fileName)
    let walId = wal.id

    var fileData = Data()
    for frame in frames {
      var length = UInt32(frame.count).littleEndian
      fileData.append(Data(bytes: &length, count: 4))
      fileData.append(frame)
    }
    let fileDataPayload = fileData

    let frameCount = frames.count
    let writeSucceeded: Bool = DispatchQueue.global(qos: .utility).sync {
      do {
        try fileDataPayload.write(to: fileUrl, options: .atomic)
        log("WALService: Wrote \(frameCount) frames to \(fileName)")
        return true
      } catch {
        let reason = error.localizedDescription
        log(
          "WALService: Failed to write frames to disk "
            + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded): "
            + reason)
        return false
      }
    }

    if writeSucceeded, let index = wals.firstIndex(where: { $0.id == walId }) {
      wals[index].storage = .disk
      wals[index].filePath = fileName
      return true
    }

    if !writeSucceeded {
      recordFrameWriteFailure(walId: walId, reason: "frame_write_failed")
    }
    return false
  }

  private func recordFrameWriteFailure(walId: String, reason: String) {
    errorMessage = "Failed to save audio backup. Recording continues in memory."
    persistenceState = .degraded(reason: reason)
    log(
      "WALService: frame write failed for \(walId) "
        + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded reason=\(reason))")
    DesktopDiagnosticsManager.shared.recordWalWriteFailed(walId: walId, reason: reason)
  }

  private func writeWalToDisk(at index: Int) {
    // Frames are persisted by `writeFramesToDisk` when the WAL is created;
    // there is no separate in-memory frame buffer to flush here. Only promote
    // to `.disk` once the backing file actually exists — otherwise we'd mark an
    // entry `.disk` with no frames and no `filePath`, which sends it into the
    // sync path where it fails with `fileNotFound` and the recording is lost
    // (#9240). Leave it `.memory` so the in-flight write (or a retry) can
    // complete it.
    guard let walDir = walDirectory,
      let fileName = wals[index].filePath, !fileName.isEmpty,
      fileManager.fileExists(atPath: walDir.appendingPathComponent(fileName).path)
    else {
      logger.warning("WALService: skipping disk promotion for \(self.wals[index].id); frames not yet persisted")
      return
    }
    wals[index].storage = .disk
  }

  // MARK: - SD Card Sync

  /// Create a WAL entry for SD card data that needs to be downloaded
  func createSdCardWal(
    device: String,
    deviceModel: String,
    codec: String,
    totalBytes: Int,
    currentOffset: Int,
    fileNum: Int = 1
  ) -> WALEntry {
    let timerStart = reserveTimerStart(device: device, proposed: timestampProvider())
    let framesPerSecond = codec == "opus_fs320" ? 50 : 100
    let bytesPerFrame = codec == "opus_fs320" ? 160 : 80
    let totalFrames = totalBytes / bytesPerFrame
    let seconds = totalFrames / framesPerSecond

    let wal = WALEntry(
      timerStart: timerStart,
      codec: codec,
      status: .miss,
      storage: .sdcard,
      seconds: seconds,
      device: device,
      deviceModel: deviceModel,
      storageOffset: currentOffset,
      storageTotalBytes: totalBytes,
      fileNum: fileNum,
      totalFrames: totalFrames
    )

    wals.append(wal)
    updatePendingWals()
    saveWals()

    logger.info("Created SD card WAL: \(wal.id), \(totalBytes) bytes, offset \(currentOffset)")
    return wal
  }

  /// Remove a just-created SD-card WAL that never received any data (a failed
  /// or aborted sync). `createSdCardWal` reserves a `.miss` entry before the
  /// download starts; leaving it after a failure permanently inflates the
  /// persisted "pending" count. A WAL that downloaded frames has a `filePath`
  /// (set by `writeFramesToDiskAndWait`) and is kept.
  func removeSdCardWalIfEmpty(walId: String) {
    guard let index = wals.firstIndex(where: { $0.id == walId }) else { return }
    let wal = wals[index]
    guard wal.storage == .sdcard, wal.status == .miss, wal.filePath == nil else { return }
    wals.remove(at: index)
    updatePendingWals()
    saveWals()
    logger.info("Removed empty SD card WAL after failed/aborted sync: \(walId)")
  }

  /// Update WAL with downloaded data
  func updateWalWithDownloadedData(walId: String, downloadedBytes: Int, frames: [Data]) {
    guard let index = wals.firstIndex(where: { $0.id == walId }) else {
      logger.warning("WAL not found for update: \(walId)")
      return
    }

    wals[index].storageOffset += downloadedBytes
    wals[index].totalFrames = frames.count

    // Write frames to disk and wait for completion so filePath is set before
    // the caller (finishSync → syncToCloud) reads it. The write itself runs
    // off-main; the BLE download path that calls this is already off-main.
    writeFramesToDiskAndWait(frames: frames, wal: wals[index])

    // Check if download complete
    if wals[index].storageOffset >= wals[index].storageTotalBytes {
      wals[index].storage = .disk
      logger.info("SD card download complete for WAL: \(walId)")
    }

    updatePendingWals()
    saveWals()
  }

  // MARK: - Cloud Sync

  /// Sync all pending WALs to cloud
  func syncToCloud() async {
    guard !isSyncing else {
      logger.warning("Sync already in progress")
      return
    }

    isSyncing = true
    defer { isSyncing = false }

    let toSync = wals.filter { $0.status == .miss && $0.storage == .disk }

    for wal in toSync {
      do {
        try await uploadWalToCloud(wal)
      } catch APIError.syncRateLimited {
        logger.warning("WAL upload rate limited; leaving pending WALs for retry")
        break
      } catch {
        logger.error("Failed to sync WAL \(wal.id): \(error.localizedDescription)")
      }
    }

    // Reconcile operates on a pre-await snapshot because it runs per-job network
    // awaits on the main actor; merge its id-keyed transitions back onto the live
    // array so WALs appended during those awaits are not dropped (see
    // WALCloudSyncLogic.mergeReconciledUploads).
    let snapshot = wals
    var workingWals = snapshot
    if await reconciler.reconcileUploadedWals(wals: &workingWals, walDirectory: walDirectory) {
      wals = WALCloudSyncLogic.mergeReconciledUploads(live: wals, snapshot: snapshot, reconciled: workingWals)
      updatePendingWals()
      saveWals()
    }

    // If jobs are still in-flight (.uploaded) after the immediate reconcile,
    // schedule a follow-up poll so queued/processing jobs eventually resolve.
    // Without this, a 202 + still-queued GET leaves WALs stuck in .uploaded.
    scheduleReconcileRetryIfNeeded()
  }

  /// One-shot delayed retry that re-runs reconcile for in-flight uploaded jobs.
  private var reconcileRetryItem: DispatchWorkItem?

  private func scheduleReconcileRetryIfNeeded() {
    guard wals.contains(where: { $0.status == .uploaded }) else {
      reconcileRetryItem?.cancel()
      reconcileRetryItem = nil
      return
    }
    // Already scheduled — let the existing one fire.
    if reconcileRetryItem != nil { return }
    let item = DispatchWorkItem { [weak self] in
      guard let self else { return }
      self.reconcileRetryItem = nil
      Task { await self.syncToCloud() }
    }
    reconcileRetryItem = item
    DispatchQueue.main.asyncAfter(deadline: .now() + 30, execute: item)
  }

  private func uploadWalToCloud(_ wal: WALEntry) async throws {
    do {
      try await performWalUpload(wal)
    } catch {
      if case APIError.syncRateLimited = error {
        throw error
      }
      let reason = String(describing: error)
      log(
        "WALService: upload failed for \(wal.id) "
          + "(failure_class=wal_upload_failed recovery_action=leave_pending recovery_result=degraded): "
          + reason)
      DesktopDiagnosticsManager.shared.recordWalUploadFailed(walId: wal.id, reason: reason)
      throw error
    }
  }

  private func performWalUpload(_ wal: WALEntry) async throws {
    guard let walDir = walDirectory,
      let filePath = wal.filePath
    else {
      throw WALError.fileNotFound
    }

    let fileUrl = walDir.appendingPathComponent(filePath)

    guard fileManager.fileExists(atPath: fileUrl.path) else {
      if let index = wals.firstIndex(where: { $0.id == wal.id }) {
        wals[index].status = .corrupted
        updatePendingWals()
        saveWals()
      }
      throw WALError.fileNotFound
    }

    let result: UploadLocalFilesResult
    if let handler = uploadLocalFilesHandler {
      result = try await handler(fileUrl)
    } else {
      result = try await apiClient.uploadLocalFilesV2(fileURLs: [fileUrl])
    }

    guard let index = wals.firstIndex(where: { $0.id == wal.id }) else {
      return
    }

    WALCloudSyncLogic.applyUploadResult(to: &wals[index], result: result)
    let uploadedStatus = wals[index].status.rawValue
    if let jobId = wals[index].jobId {
      logger.info("Uploaded WAL \(wal.id): status=\(uploadedStatus), jobId=\(jobId)")
    } else {
      logger.info("Uploaded WAL \(wal.id): status=\(uploadedStatus)")
    }

    updatePendingWals()
    saveWals()
  }

  // MARK: - Cleanup

  /// Remove synced WALs older than specified days
  func cleanupOldWals(olderThanDays: Int = 7) {
    let cutoff = Date().addingTimeInterval(-Double(olderThanDays * 24 * 60 * 60))
    let cutoffTimestamp = Int(cutoff.timeIntervalSince1970)

    let toRemove = wals.filter { $0.status == .synced && $0.timerStart < cutoffTimestamp }

    for wal in toRemove {
      // Delete file
      if let filePath = wal.filePath, let walDir = walDirectory {
        let fileUrl = walDir.appendingPathComponent(filePath)
        try? fileManager.removeItem(at: fileUrl)
      }
    }

    wals.removeAll { wal in
      toRemove.contains { $0.id == wal.id }
    }

    updatePendingWals()
    saveWals()

    logger.info("Cleaned up \(toRemove.count) old WALs")
  }

  /// Get WAL by ID
  func getWal(id: String) -> WALEntry? {
    wals.first { $0.id == id }
  }

  /// Get file path for a WAL
  func getWalFilePath(_ wal: WALEntry) -> URL? {
    guard let filePath = wal.filePath, let walDir = walDirectory else {
      return nil
    }
    return walDir.appendingPathComponent(filePath)
  }
}

// MARK: - WAL Errors

enum WALError: LocalizedError {
  case fileNotFound
  case noFramesToUpload
  case uploadFailed(String)
  case decodingFailed(String)

  var errorDescription: String? {
    switch self {
    case .fileNotFound:
      return "WAL file not found"
    case .noFramesToUpload:
      return "No frames to upload"
    case .uploadFailed(let reason):
      return "Upload failed: \(reason)"
    case .decodingFailed(let reason):
      return "Decoding failed: \(reason)"
    }
  }
}
