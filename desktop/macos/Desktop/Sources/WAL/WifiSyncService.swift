import Combine
import Foundation
import Network
import OmiWAL
import os.log

// MARK: - WiFi Sync Service

/// Service for syncing audio data from device via WiFi
/// Handles device AP connection and TCP data transfer
/// Ported from: omi/app/lib/services/wals/wal_service.dart (WiFi sync portions)
@MainActor
final class WifiSyncService: ObservableObject {

  // MARK: - Singleton

  static let shared = WifiSyncService()

  // MARK: - Published Properties

  /// Whether WiFi sync is in progress
  @Published private(set) var isSyncing = false

  /// Current sync status
  @Published private(set) var status: WifiStatus = .off

  /// Current sync progress
  @Published private(set) var progress: SyncProgress = SyncProgress()

  /// Transfer speed (bytes per second)
  @Published private(set) var transferSpeed: Double = 0

  /// Error message if sync fails
  @Published var errorMessage: String?

  // MARK: - Constants

  /// Default TCP port for device WiFi sync
  static let defaultPort: UInt16 = 12345

  /// Connection timeout in seconds
  static let connectionTimeout: TimeInterval = 60

  /// Transfer timeout in seconds
  static let transferTimeout: TimeInterval = 300  // 5 minutes

  /// Speed calculation window in seconds
  static let speedWindowSeconds: TimeInterval = 3

  // MARK: - Properties

  private let logger = Logger(subsystem: "me.omi.desktop", category: "WifiSyncService")
  private let deviceProvider = DeviceProvider.shared
  private let walServiceOverride: WALService?

  private var activeWalService: WALService {
    // Keep the production singleton lazy: constructing an injected test
    // service must never recover the real user's WAL directory.
    walServiceOverride ?? WALService.shared
  }

  private var tcpConnection: NWConnection?
  private var syncTask: Task<Void, Error>?
  private var statusStreamTask: Task<Void, Never>?

  private var currentWal: WALEntry?
  private var downloadedFrames: [Data] = []
  private var totalBytesDownloaded = 0
  private var transferStartTime: Date?

  /// Tracks the absolute stream position across chunks so 440-byte block
  /// boundaries are computed from the stream start, not the per-chunk buffer.
  private var frameParser = WifiFrameStreamParser()

  // Speed tracking
  private var speedSamples: [(timestamp: Date, bytes: Int)] = []

  // MARK: - Initialization

  init(walServiceForTesting: WALService? = nil) {
    walServiceOverride = walServiceForTesting
  }

  // MARK: - Public Methods

  /// Check if device supports WiFi sync
  func isWifiSyncSupported() async -> Bool {
    guard let connection = deviceProvider.activeConnection else { return false }
    return await connection.isWifiSyncSupported()
  }

  /// Start WiFi sync process
  /// This is a multi-step process:
  /// 1. Setup WiFi credentials on device (if needed)
  /// 2. Device creates WiFi AP
  /// 3. Mac connects to device AP
  /// 4. Send read command over BLE
  /// 5. Disconnect BLE
  /// 6. Transfer data over TCP
  /// 7. Reconnect BLE and clear storage
  func startWifiSync(
    device: BtDevice,
    codec: String,
    ssid: String? = nil,
    password: String? = nil
  ) async throws {
    guard !isSyncing else {
      logger.warning("WiFi sync already in progress")
      return
    }

    guard let connection = deviceProvider.activeConnection else {
      throw WifiSyncServiceError.deviceNotConnected
    }

    guard await connection.isWifiSyncSupported() else {
      throw WifiSyncServiceError.notSupported
    }

    isSyncing = true
    errorMessage = nil
    status = .off

    // Run the transfer in an owned, cancellable task so stopSync() actually
    // propagates cancellation into the awaiting steps (the handle used to be
    // left nil, so Stop only tore down the TCP socket and left the flow
    // running). The caller still awaits completion and receives thrown errors.
    let task = Task { [weak self] () throws in
      guard let self else { return }
      try await self.performWifiSync(device: device, codec: codec, ssid: ssid, password: password)
    }
    syncTask = task
    defer { syncTask = nil }
    try await task.value
  }

