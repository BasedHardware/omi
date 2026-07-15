import AppKit
import AVFoundation
import Foundation

/// Coordinates the capture → storage → database → OCR pipeline for Rewind
actor RewindIndexer {
    static let shared = RewindIndexer()

    private var isInitialized = false
    private var isInitializing = false

    /// OCR frequency: only run OCR every Nth frame to reduce CPU
    private var framesSinceLastOCR = 0
    private let ocrEveryNthFrame = 3

    /// OCR stats for periodic logging
    private var statsTotalFrames = 0
    private var statsOCRRan = 0
    private var statsSkippedFrequency = 0
    private var statsSkippedDedup = 0
    private var statsLastLogTime = Date()
    private let statsLogInterval: TimeInterval = 60

    /// Drop repeated static captures, but keep periodic anchors so long-running
    /// unchanged screens still appear in the timeline.
    private let frameDedupeMaxInterval: TimeInterval = 30.0
    private var lastEncodedFrameSignature: FrameDedupeSignature?
    private var lastEncodedFrameTimestamp: Date?

    /// Backoff state for initialization retries
    private var initFailureCount = 0
    private var nextRetryTime: Date = .distantPast
    private static let maxBackoffSeconds: Double = 300 // Cap at 5 minutes

    /// Retention enforcement: prune screenshots/video older than the user's
    /// `rewindRetentionDays` setting. `.distantPast` means the first frame after
    /// launch runs cleanup immediately; afterwards it runs at most every 6h.
    private var lastRetentionCleanupAt: Date = .distantPast
    private let retentionCleanupInterval: TimeInterval = 6 * 60 * 60
    private var isRetentionCleanupRunning = false

    // MARK: - Initialization

    private init() {}

    /// Reset the indexer state so it re-initializes on the next frame.
    /// Called during sign-out to avoid stale `isInitialized = true` after the database is closed.
    func reset() {
        isInitialized = false
        isInitializing = false
        initFailureCount = 0
        nextRetryTime = .distantPast
        lastEncodedFrameSignature = nil
        lastEncodedFrameTimestamp = nil
        log("RewindIndexer: Reset (will re-initialize on next frame)")
    }

    /// Initialize all Rewind services
    func initialize() async throws {
        guard !isInitialized, !isInitializing else { return }
        isInitializing = true
        defer { isInitializing = false }

        log("RewindIndexer: Initializing...")

        // Initialize database
        try await RewindDatabase.shared.initialize()

        // Initialize storage
        try await RewindStorage.shared.initialize()

        isInitialized = true
        initFailureCount = 0
        log("RewindIndexer: Initialized successfully")

        // Set up power monitor to backfill OCR when AC reconnects
        setupPowerMonitorCallback()

        // Kick off OCR embedding backfill in background
        Task(priority: .background) {
            await OCREmbeddingService.shared.backfillIfNeeded()
        }

        // Reduce ocrDataJson float precision for existing rows (one-time migration)
        Task(priority: .background) {
            await RewindDatabase.shared.reduceOCRDataPrecisionIfNeeded()
        }
    }

    /// Try to initialize with exponential backoff. Returns true if initialized.
    func ensureInitialized() async -> Bool {
        if isInitialized {
            // The database is the authoritative readiness signal. It closes its own
            // pool after repeated I/O/corruption errors (RewindDatabase.reportQueryError);
            // this cached flag then goes stale and every frame fails with
            // databaseNotInitialized until periodic cleanup reopens it up to 6h later.
            // Revalidate against the database and drop the stale flag so this frame
            // reopens it through the normal backoff path below.
            if await RewindDatabase.shared.isInitialized {
                return true
            }
            isInitialized = false
            log("RewindIndexer: Database closed after initialization (self-recovery); reinitializing")
        }

        // Check backoff timer - skip if too soon after last failure
        if Date() < nextRetryTime {
            return false
        }

        do {
            try await initialize()
            return true
        } catch {
            initFailureCount += 1
            // Exponential backoff: 2s, 4s, 8s, 16s, ... capped at 5 minutes
            let backoffSeconds = min(pow(2.0, Double(initFailureCount)), Self.maxBackoffSeconds)
            nextRetryTime = Date().addingTimeInterval(backoffSeconds)

            // First 3 failures: send to Sentry for diagnostics (logError).
            // After that: log locally only (log) to avoid flooding Sentry with a known-dead DB.
            if initFailureCount <= 3 {
                logError("RewindIndexer: Failed to initialize (attempt \(initFailureCount), next retry in \(Int(backoffSeconds))s): \(error)")
            } else if initFailureCount % 10 == 0 {
                log("RewindIndexer: Still failing to initialize (attempt \(initFailureCount), next retry in \(Int(backoffSeconds))s)")
            }
            return false
        }
    }

    // MARK: - OCR Stats

    private enum OCROutcome { case ran, skippedFrequency, skippedDedup }

    private func recordOCROutcome(_ outcome: OCROutcome) {
        statsTotalFrames += 1
        switch outcome {
        case .ran: statsOCRRan += 1
        case .skippedFrequency: statsSkippedFrequency += 1
        case .skippedDedup: statsSkippedDedup += 1
        }

        let now = Date()
        if now.timeIntervalSince(statsLastLogTime) >= statsLogInterval {
            let parts = ["\(statsTotalFrames) frames", "\(statsOCRRan) OCR'd", "\(statsSkippedFrequency) skipped (frequency)", "\(statsSkippedDedup) skipped (dedup)"]
            log("RewindIndexer: Last \(Int(statsLogInterval))s — \(parts.joined(separator: ", "))")
            statsTotalFrames = 0
            statsOCRRan = 0
            statsSkippedFrequency = 0
            statsSkippedDedup = 0
            statsLastLogTime = now
        }
    }

    private func makeFrameDedupeSignature(cgImage: CGImage, appName: String, windowTitle: String?) -> FrameDedupeSignature {
        FrameDedupeSignature(
            fingerprint: RewindOCRService.dHash(of: cgImage),
            width: cgImage.width,
            height: cgImage.height,
            appName: appName,
            windowTitle: windowTitle
        )
    }

    private func shouldSkipFrameForDedupe(_ signature: FrameDedupeSignature, timestamp: Date) async -> Bool {
        guard await VideoChunkEncoder.shared.hasFinalizedChunkForDedupe() else {
            return false
        }

        guard let lastSignature = lastEncodedFrameSignature,
              let lastTimestamp = lastEncodedFrameTimestamp,
              signature == lastSignature
        else {
            return false
        }

        return timestamp.timeIntervalSince(lastTimestamp) <= frameDedupeMaxInterval
    }

    private func markFrameEncodedForDedupe(_ signature: FrameDedupeSignature, timestamp: Date) {
        lastEncodedFrameSignature = signature
        lastEncodedFrameTimestamp = timestamp
    }

    private func hasMetadata(focusStatus: String?, extractedTasks: [String]?, insight: String?) -> Bool {
        if focusStatus != nil { return true }
        if extractedTasks?.isEmpty == false { return true }
        if insight?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false { return true }
        return false
    }

    // MARK: - Frame Processing

    /// Process a captured frame from ProactiveAssistantsPlugin
    func processFrame(_ frame: CapturedFrame) async {
        // Ensure initialized with backoff
        guard await ensureInitialized() else { return }
        scheduleRetentionCleanupIfDue()

        do {
            // Convert JPEG to CGImage for video encoding.
            // Wrap in autoreleasepool so the NSImage and its internal Obj-C
            // representations are released promptly instead of accumulating.
            let cgImage: CGImage? = autoreleasepool {
                guard let nsImage = NSImage(data: frame.jpegData) else { return nil }
                return nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
            }

            guard let cgImage = cgImage else {
                logError("RewindIndexer: Failed to create CGImage from frame data")
                return
            }

            let dedupeSignature = makeFrameDedupeSignature(cgImage: cgImage, appName: frame.appName, windowTitle: frame.windowTitle)
            if await shouldSkipFrameForDedupe(dedupeSignature, timestamp: frame.captureTime) {
                return
            }

            // Add frame to video encoder
            let encodedFrame = try await VideoChunkEncoder.shared.addFrame(
                image: cgImage,
                timestamp: frame.captureTime
            )

            // Frame was dropped by encoder (e.g. aspect ratio debounce) — skip DB insert
            // since there's no video chunk to load later
            guard let encodedFrame = encodedFrame else { return }

            // OCR gating: throttle frequency, deduplicate, then check battery
            var ocrText: String?
            var ocrDataJson: String?
            var isIndexed = false

            framesSinceLastOCR += 1
            if framesSinceLastOCR < ocrEveryNthFrame {
                recordOCROutcome(.skippedFrequency)
                isIndexed = true
            } else if await RewindOCRService.shared.shouldSkipOCR(for: cgImage) {
                recordOCROutcome(.skippedDedup)
                isIndexed = true
            } else {
                framesSinceLastOCR = 0
                recordOCROutcome(.ran)
                do {
                    let ocrResult = try await Task(priority: .utility) {
                        try await RewindOCRService.shared.extractTextWithBounds(from: cgImage)
                    }.value
                    ocrText = ocrResult.fullText
                    if let data = try? JSONEncoder().encode(ocrResult) {
                        ocrDataJson = String(data: data, encoding: .utf8)
                    }
                    isIndexed = true
                } catch {
                    logError("RewindIndexer: OCR failed for frame: \(error)")
                }
            }

            // Create database record with video reference and OCR results
            let screenshot = Screenshot(
                timestamp: frame.captureTime,
                appName: frame.appName,
                windowTitle: frame.windowTitle,
                imagePath: "",
                videoChunkPath: encodedFrame.videoChunkPath,
                frameOffset: encodedFrame.frameOffset,
                ocrText: ocrText,
                ocrDataJson: ocrDataJson,
                isIndexed: isIndexed
            )

            let inserted = try await RewindDatabase.shared.insertScreenshot(screenshot)
            markFrameEncodedForDedupe(dedupeSignature, timestamp: frame.captureTime)

            // Embed OCR text for semantic search (non-blocking)
            if let ocrText = ocrText, !ocrText.isEmpty, let id = inserted.id {
                Task(priority: .utility) {
                    await OCREmbeddingService.shared.embedScreenshot(id: id, ocrText: ocrText, appName: frame.appName, windowTitle: frame.windowTitle)
                }
            }

            // Notify that a new frame was captured (for live UI updates)
            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .rewindFrameCaptured, object: nil)
            }

        } catch {
            logError("RewindIndexer: Failed to process frame: \(error)")
            await RewindDatabase.shared.reportQueryError(error)
        }
    }

    /// Process a frame directly from a CGImage (macOS 14+ path, avoids JPEG decode round-trip)
    func processFrame(cgImage: CGImage, appName: String, windowTitle: String?, captureTime: Date) async {
        guard await ensureInitialized() else { return }
        scheduleRetentionCleanupIfDue()

        do {
            let dedupeSignature = makeFrameDedupeSignature(cgImage: cgImage, appName: appName, windowTitle: windowTitle)
            if await shouldSkipFrameForDedupe(dedupeSignature, timestamp: captureTime) {
                return
            }

            // Add frame to video encoder (CGImage directly, no decode needed)
            let encodedFrame = try await VideoChunkEncoder.shared.addFrame(
                image: cgImage,
                timestamp: captureTime
            )

            // Frame was dropped by encoder (e.g. aspect ratio debounce) — skip DB insert
            guard let encodedFrame = encodedFrame else { return }

            // OCR gating: throttle frequency, deduplicate, then check battery
            var ocrText: String?
            var ocrDataJson: String?
            var isIndexed = false

            framesSinceLastOCR += 1
            if framesSinceLastOCR < ocrEveryNthFrame {
                recordOCROutcome(.skippedFrequency)
                isIndexed = true
            } else if await RewindOCRService.shared.shouldSkipOCR(for: cgImage) {
                recordOCROutcome(.skippedDedup)
                isIndexed = true
            } else {
                framesSinceLastOCR = 0
                recordOCROutcome(.ran)
                do {
                    let ocrResult = try await Task(priority: .utility) {
                        try await RewindOCRService.shared.extractTextWithBounds(from: cgImage)
                    }.value
                    ocrText = ocrResult.fullText
                    if let data = try? JSONEncoder().encode(ocrResult) {
                        ocrDataJson = String(data: data, encoding: .utf8)
                    }
                    isIndexed = true
                } catch {
                    logError("RewindIndexer: OCR failed for CGImage frame: \(error)")
                }
            }

            let screenshot = Screenshot(
                timestamp: captureTime,
                appName: appName,
                windowTitle: windowTitle,
                imagePath: "",
                videoChunkPath: encodedFrame.videoChunkPath,
                frameOffset: encodedFrame.frameOffset,
                ocrText: ocrText,
                ocrDataJson: ocrDataJson,
                isIndexed: isIndexed
            )

            let inserted = try await RewindDatabase.shared.insertScreenshot(screenshot)
            markFrameEncodedForDedupe(dedupeSignature, timestamp: captureTime)

            // Embed OCR text for semantic search (non-blocking)
            if let ocrText = ocrText, !ocrText.isEmpty, let id = inserted.id {
                Task(priority: .utility) {
                    await OCREmbeddingService.shared.embedScreenshot(id: id, ocrText: ocrText, appName: appName, windowTitle: windowTitle)
                }
            }

            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .rewindFrameCaptured, object: nil)
            }

        } catch {
            logError("RewindIndexer: Failed to process CGImage frame: \(error)")
            await RewindDatabase.shared.reportQueryError(error)
        }
    }

    /// Process a frame with additional metadata (focus status, etc.)
    func processFrame(_ frame: CapturedFrame, focusStatus: String?, extractedTasks: [String]?, insight: String?) async {
        guard await ensureInitialized() else { return }
        scheduleRetentionCleanupIfDue()

        do {
            // Convert JPEG to CGImage for video encoding.
            // Wrap in autoreleasepool so the NSImage and its internal Obj-C
            // representations are released promptly instead of accumulating.
            let cgImage: CGImage? = autoreleasepool {
                guard let nsImage = NSImage(data: frame.jpegData) else { return nil }
                return nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
            }

            guard let cgImage = cgImage else {
                logError("RewindIndexer: Failed to create CGImage from frame data")
                return
            }

            let dedupeSignature = makeFrameDedupeSignature(cgImage: cgImage, appName: frame.appName, windowTitle: frame.windowTitle)
            let carriesMetadata = hasMetadata(focusStatus: focusStatus, extractedTasks: extractedTasks, insight: insight)
            if !carriesMetadata, await shouldSkipFrameForDedupe(dedupeSignature, timestamp: frame.captureTime) {
                return
            }

            // Add frame to video encoder
            let encodedFrame = try await VideoChunkEncoder.shared.addFrame(
                image: cgImage,
                timestamp: frame.captureTime
            )

            // Frame was dropped by encoder (e.g. aspect ratio debounce) — skip DB insert
            guard let encodedFrame = encodedFrame else { return }

            // OCR gating: throttle frequency, deduplicate, then check battery
            var ocrText: String?
            var ocrDataJson: String?
            var isIndexed = false

            framesSinceLastOCR += 1
            if framesSinceLastOCR < ocrEveryNthFrame {
                recordOCROutcome(.skippedFrequency)
                isIndexed = true
            } else if await RewindOCRService.shared.shouldSkipOCR(for: cgImage) {
                recordOCROutcome(.skippedDedup)
                isIndexed = true
            } else {
                framesSinceLastOCR = 0
                recordOCROutcome(.ran)
                do {
                    let ocrResult = try await Task(priority: .utility) {
                        try await RewindOCRService.shared.extractTextWithBounds(from: cgImage)
                    }.value
                    ocrText = ocrResult.fullText
                    if let data = try? JSONEncoder().encode(ocrResult) {
                        ocrDataJson = String(data: data, encoding: .utf8)
                    }
                    isIndexed = true
                } catch {
                    logError("RewindIndexer: OCR failed for frame with metadata: \(error)")
                }
            }

            // Encode tasks and insight as JSON
            var tasksJson: String?
            if let tasks = extractedTasks, !tasks.isEmpty {
                let data = try JSONEncoder().encode(tasks)
                tasksJson = String(data: data, encoding: .utf8)
            }

            let adviceJson: String? = insight

            let screenshot = Screenshot(
                timestamp: frame.captureTime,
                appName: frame.appName,
                windowTitle: frame.windowTitle,
                imagePath: "",
                videoChunkPath: encodedFrame.videoChunkPath,
                frameOffset: encodedFrame.frameOffset,
                ocrText: ocrText,
                ocrDataJson: ocrDataJson,
                isIndexed: isIndexed,
                focusStatus: focusStatus,
                extractedTasksJson: tasksJson,
                adviceJson: adviceJson
            )

            let inserted = try await RewindDatabase.shared.insertScreenshot(screenshot)
            if !carriesMetadata {
                markFrameEncodedForDedupe(dedupeSignature, timestamp: frame.captureTime)
            }

            // Embed OCR text for semantic search (non-blocking)
            if let ocrText = ocrText, !ocrText.isEmpty, let id = inserted.id {
                Task(priority: .utility) {
                    await OCREmbeddingService.shared.embedScreenshot(id: id, ocrText: ocrText, appName: frame.appName, windowTitle: frame.windowTitle)
                }
            }

            // Notify that a new frame was captured (for live UI updates)
            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .rewindFrameCaptured, object: nil)
            }

        } catch {
            logError("RewindIndexer: Failed to process frame with metadata: \(error)")
            await RewindDatabase.shared.reportQueryError(error)
        }
    }

    // MARK: - Cleanup

    /// Enforce the data-retention window if a cleanup is due. Throttled to once
    /// per `retentionCleanupInterval` and fire-and-forget so frame ingestion is
    /// never blocked by deletion. Called from the frame pipeline; the first frame
    /// after launch prunes anything past the retention setting.
    private func scheduleRetentionCleanupIfDue() {
        guard Date().timeIntervalSince(lastRetentionCleanupAt) >= retentionCleanupInterval else { return }
        lastRetentionCleanupAt = Date()
        Task { await self.runCleanup() }
    }

    /// Run cleanup to remove old screenshots
    func runCleanup() async {
        guard !isRetentionCleanupRunning else {
            log("RewindIndexer: Cleanup already in progress, skipping")
            return
        }
        isRetentionCleanupRunning = true
        defer { isRetentionCleanupRunning = false }

        let retentionDays = RewindSettings.shared.retentionDays

        do {
            // Ensure recovery has a chance to run if a previous cleanup closed the DB
            // after a corruption/I/O error.
            try await RewindDatabase.shared.initialize()

            // Get cutoff date
            let cutoffDate = Calendar.current.date(byAdding: .day, value: -retentionDays, to: Date())!

            // Delete from database and get paths to delete
            let deleteResult = try await RewindDatabase.shared.deleteScreenshotsOlderThan(cutoffDate)

            // Delete legacy JPEG files
            if !deleteResult.imagePaths.isEmpty {
                try await RewindStorage.shared.deleteScreenshots(relativePaths: deleteResult.imagePaths)
            }

            // Delete orphaned video chunks (all frames deleted)
            if !deleteResult.orphanedVideoChunks.isEmpty {
                try await RewindStorage.shared.deleteVideoChunks(relativePaths: deleteResult.orphanedVideoChunks)
            }

            // Clean up empty directories
            try await RewindStorage.shared.cleanupEmptyDirectories()

            let totalDeleted = deleteResult.imagePaths.count + deleteResult.orphanedVideoChunks.count
            if totalDeleted > 0 {
                log("RewindIndexer: Cleaned up \(deleteResult.imagePaths.count) old JPEGs and \(deleteResult.orphanedVideoChunks.count) video chunks")
            }

        } catch {
            logError("RewindIndexer: Cleanup failed: \(error)")
        }
    }

    /// Stop the indexer and return whether pending video frames flushed successfully.
    @discardableResult
    func stop() async -> Bool {
        // Flush any pending video frames before stopping
        do {
            _ = try await VideoChunkEncoder.shared.flushCurrentChunk()
        } catch {
            logError("RewindIndexer: Failed to flush video chunk: \(error)")
            return false
        }

        log("RewindIndexer: Stopped")
        return true
    }

    // MARK: - OCR Backfill (battery → AC)

    private var isBackfilling = false

    /// Run OCR on screenshots that were skipped due to battery
    func backfillUnindexedScreenshots() async {
        guard !isBackfilling else {
            log("RewindIndexer: Backfill already in progress, skipping")
            return
        }
        guard await ensureInitialized() else { return }

        isBackfilling = true
        defer { isBackfilling = false }

        log("RewindIndexer: Starting OCR backfill for battery-skipped screenshots...")
        var totalProcessed = 0
        let batchSize = 10

        do {
            while true {
                if PowerMonitor.cachedBatteryState() {
                    log("RewindIndexer: Backfill paused — back on battery after \(totalProcessed) screenshots")
                    return
                }

                let pending = try await RewindDatabase.shared.getBatterySkippedScreenshots(limit: batchSize)
                if pending.isEmpty { break }

                for screenshot in pending {
                    if PowerMonitor.cachedBatteryState() {
                        log("RewindIndexer: Backfill paused — back on battery after \(totalProcessed) screenshots")
                        return
                    }

                    guard let id = screenshot.id else { continue }

                    do {
                        let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
                        guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                            continue
                        }

                        let ocrResult = try await Task(priority: .utility) {
                            try await RewindOCRService.shared.extractTextWithBounds(from: cgImage)
                        }.value

                        try await RewindDatabase.shared.updateOCRResult(id: id, ocrResult: ocrResult)
                        totalProcessed += 1
                    } catch RewindError.screenshotNotFound {
                        // Screenshot/video file is permanently missing — clear skippedForBattery so we don't retry forever
                        try? await RewindDatabase.shared.clearSkippedForBattery(id: id)
                    } catch let RewindError.corruptedVideoChunk(path) {
                        log("RewindIndexer: Skipping corrupted chunk \(path) for screenshot \(id)")
                        try? await RewindDatabase.shared.clearSkippedForBattery(id: id)
                    } catch {
                        logError("RewindIndexer: Backfill OCR failed for screenshot \(id): \(error)")
                        // Clear flag to prevent infinite retry loop for permanently broken screenshots
                        try? await RewindDatabase.shared.clearSkippedForBattery(id: id)
                    }

                    // Small delay to avoid hogging CPU
                    try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
                }
            }

            log("RewindIndexer: OCR backfill complete — processed \(totalProcessed) screenshots")
        } catch {
            logError("RewindIndexer: OCR backfill failed: \(error)")
        }
    }

    /// Set up PowerMonitor callback for OCR backfill on AC reconnect
    func setupPowerMonitorCallback() {
        Task { @MainActor in
            PowerMonitor.shared.onACReconnected = {
                Task {
                    await RewindIndexer.shared.backfillUnindexedScreenshots()
                }
            }
        }
    }

    // MARK: - Statistics

    /// Get indexer statistics
    func getStats() async -> (total: Int, indexed: Int, storageSize: Int64)? {
        do {
            let dbStats = try await RewindDatabase.shared.getStats()
            let storageSize = try await RewindStorage.shared.getTotalStorageSize()
            return (dbStats.total, dbStats.indexed, storageSize)
        } catch {
            logError("RewindIndexer: Failed to get stats: \(error)")
            return nil
        }
    }

    // MARK: - Database Rebuild

    /// Rebuild database from existing video files
    /// This scans all video chunks and recreates database entries
    /// - Parameter progressCallback: Called with progress (0.0 to 1.0) as rebuild proceeds
    func rebuildFromVideoFiles(progressCallback: @escaping (Double) -> Void) async throws {
        log("RewindIndexer: Starting database rebuild from video files...")

        // Ensure initialized
        if !isInitialized {
            try await initialize()
        }

        // Get all video chunk files
        let videoChunks = try await RewindStorage.shared.getAllVideoChunks()
        let totalChunks = videoChunks.count

        if totalChunks == 0 {
            log("RewindIndexer: No video chunks found to rebuild from")
            progressCallback(1.0)
            return
        }

        log("RewindIndexer: Found \(totalChunks) video chunks to process")

        var processedChunks = 0
        var totalFrames = 0
        var failureSummary = RewindRebuildFailureSummary(totalChunks: totalChunks)

        for chunkInfo in videoChunks {
            defer {
                processedChunks += 1
                progressCallback(Double(processedChunks) / Double(totalChunks))
            }

            let screenshots: [Screenshot]
            do {
                screenshots = try await Self.reconstructedScreenshots(from: chunkInfo)
            } catch RewindChunkExtractionError.unparseablePath {
                failureSummary.record(.unparseablePath)
                log("RewindIndexer: Cannot rebuild chunk with an unparseable path: \(chunkInfo.relativePath)")
                continue
            } catch RewindChunkExtractionError.zeroFrames {
                failureSummary.record(.zeroFrames)
                log("RewindIndexer: Cannot rebuild zero-frame chunk: \(chunkInfo.relativePath)")
                continue
            } catch RewindChunkExtractionError.invalidTimeline {
                failureSummary.record(.invalidTimeline)
                log("RewindIndexer: Cannot rebuild chunk with an invalid sample timeline: \(chunkInfo.relativePath)")
                continue
            } catch {
                failureSummary.record(.videoRead)
                log("RewindIndexer: Failed to read chunk \(chunkInfo.relativePath): \(error)")
                continue
            }

            do {
                // Replacement is transactional and idempotent: a retry neither
                // duplicates rows nor destroys the previous complete chunk when a
                // reconstructed insert fails.
                totalFrames += try await RewindDatabase.shared.replaceScreenshotsForVideoChunk(
                    path: chunkInfo.relativePath,
                    screenshots: screenshots
                )
            } catch {
                failureSummary.record(.databaseWrite)
                log("RewindIndexer: Failed to commit chunk \(chunkInfo.relativePath): \(error)")
            }
        }

        if failureSummary.hasFailures {
            let message = failureSummary.message
            logError("RewindIndexer: \(message)")
            throw RewindError.storageError(message)
        }

        log("RewindIndexer: Rebuild complete - processed \(totalChunks) chunks, \(totalFrames) frames")
    }

    /// Reconstruct screenshot rows from the chunk's actual encoded sample timeline.
    /// Sample ordinal remains the durable `frameOffset` contract used by playback;
    /// presentation time preserves variable/low-cadence capture timing.
    static func reconstructedScreenshots(from chunkInfo: VideoChunkInfo) async throws -> [Screenshot] {
        // Parse the chunk's capture time from its relative path (the day lives in
        // the parent directory: "<yyyy-MM-dd>/chunk_HHmmss.mp4").
        guard let timestamp = Self.parseChunkTimestamp(relativePath: chunkInfo.relativePath) else {
            throw RewindChunkExtractionError.unparseablePath
        }

        let presentationTimes = try await readVideoSamplePresentationTimes(at: chunkInfo.fullPath)
        return presentationTimes.enumerated().map { frameOffset, presentationTime in
            Screenshot(
                timestamp: timestamp.addingTimeInterval(presentationTime),
                appName: "Unknown",
                windowTitle: nil,
                imagePath: "",
                videoChunkPath: chunkInfo.relativePath,
                frameOffset: frameOffset,
                ocrText: nil,
                ocrDataJson: nil,
                isIndexed: false
            )
        }
    }

    /// Validate a decoded sample timeline before it becomes durable database state.
    /// Video samples must be non-empty and strictly increase from a finite,
    /// non-negative presentation time.
    @discardableResult
    static func validateVideoSampleTimeline(_ presentationTimes: [TimeInterval]) throws -> [TimeInterval] {
        guard !presentationTimes.isEmpty else {
            throw RewindChunkExtractionError.zeroFrames
        }

        var previous: TimeInterval?
        for presentationTime in presentationTimes {
            guard presentationTime.isFinite,
                  presentationTime >= 0,
                  previous.map({ presentationTime > $0 }) ?? true
            else {
                throw RewindChunkExtractionError.invalidTimeline
            }
            previous = presentationTime
        }
        return presentationTimes
    }

    /// Read compressed video samples directly so rebuild count and timing come
    /// from the file rather than `duration × nominalFrameRate`, which invents rows
    /// for low-cadence and variable-frame-rate chunks.
    private static func readVideoSamplePresentationTimes(at path: URL) async throws -> [TimeInterval] {
        let asset = AVURLAsset(url: path)
        guard let videoTrack = try await asset.loadTracks(withMediaType: .video).first else {
            throw RewindChunkExtractionError.zeroFrames
        }

        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: videoTrack, outputSettings: nil)
        output.alwaysCopiesSampleData = false

        guard reader.canAdd(output) else {
            throw RewindError.storageError("AVFoundation cannot add rebuild video track output")
        }
        reader.add(output)

        guard reader.startReading() else {
            let message = reader.error?.localizedDescription ?? "unknown error"
            throw RewindError.storageError("AVFoundation rebuild reader failed to start: \(message)")
        }

        var presentationTimes: [TimeInterval] = []
        while let sampleBuffer = output.copyNextSampleBuffer() {
            defer { CMSampleBufferInvalidate(sampleBuffer) }
            let sampleCount = CMSampleBufferGetNumSamples(sampleBuffer)
            // AVAssetReader may surface zero-sample marker buffers around
            // compressed HEVC media. They carry no screenshot identity; skip
            // them and let the final non-empty validation reject files that
            // contain no actual video samples.
            guard sampleCount > 0 else { continue }

            for sampleIndex in 0..<sampleCount {
                var timing = CMSampleTimingInfo(
                    duration: .invalid,
                    presentationTimeStamp: .invalid,
                    decodeTimeStamp: .invalid
                )
                guard CMSampleBufferGetSampleTimingInfo(
                    sampleBuffer,
                    at: sampleIndex,
                    timingInfoOut: &timing
                ) == 0 else {
                    reader.cancelReading()
                    throw RewindChunkExtractionError.invalidTimeline
                }
                presentationTimes.append(CMTimeGetSeconds(timing.presentationTimeStamp))
            }
        }

        if reader.status == .failed {
            let message = reader.error?.localizedDescription ?? "unknown error"
            throw RewindError.storageError("AVFoundation rebuild reader failed: \(message)")
        }
        if reader.status == .cancelled {
            throw RewindError.storageError("AVFoundation rebuild reader was cancelled")
        }

        return try validateVideoSampleTimeline(presentationTimes)
    }

    /// Parse a chunk's capture timestamp from its stored relative path.
    ///
    /// New format (VideoChunkEncoder.generateChunkPath):
    ///   "<yyyy-MM-dd>/chunk_<HHmmss>.<ext>" — day directory + time-only filename.
    /// Legacy flat format: "chunk_<YYYYMMDD>_<HHMMSS>.hevc".
    ///
    /// The encoder wrote both parts with local-time DateFormatters, so parse in the
    /// current time zone to round-trip. Pure + static so rebuild parsing is testable.
    static func parseChunkTimestamp(relativePath: String) -> Date? {
        let parts = relativePath.split(separator: "/").map(String.init)
        let filename = parts.last ?? relativePath

        // New format: day directory + "chunk_HHmmss.<ext>".
        if parts.count >= 2, let time = timeComponentFromChunkFilename(filename) {
            let dayStr = parts[parts.count - 2]
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = .current
            formatter.dateFormat = "yyyy-MM-dd'T'HHmmss"
            if let date = formatter.date(from: "\(dayStr)T\(time)") {
                return date
            }
        }

        // Legacy flat format: chunk_YYYYMMDD_HHMMSS.hevc
        return parseLegacyChunkTimestamp(filename)
    }

    /// Extract the "HHmmss" component from "chunk_HHmmss.<ext>", or nil if the
    /// filename doesn't match the time-only chunk shape.
    private static func timeComponentFromChunkFilename(_ filename: String) -> String? {
        guard filename.hasPrefix("chunk_") else { return nil }
        let afterPrefix = filename.dropFirst("chunk_".count)
        let stem = afterPrefix.split(separator: ".").first.map(String.init) ?? String(afterPrefix)
        guard stem.count == 6, stem.allSatisfy({ $0.isNumber }) else { return nil }
        return stem
    }

    private static func parseLegacyChunkTimestamp(_ filename: String) -> Date? {
        // Expected format: chunk_YYYYMMDD_HHMMSS.hevc
        guard filename.hasPrefix("chunk_"),
              filename.hasSuffix(".hevc"),
              filename.count == 26 else { return nil }  // "chunk_" (6) + 8 + "_" (1) + 6 + ".hevc" (5) = 26

        let startIndex = filename.index(filename.startIndex, offsetBy: 6)
        let dateEndIndex = filename.index(startIndex, offsetBy: 8)
        let timeStartIndex = filename.index(dateEndIndex, offsetBy: 1)
        let timeEndIndex = filename.index(timeStartIndex, offsetBy: 6)

        let dateStr = String(filename[startIndex..<dateEndIndex])
        let timeStr = String(filename[timeStartIndex..<timeEndIndex])

        // Validate that both parts are numeric
        guard dateStr.allSatisfy({ $0.isNumber }),
              timeStr.allSatisfy({ $0.isNumber }) else { return nil }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMddHHmmss"
        return formatter.date(from: dateStr + timeStr)
    }

}

