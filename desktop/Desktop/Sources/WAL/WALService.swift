import Combine
import Foundation
import os.log

// MARK: - WAL Service

/// Main coordinator for Write-Ahead Log sync operations
/// Manages local WAL storage and coordinates sync with device and cloud
/// Ported from: omi/app/lib/services/wals/wal_service.dart
@MainActor
final class WALService: ObservableObject {

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

    // MARK: - Constants

    /// Chunk duration in seconds (create WAL every N seconds)
    static let chunkSizeInSeconds = 60

    /// Flush interval in seconds (write in-memory WALs to disk)
    static let flushIntervalInSeconds = 90

    /// Delay before processing new frames
    static let newFrameSyncDelaySeconds = 15

    /// Minimum frames to trigger a WAL creation (10 seconds worth)
    static let lossesThresholdFrames = 10 * 100 // 10 seconds at 100 fps

    /// SD card chunk duration
    static let sdcardChunkSizeSeconds = 60

    // MARK: - Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "WALService")
    private let fileManager = FileManager.default

    private var walDirectory: URL?
    private var flushTimer: Timer?
    private var chunkTimer: Timer?

    // In-memory frame buffer for current recording
    private var currentFrames: [Data] = []
    private var currentFramesSynced: [Bool] = []
    private var currentDevice: String?
    private var currentCodec: String?
    private var recordingStartTime: Int?

    // MARK: - Initialization

    private init() {
        setupWalDirectory()
        loadWals()
    }

    // MARK: - Directory Setup

    private func setupWalDirectory() {
        guard let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            logger.error("Could not find Application Support directory")
            return
        }

        let walDir = appSupport.appendingPathComponent("me.omi.desktop/wals", isDirectory: true)

        do {
            try fileManager.createDirectory(at: walDir, withIntermediateDirectories: true)
            walDirectory = walDir
            logger.info("WAL directory: \(walDir.path)")
        } catch {
            logger.error("Failed to create WAL directory: \(error.localizedDescription)")
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
        guard let file = walMetadataFile, fileManager.fileExists(atPath: file.path) else {
            logger.info("No existing WAL metadata found")
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
            // Try backup
            loadFromBackup()
        }
    }

    private func loadFromBackup() {
        guard let backup = walBackupFile, fileManager.fileExists(atPath: backup.path) else {
            return
        }

        do {
            let data = try Data(contentsOf: backup)
            let metadata = try JSONDecoder().decode(WALMetadata.self, from: data)
            wals = metadata.wals
            updatePendingWals()
            logger.info("Loaded \(self.wals.count) WALs from backup")
        } catch {
            logger.error("Failed to load WALs from backup: \(error.localizedDescription)")
        }
    }

    /// Save WALs to disk with backup (file I/O runs on background thread)
    func saveWals() {
        guard let file = walMetadataFile, let backup = walBackupFile else { return }

        do {
            // Encode on main thread (accesses @Published wals)
            let metadata = WALMetadata(wals: wals)
            let data = try JSONEncoder().encode(metadata)

            // Write to disk on background thread to avoid blocking UI
            DispatchQueue.global(qos: .utility).async {
                do {
                    // Create backup first
                    if FileManager.default.fileExists(atPath: file.path) {
                        try? FileManager.default.removeItem(at: backup)
                        try FileManager.default.copyItem(at: file, to: backup)
                    }

                    try data.write(to: file, options: .atomic)
                } catch {
                    log("WALService: Failed to save WALs: \(error.localizedDescription)")
                }
            }

            logger.debug("Saved \(self.wals.count) WALs to disk")
        } catch {
            logger.error("Failed to encode WALs: \(error.localizedDescription)")
        }
    }

    private func updatePendingWals() {
        pendingWals = wals.filter { $0.status == .miss || $0.status == .inProgress }
    }

    // MARK: - Frame Recording

    /// Start recording frames from a device
    func startRecording(device: String, codec: String) {
        currentDevice = device
        currentCodec = codec
        currentFrames = []
        currentFramesSynced = []
        recordingStartTime = Int(Date().timeIntervalSince1970)

        startTimers()
        logger.info("Started recording from device: \(device), codec: \(codec)")
    }

    /// Add a frame to the current recording
    func addFrame(_ frame: Data, synced: Bool = false) {
        currentFrames.append(frame)
        currentFramesSynced.append(synced)
    }

    /// Stop recording and create final WAL
    func stopRecording() {
        stopTimers()

        // Create WAL for remaining frames
        if !currentFrames.isEmpty {
            createWalFromCurrentFrames()
        }

        currentDevice = nil
        currentCodec = nil
        currentFrames = []
        currentFramesSynced = []
        recordingStartTime = nil

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
        let unsyncedCount = currentFramesSynced.filter { !$0 }.count

        if unsyncedCount >= Self.lossesThresholdFrames {
            createWalFromCurrentFrames()
        }
    }