  private func performWifiSync(
    device: BtDevice,
    codec: String,
    ssid: String?,
    password: String?
  ) async throws {
    guard let connection = deviceProvider.activeConnection else {
      throw WifiSyncServiceError.deviceNotConnected
    }

    do {
      // Step 1: Setup WiFi if credentials provided
      if let ssid = ssid, let password = password {
        logger.info("Setting up WiFi credentials...")
        let result = await connection.setupWifiSync(ssid: ssid, password: password)
        guard result.success else {
          throw WifiSyncServiceError.setupFailed(result.errorMessage ?? "Unknown error")
        }
      }

      // Step 2: Start WiFi sync on device
      logger.info("Starting WiFi on device...")
      let started = await connection.startWifiSync()
      guard started else {
        throw WifiSyncServiceError.deviceFailed
      }

      status = .on

      // Step 3: Monitor WiFi status
      startStatusMonitoring(connection: connection)

      // Step 4: Wait for device to be ready
      try await waitForDeviceReady(connection: connection)

      // Step 5: Get storage info and send read command
      let storageList = await connection.getStorageList()
      guard storageList.count >= 2 else {
        throw WifiSyncServiceError.noDataToSync
      }

      let totalBytes = Int(storageList[0])
      let currentOffset = Int(storageList[1])
      let bytesToDownload = totalBytes - currentOffset

      guard bytesToDownload > 0 else {
        logger.info("No data to sync")
        await cleanup()
        return
      }

      // Create WAL
      currentWal = activeWalService.createSdCardWal(
        device: device.id,
        deviceModel: device.type.displayName,
        codec: codec,
        totalBytes: totalBytes,
        currentOffset: currentOffset
      )

      progress = SyncProgress(totalBytes: bytesToDownload)

      // Send read command
      let readSuccess = await connection.writeToStorage(
        fileNum: 1,
        command: StorageCommand.read.rawValue,
        offset: currentOffset
      )

      guard readSuccess else {
        throw WifiSyncServiceError.commandFailed
      }

      // Step 6: Connect to device WiFi AP
      // Note: On macOS, we need to use CWWiFiClient to connect to WiFi
      // For now, assume user has connected manually or use device's auto-generated AP
      logger.info("Connecting to device TCP server...")

      // Bail before opening the socket if Stop was pressed during BLE setup.
      try Task.checkCancellation()

      // Get device IP (typically 192.168.4.1 for ESP32 SoftAP)
      let deviceIP = "192.168.4.1"

      try await connectTCP(host: deviceIP, port: Self.defaultPort)

      status = .tcpConnected
      transferStartTime = Date()

      // Step 7: Receive data
      try await receiveData()

      // Step 8: Finish sync
      await finishSync()

    } catch {
      logger.error("WiFi sync failed: \(error.localizedDescription)")
      errorMessage = error.localizedDescription
      await cleanup()
      throw error
    }
  }

  /// Stop WiFi sync
  func stopSync() {
    syncTask?.cancel()
    statusStreamTask?.cancel()
    tcpConnection?.cancel()

    syncTask = nil
    statusStreamTask = nil
    tcpConnection = nil

    Task {
      await cleanup()
    }
  }

  // MARK: - Private Methods

  private func startStatusMonitoring(connection: DeviceConnection) {
    statusStreamTask = Task { [weak self] in
      let stream = connection.getWifiSyncStatusStream()

      do {
        for try await statusCode in stream {
          guard let self = self else { break }

          if let newStatus = WifiStatus(rawValue: statusCode) {
            await MainActor.run {
              self.status = newStatus
            }
            self.logger.debug("WiFi status: \(newStatus.displayName)")
          }
        }
      } catch {
        self?.logger.debug("Status stream ended: \(error.localizedDescription)")
      }
    }
  }

  private func waitForDeviceReady(connection: DeviceConnection) async throws {
    let startTime = Date()

    while Date().timeIntervalSince(startTime) < Self.connectionTimeout {
      if Task.isCancelled { throw CancellationError() }

      if status.isActive {
        return
      }

      try await Task.sleep(nanoseconds: 500_000_000)  // 0.5 seconds
    }

    throw WifiSyncServiceError.timeout
  }

  private func connectTCP(host: String, port: UInt16) async throws {
    let endpoint = NWEndpoint.hostPort(
      host: NWEndpoint.Host(host),
      port: NWEndpoint.Port(rawValue: port)!
    )

    let connection = NWConnection(to: endpoint, using: .tcp)
    self.tcpConnection = connection

    return try await withCheckedThrowingContinuation { continuation in
      // Resume the continuation directly in each terminal case and clear the
      // handler on first resume so it fires exactly once (no shared mutable
      // state, which strict concurrency rejects across the @Sendable handler).
      connection.stateUpdateHandler = { [weak self] state in
        switch state {
        case .ready:
          self?.logger.info("TCP connection ready")
          connection.stateUpdateHandler = nil
          continuation.resume()

        case .failed(let error):
          self?.logger.error("TCP connection failed: \(error.localizedDescription)")
          connection.stateUpdateHandler = nil
          continuation.resume(throwing: WifiSyncServiceError.connectionFailed)

        case .waiting(let error):
          // The device AP is unreachable (e.g. the Mac never joined it).
          // NWConnection would sit in `.waiting` and retry forever, hanging
          // the sync in "syncing" with no exit but Stop. Fail fast so the
          // user can retry instead.
          self?.logger.error("TCP connection unreachable: \(error.localizedDescription)")
          connection.stateUpdateHandler = nil
          continuation.resume(throwing: WifiSyncServiceError.connectionFailed)

        case .cancelled:
          connection.stateUpdateHandler = nil
          continuation.resume(throwing: CancellationError())

        default:
          break
        }
      }

      connection.start(queue: .main)
    }
  }