enum RewindShutdownFlush {
    static func flush(timeout: TimeInterval, context: String) -> Bool {
        let state = RewindFlushState()
        let semaphore = DispatchSemaphore(value: 0)
        Task.detached(priority: .userInitiated) {
            state.setFlushed(await RewindIndexer.shared.stop())
            semaphore.signal()
        }

        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            logError("\(context): Timed out flushing Rewind chunk")
            return false
        }

        if !state.didFlush {
            logError("\(context): Failed to flush Rewind chunk")
        }
        return state.didFlush
    }
}

private final class RewindFlushState: @unchecked Sendable {
    private let lock = NSLock()
    private var flushed = false

    var didFlush: Bool {
        lock.lock()
        defer { lock.unlock() }
        return flushed
    }

    func setFlushed(_ value: Bool) {
        lock.lock()
        flushed = value
        lock.unlock()
    }
}

private struct FrameDedupeSignature: Equatable {
    let fingerprint: UInt64
    let width: Int
    let height: Int
    let appName: String
    let windowTitle: String?
}

enum RewindChunkExtractionError: Error, Equatable {
    case unparseablePath
    case zeroFrames
    case invalidTimeline
}

enum RewindRebuildFailureKind: CaseIterable, Hashable {
    case unparseablePath
    case zeroFrames
    case invalidTimeline
    case videoRead
    case databaseWrite

