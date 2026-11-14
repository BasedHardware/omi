import Combine
import Foundation
import OmiWAL
import os.log

// MARK: - Storage Sync Service

/// Service for syncing audio data from device SD card via BLE
/// Ported from: omi/app/lib/services/wals/sdcard_wal_sync.dart
@MainActor
final class StorageSyncService: ObservableObject {

  // MARK: - Singleton

  static let shared = StorageSyncService()

  // MARK: - Published Properties

  /// Whether sync is in progress
  @Published private(set) var isSyncing = false

  /// Current sync progress
  @Published private(set) var progress: SyncProgress = SyncProgress()

  /// Error message if sync fails
  @Published var errorMessage: String?

  // MARK: - Constants

  /// Minimum bytes to trigger a sync (10 frames worth)
  static let minBytesToSync = 80 * 10 * 100  // 10 seconds at 80 bytes/frame, 100 fps

  /// BLE packet size for standard packets
  static let standardPacketSize = 83

  /// BLE packet size for packed format
  static let packedPacketSize = 440

  // MARK: - Properties

  private let logger = Logger(subsystem: "me.omi.desktop", category: "StorageSyncService")
  private let walService = WALService.shared
  private let deviceProvider = DeviceProvider.shared

  private var syncTask: Task<Void, Never>?
  private var currentWal: WALEntry?
  private var downloadedFrames: [Data] = []
  private var totalBytesDownloaded = 0
  private var lastProgressUpdate = Date()
  private var lastProgressBytes = 0

  /// Monotonic identity for the current sync attempt.
  ///
  /// `stopSync` and `finishSync` both suspend on the async WAL write. Without an
  /// identity check, a stop that resumes after a new sync has started would
  /// clear the new sync's state, and a cancelled `finishSync` could upload and
  /// reset a newer attempt. Every start/stop bumps this; a suspended path only
  /// mutates shared state while its captured generation is still current.
  private var syncGeneration = 0

  // MARK: - Initialization

  private init() {}

  // MARK: - Public Methods

  /// Check if device has data to sync
  func checkForStorageData() async -> (totalBytes: Int, currentOffset: Int)? {
    guard let connection = deviceProvider.activeConnection else {
      logger.warning("No device connected for storage check")
      return nil
    }

    let storageList = await connection.getStorageList()

    guard storageList.count >= 2 else {
      logger.debug("No storage data available")
      return nil
    }

    let totalBytes = Int(storageList[0])
    let currentOffset = Int(storageList[1])

    logger.info("Storage check: total=\(totalBytes), offset=\(currentOffset)")
    return (totalBytes, currentOffset)
  }

  /// Start syncing from device storage
  func startSync(device: BtDevice, codec: String) async throws {
    guard !isSyncing else {
      logger.warning("Sync already in progress")
      return
    }

    guard let connection = deviceProvider.activeConnection else {
      throw StorageSyncError.deviceNotConnected
    }

    // Check storage status
    guard let (totalBytes, currentOffset) = await checkForStorageData() else {
      throw StorageSyncError.noDataToSync
    }

    let bytesToDownload = totalBytes - currentOffset
    guard bytesToDownload >= Self.minBytesToSync else {
      logger.info("Not enough data to sync: \(bytesToDownload) bytes")
      return
    }

    isSyncing = true
    errorMessage = nil
    downloadedFrames = []
    totalBytesDownloaded = 0
    lastProgressUpdate = Date()
    lastProgressBytes = 0

    // Claim a fresh generation for this attempt. A stop or completion from an
    // earlier attempt that resumes after an await will see a stale generation
    // and leave this sync's state alone.
    syncGeneration &+= 1
    let generation = syncGeneration

    // Create WAL for this sync
    currentWal = walService.createSdCardWal(
      device: device.id,
      deviceModel: device.type.displayName,
      codec: codec,
      totalBytes: totalBytes,
      currentOffset: currentOffset
    )

    progress = SyncProgress(
      totalBytes: bytesToDownload,
      downloadedBytes: 0
    )

    logger.info("Starting SD card sync: \(bytesToDownload) bytes to download")

    // Start sync task
    syncTask = Task { [weak self] in
      await self?.performSync(connection: connection, offset: currentOffset, generation: generation)
    }
  }