    private func flushToDisk() {
        // Write any in-memory WALs to disk
        for i in 0..<wals.count {
            if wals[i].storage == .memory {
                writeWalToDisk(at: i)
            }
        }
        saveWals()
    }

    private func createWalFromCurrentFrames() {
        guard let device = currentDevice,
              let codec = currentCodec,
              let startTime = recordingStartTime,
              !currentFrames.isEmpty else { return }

        // Calculate actual duration based on frames
        let framesPerSecond = codec == "opus_fs320" ? 50 : 100
        let seconds = max(1, currentFrames.count / framesPerSecond)

        let wal = WALEntry(
            timerStart: startTime,
            codec: codec,
            status: .miss,
            storage: .memory,
            seconds: seconds,
            device: device,
            deviceModel: device,
            totalFrames: currentFrames.count
        )

        // Check for duplicate
        if let existingIndex = wals.firstIndex(where: { $0.id == wal.id }) {
            // Append to existing
            wals[existingIndex].totalFrames += currentFrames.count
            logger.debug("Appended \(self.currentFrames.count) frames to existing WAL")
        } else {
            wals.append(wal)
            logger.info("Created new WAL: \(wal.id) with \(self.currentFrames.count) frames")
        }

        // Write frames to disk
        writeFramesToDisk(frames: currentFrames, wal: wal)

        // Clear current frames
        currentFrames = []
        currentFramesSynced = []
        recordingStartTime = Int(Date().timeIntervalSince1970)

        updatePendingWals()
        saveWals()
    }

    private func writeFramesToDisk(frames: [Data], wal: WALEntry) {
        guard let walDir = walDirectory else { return }

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

        let frameCount = frames.count

        // Write to disk on background thread to avoid blocking UI
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                try fileData.write(to: fileUrl, options: .atomic)
                log("WALService: Wrote \(frameCount) frames to \(fileName)")

                // Update WAL state back on main thread
                DispatchQueue.main.async {
                    if let index = self?.wals.firstIndex(where: { $0.id == walId }) {
                        self?.wals[index].storage = .disk
                        self?.wals[index].filePath = fileName
                    }
                }
            } catch {
                log("WALService: Failed to write frames to disk: \(error.localizedDescription)")
            }
        }
    }

    private func writeWalToDisk(at index: Int) {
        // For in-memory WALs that don't have frames here, just mark as disk
        // In a full implementation, this would write buffered frames
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
        let timerStart = Int(Date().timeIntervalSince1970)
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

    /// Update WAL with downloaded data
    func updateWalWithDownloadedData(walId: String, downloadedBytes: Int, frames: [Data]) {
        guard let index = wals.firstIndex(where: { $0.id == walId }) else {
            logger.warning("WAL not found for update: \(walId)")
            return
        }

        wals[index].storageOffset += downloadedBytes
        wals[index].totalFrames = frames.count

        // Write frames to disk
        writeFramesToDisk(frames: frames, wal: wals[index])

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
            } catch {
                logger.error("Failed to sync WAL \(wal.id): \(error.localizedDescription)")
            }
        }
    }

    private func uploadWalToCloud(_ wal: WALEntry) async throws {
        guard let walDir = walDirectory,
              let filePath = wal.filePath else {
            throw WALError.fileNotFound
        }

        let fileUrl = walDir.appendingPathComponent(filePath)

        guard fileManager.fileExists(atPath: fileUrl.path) else {
            throw WALError.fileNotFound
        }

        // Read file data
        let fileData = try Data(contentsOf: fileUrl)

        // Parse frames from file
        let frames = parseFramesFromFile(fileData)

        guard !frames.isEmpty else {
            throw WALError.noFramesToUpload
        }

        // Convert frames to PCM and create segments
        // For now, log what would be uploaded
        logger.info("Would upload WAL \(wal.id): \(frames.count) frames, \(fileData.count) bytes")

        // TODO: Integrate with transcription service and API
        // 1. Decode Opus frames to PCM
        // 2. Run through transcription
        // 3. Upload conversation to API

        // Mark as synced
        if let index = wals.firstIndex(where: { $0.id == wal.id }) {
            wals[index].status = .synced
        }

        updatePendingWals()
        saveWals()
    }

    private func parseFramesFromFile(_ data: Data) -> [Data] {
        var frames: [Data] = []
        var offset = 0

        while offset + 4 <= data.count {
            // Read frame length (little-endian uint32)
            let length = Int(data[offset]) |
                        (Int(data[offset + 1]) << 8) |
                        (Int(data[offset + 2]) << 16) |
                        (Int(data[offset + 3]) << 24)
            offset += 4

            guard length > 0, offset + length <= data.count else {
                break
            }

            let frame = data.subdata(in: offset..<(offset + length))
            frames.append(frame)
            offset += length
        }

        return frames
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