    var summaryLabel: String {
        switch self {
        case .unparseablePath: return "unparseable_path"
        case .zeroFrames: return "zero_frames"
        case .invalidTimeline: return "invalid_timeline"
        case .videoRead: return "video_read"
        case .databaseWrite: return "database_write"
        }
    }
}

/// Fixed-cardinality failure accounting for a best-effort rebuild. The thrown
/// summary never grows with the number of chunks and never includes paths or raw
/// error payloads; detailed per-chunk diagnostics remain in the local log.
struct RewindRebuildFailureSummary {
    let totalChunks: Int
    private(set) var counts: [RewindRebuildFailureKind: Int] = [:]

    mutating func record(_ kind: RewindRebuildFailureKind) {
        counts[kind, default: 0] += 1
    }

    var failedChunkCount: Int {
        counts.values.reduce(0, +)
    }

    var hasFailures: Bool {
        failedChunkCount > 0
    }

    var message: String {
        let committedChunks = max(0, totalChunks - failedChunkCount)
        let categorySummary = RewindRebuildFailureKind.allCases.compactMap { kind -> String? in
            guard let count = counts[kind], count > 0 else { return nil }
            return "\(kind.summaryLabel)=\(count)"
        }.joined(separator: ", ")
        return "Rebuild committed \(committedChunks) of \(totalChunks) video chunks; "
            + "\(failedChunkCount) failed (\(categorySummary))"
    }
}