  /// Stop current sync
  func stopSync() async {
    syncTask?.cancel()
    syncTask = nil

    // Invalidate the cancelled attempt before suspending, and take ownership of
    // its state up front. Clearing before the await means a sync started while
    // the partial write is in flight owns fresh state and cannot be clobbered
    // when this stop resumes.
    syncGeneration &+= 1
    let wal = currentWal
    let frames = downloadedFrames
    let bytes = totalBytesDownloaded

    isSyncing = false
    currentWal = nil
    downloadedFrames = []
    totalBytesDownloaded = 0
    lastProgressBytes = 0

    // Save partial progress
    if let wal, !frames.isEmpty {
      await walService.updateWalWithDownloadedData(
        walId: wal.id,
        downloadedBytes: bytes,
        frames: frames
      )
    }

    logger.info("Sync stopped")
  }

  /// Clear device storage after successful sync
  func clearDeviceStorage() async -> Bool {
    guard let connection = deviceProvider.activeConnection else {
      logger.warning("No device connected for storage clear")
      return false
    }

    let success = await connection.writeToStorage(
      fileNum: 1,
      command: StorageCommand.clear.rawValue,
      offset: 0
    )

    if success {
      logger.info("Device storage cleared")
    } else {
      logger.error("Failed to clear device storage")
    }

    return success
  }

  // MARK: - Private Methods

  private func performSync(connection: DeviceConnection, offset: Int, generation: Int) async {
    // Send read command to start transfer
    let success = await connection.writeToStorage(
      fileNum: 1,
      command: StorageCommand.read.rawValue,
      offset: offset
    )

    guard success else {
      guard generation == syncGeneration else { return }
      errorMessage = "Failed to start storage transfer"
      isSyncing = false
      return
    }

    // Listen for data stream
    let stream = connection.getStorageStream()

    do {
      for try await data in stream {
        // A stop or a newer sync invalidates this attempt; stop consuming so we
        // never append frames to another attempt's buffer.
        if Task.isCancelled || generation != syncGeneration { break }

        let result = processPacket(data)

        switch result {
        case .continue:
          continue

        case .complete:
          logger.info("Transfer complete")
          await finishSync(generation: generation)
          return

        case .error(let message):
          logger.error("Transfer error: \(message)")
          guard generation == syncGeneration else { return }
          errorMessage = message
          isSyncing = false
          return
        }
      }
    } catch {
      if !Task.isCancelled {
        logger.error("Stream error: \(error.localizedDescription)")
        guard generation == syncGeneration else { return }
        errorMessage = error.localizedDescription
        isSyncing = false
      }
    }
  }

  private enum PacketResult {
    case `continue`
    case complete
    case error(String)
  }

  private func processPacket(_ data: Data) -> PacketResult {
    guard !data.isEmpty else { return .continue }

    // Check for response codes
    if data.count == 1 {
      let code = data[0]

      if let response = StorageResponse(rawValue: code) {
        switch response {
        case .ok:
          return .continue
        case .endOfTransmission:
          return .complete
        case .badFileSize:
          return .error("Bad file size")
        case .fileSizeZero:
          return .error("File is empty")
        }
      }

      // Unknown single-byte response
      if code >= 100 {
        return .complete
      }
      return .continue
    }

    // Process data packet
    if data.count == Self.standardPacketSize {
      processStandardPacket(data)
    } else if data.count == Self.packedPacketSize {
      processPackedPacket(data)
    } else {
      // Variable size packet - try to parse as frames. Count its bytes too
      // (mirroring processPackedPacket): without this, a packet whose length is
      // neither the standard nor packed size contributes decoded frames but zero
      // counted bytes, so totalBytesDownloaded (and the WAL storageOffset it
      // advances) stays ~0 — progress reports ~0%/bogus B-s and the
      // `storageOffset >= storageTotalBytes` completion check never fires even
      // though the audio was actually downloaded.
      parseFramesFromData(data)
      totalBytesDownloaded += data.count
    }

    // Update progress periodically
    updateProgress()

    return .continue
  }

  private func processStandardPacket(_ data: Data) {
    // Format: [header(3)][count][data(80)]
    guard data.count >= 4 else { return }

    let frameData = data.suffix(80)
    if frameData.count == 80 && OpusFrameValidator.startsWithValidFrame(Data(frameData)) {
      downloadedFrames.append(Data(frameData))
      totalBytesDownloaded += 80
    }
  }