  private func receiveData() async throws {
    guard let connection = tcpConnection else {
      throw WifiSyncServiceError.connectionFailed
    }

    downloadedFrames = []
    totalBytesDownloaded = 0
    speedSamples = []
    frameParser = WifiFrameStreamParser()

    var buffer = Data()
    let startTime = Date()

    while Date().timeIntervalSince(startTime) < Self.transferTimeout {
      if Task.isCancelled { throw CancellationError() }

      // Receive data chunk
      let chunk = try await receiveChunk(connection: connection)

      if chunk.isEmpty {
        // End of stream
        break
      }

      buffer.append(chunk)
      totalBytesDownloaded += chunk.count

      // Parse frames from buffer
      let (frames, remaining) = frameParser.parse(buffer)
      buffer = remaining

      downloadedFrames.append(contentsOf: frames)

      // Update progress
      updateProgress()
    }

    // Parse any remaining data
    let (finalFrames, _) = frameParser.parse(buffer)
    downloadedFrames.append(contentsOf: finalFrames)

    logger.info("Received \(self.totalBytesDownloaded) bytes, \(self.downloadedFrames.count) frames")
  }

  private func receiveChunk(connection: NWConnection) async throws -> Data {
    return try await withCheckedThrowingContinuation { continuation in
      connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, isComplete, error in
        if let error = error {
          continuation.resume(throwing: error)
          return
        }

        if isComplete && (data == nil || data!.isEmpty) {
          continuation.resume(returning: Data())
          return
        }

        continuation.resume(returning: data ?? Data())
      }
    }
  }

  private func updateProgress() {
    let now = Date()

    // Add sample for speed calculation
    speedSamples.append((now, totalBytesDownloaded))

    // Remove old samples outside window
    speedSamples.removeAll { now.timeIntervalSince($0.timestamp) > Self.speedWindowSeconds }

    // Calculate speed
    if speedSamples.count >= 2 {
      let oldest = speedSamples.first!
      let newest = speedSamples.last!
      let timeDiff = newest.timestamp.timeIntervalSince(oldest.timestamp)
      let bytesDiff = newest.bytes - oldest.bytes

      if timeDiff > 0 {
        transferSpeed = Double(bytesDiff) / timeDiff
      }
    }

    progress = SyncProgress(
      totalBytes: progress.totalBytes,
      downloadedBytes: totalBytesDownloaded,
      framesDownloaded: downloadedFrames.count,
      bytesPerSecond: transferSpeed
    )
  }

  private func finishSync() async {
    guard let wal = currentWal else { return }

    // Save downloaded data
    activeWalService.updateWalWithDownloadedData(
      walId: wal.id,
      downloadedBytes: totalBytesDownloaded,
      frames: downloadedFrames
    )

    let frameCount = downloadedFrames.count

    // Tear down the device SoftAP first so the Mac can regain its normal
    // internet route before uploading downloaded WALs to cloud.
    await cleanup()

    await activeWalService.syncToCloud()

    logger.info("WiFi sync completed: \(frameCount) frames")
  }

  /// Test seam: exercise finishSync without a live device/TCP session.
  func finishSyncForTesting(wal: WALEntry, frames: [Data], downloadedBytes: Int) async {
    currentWal = wal
    downloadedFrames = frames
    totalBytesDownloaded = downloadedBytes
    await finishSync()
  }

  private func cleanup() async {
    statusStreamTask?.cancel()
    statusStreamTask = nil

    tcpConnection?.cancel()
    tcpConnection = nil

    // Stop WiFi on device
    if let connection = deviceProvider.activeConnection {
      _ = await connection.stopWifiSync()
    }

    // Drop the reserved SD-card WAL if this sync downloaded nothing, so a
    // failed/aborted transfer doesn't leave a permanent phantom 'pending' entry.
    if let wal = currentWal {
      activeWalService.removeSdCardWalIfEmpty(walId: wal.id)
    }

    isSyncing = false
    status = .off
    currentWal = nil
    downloadedFrames = []
    totalBytesDownloaded = 0
    transferSpeed = 0
    speedSamples = []
  }
}

// MARK: - WiFi Sync Errors

enum WifiSyncServiceError: LocalizedError {
  case deviceNotConnected
  case notSupported
  case setupFailed(String)
  case deviceFailed
  case noDataToSync
  case commandFailed
  case connectionFailed
  case timeout
  case transferFailed(String)

  var errorDescription: String? {
    switch self {
    case .deviceNotConnected:
      return "Device not connected"
    case .notSupported:
      return "Device does not support WiFi sync"
    case .setupFailed(let reason):
      return "WiFi setup failed: \(reason)"
    case .deviceFailed:
      return "Device failed to start WiFi"
    case .noDataToSync:
      return "No data available to sync"
    case .commandFailed:
      return "Failed to send command to device"
    case .connectionFailed:
      return "Failed to connect to device WiFi"
    case .timeout:
      return "Connection timed out"
    case .transferFailed(let reason):
      return "Transfer failed: \(reason)"
    }
  }
}
