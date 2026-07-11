import Combine
import Foundation
import OmiSupport
import OmiWAL
import os.log

// MARK: - WAL Persistence State

enum WALPersistenceState: Equatable {
    case ready
    case degraded(reason: String)
}

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
    static let lossesThresholdFrames = 10 * 100 // 10 seconds at 100 fps

    /// SD card chunk duration
    static let sdcardChunkSizeSeconds = 60

    // MARK: - Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "WALService")
    private let fileManager = FileManager.default
    private let apiClient: APIClient
    private let reconciler: WALSyncReconciler
    private var frameWriteInProgress = false

    /// Test seam — when set, bypasses `APIClient.uploadLocalFilesV2`.
    var uploadLocalFilesHandler: ((URL) async throws -> UploadLocalFilesResult)?

    /// Test-only: point WAL I/O at a temp directory.
    func setWalDirectoryForTesting(_ url: URL?) {
        walDirectory = url
        if url != nil {
            persistenceState = .ready
        }
    }

    func setWalsForTesting(_ entries: [WALEntry]) {
        wals = entries
    }

    func uploadWalToCloudForTesting(_ wal: WALEntry) async throws {
        try await uploadWalToCloud(wal)
    }

    func flushToDiskForTesting() {
        flushToDisk()
    }

    func createWalFromCurrentFramesForTesting() {
        createWalFromCurrentFrames()
    }

    var currentFrameCountForTesting: Int {
        currentFrames.count
    }

    private var walDirectory: URL?
    private var directoryRecreateAttempts = 0
    private let maxDirectoryRecreateAttempts = 3
    private var flushTimer: Timer?
    private var chunkTimer: Timer?

    // In-memory frame buffer for current recording
    private var currentFrames: [Data] = []
    private var currentFramesSynced: [Bool] = []
    private var currentDevice: String?
    private var currentCodec: String?
    private var recordingStartTime: Int?

    // MARK: - Initialization

    init(
        apiClient: APIClient = .shared,
        reconciler: WALSyncReconciler = .shared
    ) {
        self.apiClient = apiClient
        self.reconciler = reconciler
        setupWalDirectory()
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
        // `.uploaded` stays pending (in-flight) until reconciler transitions it
        // to `.synced` or back to `.miss`, so it doesn't vanish from the count
        // while a background job is still processing.
        pendingWals = wals.filter { $0.status == .miss || $0.status == .inProgress || $0.status == .uploaded }
    }

    // MARK: - Frame Recording

    /// Start recording frames from a device
    func startRecording(device: String, codec: String) {
        // Best-effort flush of frames retained after a prior degraded stop.
        // If the retry fails again, preserve the frames in-memory rather than
        // silently dropping them — they'll be retried on the next flush.
        if !currentFrames.isEmpty {
            _ = createWalFromCurrentFrames()
        }

        currentDevice = device
        currentCodec = codec
        // Only clear the frame buffer if the retained flush succeeded (or there
        // were none to flush). Dropping frames on a failed retry would lose audio.
        if currentFrames.isEmpty {
            currentFrames = []
            currentFramesSynced = []
        }
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

        // Create WAL for remaining frames. On write failure, frames stay in
        // `currentFrames` so a later start/retry can persist them — do not clear.
        if !currentFrames.isEmpty {
            _ = createWalFromCurrentFrames()
        }

        if currentFrames.isEmpty {
            currentDevice = nil
            currentCodec = nil
            currentFramesSynced = []
            recordingStartTime = nil
        } else {
            log(
                "WALService: stopRecording retained \(currentFrames.count) in-memory frames "
                    + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded)")
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

    @discardableResult
    private func createWalFromCurrentFrames() -> Bool {
        guard let device = currentDevice,
              let codec = currentCodec,
              let startTime = recordingStartTime,
              !currentFrames.isEmpty else { return true }
        guard !frameWriteInProgress else { return true }

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

        // Check for duplicate. Two chunks can share a WAL id ("device_second", 1s
        // resolution) when a second chunk is created within the same wall-clock
        // second as a prior successful write. They share generateFileName(), so the
        // duplicate write MUST extend the existing file (append: true below), not
        // atomically overwrite it — overwriting truncated the earlier ~60s of audio
        // to just the new buffer while totalFrames claimed the sum.
        let existingIndex = wals.firstIndex(where: { $0.id == wal.id })
        if let existingIndex {
            wals[existingIndex].totalFrames += currentFrames.count
            logger.debug("Appended \(self.currentFrames.count) frames to existing WAL")
        } else {
            wals.append(wal)
            logger.info("Created new WAL: \(wal.id) with \(self.currentFrames.count) frames")
        }

        let framesToWrite = currentFrames
        let syncedToWrite = currentFramesSynced
        frameWriteInProgress = true
        writeFramesToDiskAsync(frames: framesToWrite, wal: wal, append: existingIndex != nil) {
            [weak self] wrote in
            guard let self else { return }
            self.frameWriteInProgress = false
            guard wrote else {
                self.errorMessage = "Failed to save audio backup. Recording continues in memory."
                log(
                    "WALService: frame write failed — retaining \(framesToWrite.count) in-memory frames "
                        + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded)")
                // writeFramesToDiskAsync already recorded the health event via
                // recordFrameWriteFailure — do not duplicate it here.
                self.updatePendingWals()
                return
            }

            // Clear only the frames that were durably written (#9240). New frames
            // may have arrived while the off-main write was in flight.
            let writtenCount = framesToWrite.count
            if self.currentFrames.count >= writtenCount {
                self.currentFrames.removeFirst(writtenCount)
            } else {
                self.currentFrames = []
            }
            let syncedCount = min(syncedToWrite.count, self.currentFramesSynced.count)
            if syncedCount > 0 {
                self.currentFramesSynced.removeFirst(syncedCount)
            }
            self.recordingStartTime = Int(Date().timeIntervalSince1970)
            self.updatePendingWals()
            self.saveWals()
        }

        updatePendingWals()
        return true
    }

    /// Length-prefix encode frames into the on-disk WAL chunk byte layout
    /// (`UInt32 little-endian length + frame bytes`, repeated).
    static func encodeFrames(_ frames: [Data]) -> Data {
        var fileData = Data()
        for frame in frames {
            var length = UInt32(frame.count).littleEndian
            fileData.append(Data(bytes: &length, count: 4))
            fileData.append(frame)
        }
        return fileData
    }

    /// Bytes to write for a WAL chunk. When `append` is set and the file already
    /// has content, the new frames EXTEND it — a duplicate WAL id (same
    /// device+second) must never atomically overwrite the earlier frames, which
    /// destroyed the previously-recorded audio.
    static func frameFileBytes(existing: Data?, frames: [Data], append: Bool) -> Data {
        let encoded = encodeFrames(frames)
        if append, let existing, !existing.isEmpty {
            return existing + encoded
        }
        return encoded
    }

    private func writeFramesToDiskAsync(
        frames: [Data],
        wal: WALEntry,
        append: Bool = false,
        completion: @escaping @MainActor (Bool) -> Void
    ) {
        guard let walDir = walDirectory else {
            recordFrameWriteFailure(walId: wal.id, reason: "wal_directory_unavailable")
            completion(false)
            return
        }

        let fileName = wal.generateFileName()
        let fileUrl = walDir.appendingPathComponent(fileName)
        let walId = wal.id

        let frameCount = frames.count
        DispatchQueue.global(qos: .utility).async { [weak self, frames] in
            // On a duplicate-id append, read the already-persisted frames off the
            // main thread and extend them; a failed atomic write leaves the prior
            // file untouched.
            let existing = append ? try? Data(contentsOf: fileUrl) : nil
            let fileData = Self.frameFileBytes(existing: existing, frames: frames, append: append)
            let succeeded: Bool
            let failureReason: String?
            do {
                try fileData.write(to: fileUrl, options: .atomic)
                log("WALService: Wrote \(frameCount) frames to \(fileName)")
                succeeded = true
                failureReason = nil
            } catch {
                let reason = error.localizedDescription
                log(
                    "WALService: Failed to write frames to disk "
                        + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded): "
                        + reason)
                succeeded = false
                failureReason = reason
            }

            DispatchQueue.main.async {
                guard let self else { return }
                if succeeded, let index = self.wals.firstIndex(where: { $0.id == walId }) {
                    self.wals[index].storage = .disk
                    self.wals[index].filePath = fileName
                    completion(true)
                } else {
                    self.recordFrameWriteFailure(walId: walId, reason: failureReason ?? "frame_write_failed")
                    completion(false)
                }
            }
        }
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

        let frameCount = frames.count

        // Write to disk on background thread to avoid blocking the main actor.
        // The completion handler hops back to main to set filePath — callers that
        // need filePath set before proceeding should use writeFramesToDiskAndWait.
        DispatchQueue.global(qos: .utility).async { [weak self] in
            do {
                try fileData.write(to: fileUrl, options: .atomic)
                log("WALService: Wrote \(frameCount) frames to \(fileName)")

                DispatchQueue.main.async {
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
                DispatchQueue.main.async {
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

        let frameCount = frames.count
        let group = DispatchGroup()
        var writeSucceeded = false
        group.enter()
        DispatchQueue.global(qos: .utility).async {
            do {
                try fileData.write(to: fileUrl, options: .atomic)
                log("WALService: Wrote \(frameCount) frames to \(fileName)")
                writeSucceeded = true
            } catch {
                let reason = error.localizedDescription
                log(
                    "WALService: Failed to write frames to disk "
                        + "(failure_class=wal_write_failed recovery_action=retain_frames recovery_result=degraded): "
                        + reason)
                writeSucceeded = false
            }
            group.leave()
        }
        group.wait()

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

        var workingWals = wals
        if await reconciler.reconcileUploadedWals(wals: &workingWals, walDirectory: walDirectory) {
            wals = workingWals
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
              let filePath = wal.filePath else {
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