  private func processPackedPacket(_ data: Data) {
    // Format: [frameSize][frameData][frameSize][frameData]...
    parseFramesFromData(data)
    totalBytesDownloaded += data.count
  }

  private func parseFramesFromData(_ data: Data) {
    var offset = 0

    while offset < data.count {
      // Read frame size (1 byte)
      let frameSize = Int(data[offset])
      offset += 1

      // Check for padding/empty slot
      if frameSize == 0 {
        // Skip padding until next block boundary
        let blockOffset = offset % Self.packedPacketSize
        if blockOffset != 0 {
          let remaining = Self.packedPacketSize - blockOffset
          offset += remaining
        }
        continue
      }

      // Validate frame size
      guard frameSize > 0, offset + frameSize <= data.count else {
        break
      }

      // Check if valid Opus frame
      let frameData = data.subdata(in: offset..<(offset + frameSize))
      if OpusFrameValidator.startsWithValidFrame(frameData) {
        downloadedFrames.append(frameData)
      }

      offset += frameSize
    }
  }

  /// Throughput over an interval. `nonisolated static` so it is synchronously
  /// unit-testable without hopping the main actor.
  nonisolated static func bytesPerSecond(bytesDelta: Int, interval: TimeInterval) -> Double {
    interval > 0 ? Double(bytesDelta) / interval : 0
  }

  private func updateProgress() {
    let now = Date()
    let interval = now.timeIntervalSince(lastProgressUpdate)
    guard interval >= 0.5 else { return }

    // Rate over the elapsed interval since the last update, using the bytes
    // downloaded in that window. The previous code reassigned lastProgressUpdate
    // to `now` before computing `elapsed = now - lastProgressUpdate`, so `elapsed`
    // was always 0 and the reported speed was always 0 B/s.
    let bytesDelta = totalBytesDownloaded - lastProgressBytes
    let bytesPerSecond = Self.bytesPerSecond(bytesDelta: bytesDelta, interval: interval)
    lastProgressUpdate = now
    lastProgressBytes = totalBytesDownloaded
    let generation = syncGeneration

    Task { @MainActor in
      // A stop or newer sync may have replaced this attempt's progress.
      guard generation == syncGeneration else { return }
      progress = SyncProgress(
        totalBytes: progress.totalBytes,
        downloadedBytes: totalBytesDownloaded,
        framesDownloaded: downloadedFrames.count,
        bytesPerSecond: bytesPerSecond
      )
    }
  }

  private func finishSync(generation: Int) async {
    guard generation == syncGeneration, let wal = currentWal else { return }

    // Snapshot this attempt's frames before suspending: a stop or a newer sync
    // may mutate the shared buffers while the write is in flight.
    let frames = downloadedFrames
    let bytes = totalBytesDownloaded
    let frameCount = frames.count

    // Save downloaded data
    await walService.updateWalWithDownloadedData(
      walId: wal.id,
      downloadedBytes: bytes,
      frames: frames
    )

    // A stop or a newer sync took over while we were writing. Do not upload or
    // reset state that no longer belongs to this attempt.
    guard generation == syncGeneration else {
      logger.info("Sync completion superseded; skipping upload and state reset")
      return
    }

    // Upload downloaded WALs to cloud (real POST /v2/sync-local-files) before
    // resetting isSyncing, so a concurrent BLE download cannot start and get
    // its own syncToCloud() skipped by WALService's isSyncing guard.
    await walService.syncToCloud()

    guard generation == syncGeneration else {
      logger.info("Sync completion superseded during upload; skipping state reset")
      return
    }

    isSyncing = false
    currentWal = nil
    downloadedFrames = []
    totalBytesDownloaded = 0

    logger.info("Sync completed: \(frameCount) frames downloaded")
  }
}

// MARK: - Storage Sync Errors

enum StorageSyncError: LocalizedError {
  case deviceNotConnected
  case noDataToSync
  case transferFailed(String)
  case timeout

  var errorDescription: String? {
    switch self {
    case .deviceNotConnected:
      return "Device not connected"
    case .noDataToSync:
      return "No data available to sync"
    case .transferFailed(let reason):
      return "Transfer failed: \(reason)"
    case .timeout:
      return "Transfer timed out"
    }
  }
}
