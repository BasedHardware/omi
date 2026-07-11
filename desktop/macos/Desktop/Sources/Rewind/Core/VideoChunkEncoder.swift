import AppKit
import AVFoundation
import CoreGraphics
import Foundation
import Sentry

/// Encodes screenshot frames into H.265 video chunks using VideoToolbox for efficient storage.
actor VideoChunkEncoder {
    static let shared = VideoChunkEncoder()

    // MARK: - Configuration

    private let chunkDuration: TimeInterval = 60.0 // 60-second chunks
    /// First chunk after launch finalizes faster so Rewind shows screenshots within
    /// seconds of monitoring starting, instead of waiting up to 60s + 10s stale grace.
    /// The Rewind UI filters out the active (unfinalized) chunk, so without this you'd
    /// see nothing on the Rewind page for ~1-2 minutes after every launch.
    private let firstChunkDuration: TimeInterval = 5.0
    private var frameRate: Double {
        let interval = RewindSettings.shared.effectiveCaptureInterval(isOnBattery: PowerMonitor.cachedBatteryState())
        return 1.0 / interval // e.g. 0.5s interval = 2 FPS
    }
    private let maxResolution: CGFloat = 3000 // Maximum dimension

    /// Threshold for aspect ratio change that triggers a new chunk (20% difference)
    private let aspectRatioChangeThreshold: CGFloat = 0.2

    /// Seconds the new aspect ratio must remain stable before switching chunks.
    /// Prevents rapid app switching from spawning bursts of short-lived chunks
    /// that churn the hardware encoder during finalization.
    private let aspectRatioStabilityDelay: TimeInterval = 2.0

    /// Maximum frames to buffer before forcing a flush (memory safety)
    /// Calculated from chunk duration + frame rate + padding so the normal
    /// duration-based finalization always fires before this safety limit.
    private var maxBufferFrames: Int {
        Int(chunkDuration * frameRate) + 20
    }

    /// Maximum consecutive encoder failures before emergency reset
    private let maxConsecutiveFailures = 5

    /// Consecutive not-ready states that force an encoder reset. This keeps
    /// writer readiness loops bounded instead of emitting one Sentry event per frame.
    private let maxConsecutiveNotReadyFailures = 3

    // MARK: - State

    /// Buffer stores only timestamps, not CGImages (memory optimization)
    /// CGImages are written to the encoder immediately and not retained.
    private var frameTimestamps: [Date] = []

    /// Track consecutive encoder write failures for recovery.
    private var consecutiveWriteFailures = 0
    private var encoderRestartCount = 0
    private var emergencyResetCount = 0
    private var writerNotReadyCount = 0

    /// Pending aspect ratio debounce state
    private var pendingAspectRatioSize: CGSize?
    private var pendingAspectRatioSince: Date?
    private var currentChunkStartTime: Date?
    private(set) var currentChunkPath: String?
    private var frameOffsetInChunk: Int = 0

    // Native HEVC writer state
    private var assetWriter: AVAssetWriter?
    private var writerInput: AVAssetWriterInput?
    private var pixelBufferAdaptor: AVAssetWriterInputPixelBufferAdaptor?
    private var currentOutputSize: CGSize?
    private var currentChunkInputSize: CGSize?  // Track input size for aspect ratio comparison

    /// Timer to finalize stale chunks when frames stop arriving
    private var stalenessCheckTask: Task<Void, Never>?

    private var videosDirectory: URL?
    private var isInitialized = false

    /// True after the first chunk finalizes. Until then we use `firstChunkDuration`
    /// instead of `chunkDuration` so Rewind UI starts showing frames within seconds
    /// of launch.
    private var hasFinalizedAnyChunk = false

    // MARK: - Types

    struct EncodedFrame {
        let videoChunkPath: String // Relative path to .mp4
        let frameOffset: Int // Frame index within chunk
        let timestamp: Date
    }

    struct ChunkFlushResult {
        let videoChunkPath: String
        let frames: [EncodedFrame]
    }

    // MARK: - Initialization

    private init() {}

    /// Initialize the encoder with the videos directory
    func initialize(videosDirectory: URL) async throws {
        if isInitialized {
            guard self.videosDirectory != videosDirectory else { return }
            await resetForUserSwitch()
        }

        self.videosDirectory = videosDirectory
        isInitialized = true
        log("VideoChunkEncoder: Initialized at \(videosDirectory.path)")
    }

    func videosDirectoryForTesting() -> URL? {
        videosDirectory
    }

    func hasFinalizedChunkForDedupe() -> Bool {
        hasFinalizedAnyChunk
    }

    // MARK: - Frame Processing

    /// Add a frame to the buffer. Returns encoded info if this frame completed a chunk.
    func addFrame(image: CGImage, timestamp: Date) async throws -> EncodedFrame? {
        guard isInitialized, let videosDir = videosDirectory else {
            throw RewindError.storageError("VideoChunkEncoder not initialized")
        }

        let newFrameSize = CGSize(width: image.width, height: image.height)

        // SAFETY: Check if buffer exceeded max size (memory leak prevention)
        if frameTimestamps.count >= maxBufferFrames {
            log("VideoChunkEncoder: Buffer exceeded \(maxBufferFrames) frames, forcing flush to prevent memory leak")
            logError("VideoChunkEncoder: Emergency buffer flush triggered - \(frameTimestamps.count) frames")
            try await emergencyReset(reason: "buffer_overflow")
        }

        // Check if aspect ratio changed significantly.
        // Debounce: require the new ratio to be stable for aspectRatioStabilityDelay before
        // switching chunks. Rapid app switching (e.g. Firefox ↔ terminal) previously caused
        // bursts of 1-3 frame chunks whose hevc_videotoolbox encoder hung on finalization,
        // blocking the actor for 10s per event and chaining into a cascade.
        if let currentInputSize = currentChunkInputSize,
           hasSignificantAspectRatioChange(from: currentInputSize, to: newFrameSize) {
            let now = Date()
            let pendingMatches = pendingAspectRatioSize.map {
                !hasSignificantAspectRatioChange(from: $0, to: newFrameSize)
            } ?? false

            if pendingMatches,
               let since = pendingAspectRatioSince,
               now.timeIntervalSince(since) >= aspectRatioStabilityDelay {
                // New aspect ratio has been stable for the required delay — commit the switch
                log("VideoChunkEncoder: Aspect ratio changed significantly (\(currentInputSize) -> \(newFrameSize)), starting new chunk")
                pendingAspectRatioSize = nil
                pendingAspectRatioSince = nil
                try await finalizeCurrentChunk()
            } else {
                // Not yet stable — record/refresh the pending candidate and drop this frame
                if !pendingMatches {
                    pendingAspectRatioSize = newFrameSize
                    pendingAspectRatioSince = now
                }
                return nil
            }
        } else {
            // Aspect ratio matches current chunk — clear any pending transition
            pendingAspectRatioSize = nil
            pendingAspectRatioSince = nil
        }

        // Start new chunk if needed
        if currentChunkStartTime == nil {
            currentChunkStartTime = timestamp
            currentChunkPath = generateChunkPath(for: timestamp)
            frameOffsetInChunk = 0
            currentChunkInputSize = newFrameSize

            // Start native HEVC writer for this chunk
            do {
                try startVideoWriter(
                    for: currentChunkPath!,
                    videosDir: videosDir,
                    imageSize: newFrameSize
                )
                consecutiveWriteFailures = 0 // Reset on successful start
                writerNotReadyCount = 0
                encoderRestartCount += 1
            } catch {
                consecutiveWriteFailures += 1
                logError("VideoChunkEncoder: Failed to start video writer (\(consecutiveWriteFailures)/\(maxConsecutiveFailures)): \(error)")

                // Reset the half-initialized chunk state so the NEXT frame cleanly retries
                // starting the writer. Without this, currentChunkStartTime stays set while
                // writer state is nil, so every subsequent frame skips the start path and
                // fails inside writeFrame() with "Video writer not ready" — needlessly dropping
                // ~5 frames (2.5s of Rewind footage) and emitting misleading write-failure
                // errors until the emergency-reset threshold finally clears the state.
                currentChunkStartTime = nil
                currentChunkPath = nil
                currentChunkInputSize = nil
                currentOutputSize = nil
                frameOffsetInChunk = 0

                if consecutiveWriteFailures >= maxConsecutiveFailures {
                    logError("VideoChunkEncoder: Too many video writer failures, performing emergency reset")
                    try await emergencyReset(reason: "writer_start_failure")
                }
                throw error
            }
        }

        // Write frame to the encoder FIRST (CGImage not stored after this). Only a
        // successful write may consume a frame index: if the write throws, the
        // caller skips the DB insert for this frame, so advancing frameOffsetInChunk
        // / appending a timestamp here would desync every later frame in the chunk
        // by one (DB frameOffset N pointing at real sample N-1, and the last record
        // pointing past the end of the video). Record the frame only after success.
        do {
            try await writeFrame(image: image)
            consecutiveWriteFailures = 0 // Reset on successful write
            resetStalenessTimer()
        } catch {
            consecutiveWriteFailures += 1
            logError("VideoChunkEncoder: Failed to write frame (\(consecutiveWriteFailures)/\(maxConsecutiveFailures)): \(error)")

            if consecutiveWriteFailures >= maxConsecutiveFailures {
                logError("VideoChunkEncoder: Too many write failures, performing emergency reset")
                try await emergencyReset(reason: "write_failure")
            }
            throw error
        }

        // Write succeeded — now record the timestamp (CGImage is not retained) and
        // claim this frame's offset, so offsets match real encoded sample indices.
        frameTimestamps.append(timestamp)

        let frameInfo = EncodedFrame(
            videoChunkPath: currentChunkPath!,
            frameOffset: frameOffsetInChunk,
            timestamp: timestamp
        )

        frameOffsetInChunk += 1

        // Check if chunk duration exceeded.
        // First chunk uses the shorter `firstChunkDuration` so Rewind starts showing
        // frames within ~5s of launch instead of waiting out the full 60s window.
        let effectiveDuration = hasFinalizedAnyChunk ? chunkDuration : firstChunkDuration
        if let startTime = currentChunkStartTime,
           timestamp.timeIntervalSince(startTime) >= effectiveDuration
        {
            // Finalize current chunk
            try await finalizeCurrentChunk()
            hasFinalizedAnyChunk = true
            return frameInfo
        }

        return frameInfo
    }

    /// Force flush current buffer (app termination, etc.)
    func flushCurrentChunk() async throws -> ChunkFlushResult? {
        guard currentChunkPath != nil, !frameTimestamps.isEmpty else {
            return nil
        }

        let chunkPath = currentChunkPath!
        let frames = frameTimestamps.enumerated().map { index, timestamp in
            EncodedFrame(
                videoChunkPath: chunkPath,
                frameOffset: index,
                timestamp: timestamp
            )
        }

        try await finalizeCurrentChunk()

        return ChunkFlushResult(videoChunkPath: chunkPath, frames: frames)
    }

    // MARK: - Video Writer Management

    private func startVideoWriter(for relativePath: String, videosDir: URL, imageSize: CGSize) throws {
        // Create day subdirectory if needed
        let components = relativePath.components(separatedBy: "/")
        if components.count > 1 {
            let dayDir = videosDir.appendingPathComponent(components[0], isDirectory: true)
            try FileManager.default.createDirectory(at: dayDir, withIntermediateDirectories: true)
        }

        let fullPath = videosDir.appendingPathComponent(relativePath)

        // Calculate output size (maintain aspect ratio, max 3000)
        let outputSize = calculateOutputSize(for: imageSize)
        currentOutputSize = outputSize

        if FileManager.default.fileExists(atPath: fullPath.path) {
            try FileManager.default.removeItem(at: fullPath)
        }

        let width = Int(outputSize.width)
        let height = Int(outputSize.height)
        let bitrate = estimatedHEVCBitrate(width: width, height: height)

        let writer = try AVAssetWriter(outputURL: fullPath, fileType: .mp4)
        writer.shouldOptimizeForNetworkUse = true

        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.hevc,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: bitrate,
                AVVideoExpectedSourceFrameRateKey: max(1, Int(ceil(frameRate))),
                AVVideoMaxKeyFrameIntervalDurationKey: 10,
                AVVideoAllowFrameReorderingKey: false
            ]
        ]

        let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = true

        guard writer.canAdd(input) else {
            throw RewindError.storageError("Cannot add HEVC writer input")
        }
        writer.add(input)

        let adaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: input,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                kCVPixelBufferWidthKey as String: width,
                kCVPixelBufferHeightKey as String: height,
                kCVPixelBufferIOSurfacePropertiesKey as String: [:]
            ]
        )

        guard writer.startWriting() else {
            if let writerError = writer.error {
                throw RewindError.storageWriteFailed("Failed to start HEVC writer", underlying: writerError)
            }
            throw RewindError.storageError("Failed to start HEVC writer: unknown error")
        }
        writer.startSession(atSourceTime: .zero)

        assetWriter = writer
        writerInput = input
        pixelBufferAdaptor = adaptor

        log("VideoChunkEncoder: Started native HEVC writer for chunk at \(relativePath)")

        // Log frame dimensions to Sentry for debugging user quality issues
        let breadcrumb = Breadcrumb(level: .info, category: "video_encoder")
        breadcrumb.message = "Started video chunk encoding"
        breadcrumb.data = [
            "chunk_path": relativePath,
            "input_width": Int(imageSize.width),
            "input_height": Int(imageSize.height),
            "output_width": Int(outputSize.width),
            "output_height": Int(outputSize.height),
            "quality": 65,
            "estimated_bitrate": bitrate,
            "encoder": "AVAssetWriter.hevc",
            "input_format": "cvpixelbuffer_bgra",
            "max_resolution": Int(maxResolution)
        ]
        SentrySDK.addBreadcrumb(breadcrumb)
    }

    private func writeFrame(image: CGImage) async throws {
        guard let input = writerInput,
              let adaptor = pixelBufferAdaptor,
              let outputSize = currentOutputSize
        else {
            writerNotReadyCount += 1

            if writerNotReadyCount >= maxConsecutiveNotReadyFailures {
                logError("VideoChunkEncoder: Video writer not ready \(writerNotReadyCount)x, resetting encoder state")
                try await emergencyReset(reason: "writer_not_ready_loop")
            } else {
                log("VideoChunkEncoder: Video writer not ready (\(writerNotReadyCount)/\(maxConsecutiveNotReadyFailures))")
            }

            throw RewindError.storageError("Video writer not ready")
        }

        try await waitForWriterInputReady(input)

        let pixelBuffer: CVPixelBuffer = try autoreleasepool {
            try createPixelBuffer(from: image, size: outputSize, adaptor: adaptor)
        }

        let presentationTime = CMTime(seconds: Double(max(0, frameOffsetInChunk - 1)) / frameRate, preferredTimescale: 600)
        guard adaptor.append(pixelBuffer, withPresentationTime: presentationTime) else {
            if let writerError = assetWriter?.error {
                throw RewindError.storageWriteFailed("Failed to append frame to HEVC writer", underlying: writerError)
            }
            throw RewindError.storageError("Failed to append frame to HEVC writer: unknown error")
        }
        writerNotReadyCount = 0
    }

    private func finalizeCurrentChunk() async throws {
        stalenessCheckTask?.cancel()
        stalenessCheckTask = nil
        defer {
            resetCurrentChunkState()
        }

        if let input = writerInput, let writer = assetWriter {
            let frameCount = frameTimestamps.count
            input.markAsFinished()
            do {
                try await finishWriting(writer)
            } catch {
                writer.cancelWriting()
                throw error
            }
            log("VideoChunkEncoder: Finalized chunk with \(frameCount) frames (restartCount=\(encoderRestartCount), emergencyResets=\(emergencyResetCount))")
        }
    }

    private func resetCurrentChunkState() {
        // Reset state (timestamps only - no CGImages retained)
        frameTimestamps.removeAll()
        currentChunkStartTime = nil
        currentChunkPath = nil
        frameOffsetInChunk = 0
        currentOutputSize = nil
        currentChunkInputSize = nil
        assetWriter = nil
        writerInput = nil
        pixelBufferAdaptor = nil
        consecutiveWriteFailures = 0
        pendingAspectRatioSize = nil
        pendingAspectRatioSince = nil
    }

    // MARK: - Staleness Detection

    /// Reset the staleness timer after each successful frame write.
    /// If no new frame arrives within chunkDuration + 10s, finalize the chunk
    /// to release the H.265 hardware encoder context.
    private func resetStalenessTimer() {
        stalenessCheckTask?.cancel()
        let timeout = chunkDuration + 10.0
        stalenessCheckTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await self?.finalizeStaleChunkIfNeeded()
        }
    }

    /// Finalize a chunk that has gone stale (no new frames for longer than chunk duration).
    private func finalizeStaleChunkIfNeeded() async {
        guard let startTime = currentChunkStartTime else { return }

        let age = Date().timeIntervalSince(startTime)
        guard age >= chunkDuration else { return }

        log("VideoChunkEncoder: Stale chunk detected (age: \(String(format: "%.0f", age))s, no new frames) — finalizing to release encoder resources")

        let breadcrumb = Breadcrumb(level: .warning, category: "video_encoder")
        breadcrumb.message = "Stale chunk finalized"
        breadcrumb.data = [
            "age_seconds": Int(age),
            "frame_count": frameTimestamps.count,
            "chunk_path": currentChunkPath ?? "none"
        ]
        SentrySDK.addBreadcrumb(breadcrumb)

        try? await finalizeCurrentChunk()
    }

    // MARK: - Helpers

    private func generateChunkPath(for timestamp: Date) -> String {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let dayString = dateFormatter.string(from: timestamp)

        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "HHmmss"
        let timeString = timeFormatter.string(from: timestamp)

        return "\(dayString)/chunk_\(timeString).mp4"
    }

    /// Check if aspect ratio changed significantly between two sizes
    private func hasSignificantAspectRatioChange(from oldSize: CGSize, to newSize: CGSize) -> Bool {
        guard oldSize.height > 0 && newSize.height > 0 else { return true }

        let oldAspect = oldSize.width / oldSize.height
        let newAspect = newSize.width / newSize.height

        // Calculate the relative difference in aspect ratio
        let aspectDiff = abs(oldAspect - newAspect) / max(oldAspect, newAspect)

        return aspectDiff > aspectRatioChangeThreshold
    }

    private func calculateOutputSize(for size: CGSize) -> CGSize {
        let maxDimension = max(size.width, size.height)

        if maxDimension <= maxResolution {
            // Round to even numbers (required by video codecs)
            return CGSize(
                width: CGFloat(Int(size.width) / 2 * 2),
                height: CGFloat(Int(size.height) / 2 * 2)
            )
        }

        let scale = maxResolution / maxDimension
        let newWidth = Int(size.width * scale) / 2 * 2
        let newHeight = Int(size.height * scale) / 2 * 2

        return CGSize(width: CGFloat(newWidth), height: CGFloat(newHeight))
    }

    private func estimatedHEVCBitrate(width: Int, height: Int) -> Int {
        let bitsPerPixelFrame = 0.35
        let bitrate = Double(width * height) * max(frameRate, 1.0) * bitsPerPixelFrame
        return max(350_000, min(8_000_000, Int(bitrate)))
    }

    private func createPixelBuffer(
        from image: CGImage,
        size: CGSize,
        adaptor: AVAssetWriterInputPixelBufferAdaptor
    ) throws -> CVPixelBuffer {
        let width = Int(size.width)
        let height = Int(size.height)
        guard width > 0, height > 0 else {
            throw RewindError.storageError("Invalid pixel buffer size \(size)")
        }

        let pixelBuffer: CVPixelBuffer
        if let pool = adaptor.pixelBufferPool {
            var pooledBuffer: CVPixelBuffer?
            let status = CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pooledBuffer)
            guard status == kCVReturnSuccess, let pooledBuffer else {
                throw RewindError.storageError("Failed to create pooled pixel buffer: \(status)")
            }
            pixelBuffer = pooledBuffer
        } else {
            var createdBuffer: CVPixelBuffer?
            let status = CVPixelBufferCreate(
                nil,
                width,
                height,
                kCVPixelFormatType_32BGRA,
                [
                    kCVPixelBufferIOSurfacePropertiesKey as String: [:]
                ] as CFDictionary,
                &createdBuffer
            )
            guard status == kCVReturnSuccess, let createdBuffer else {
                throw RewindError.storageError("Failed to create pixel buffer: \(status)")
            }
            pixelBuffer = createdBuffer
        }

        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, []) }

        guard let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else {
            throw RewindError.storageError("Pixel buffer has no base address")
        }

        let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
        guard let context = CGContext(
            data: baseAddress,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
        ) else {
            throw RewindError.storageError("Failed to create pixel buffer context")
        }

        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        return pixelBuffer
    }

    private func finishWriting(_ writer: AVAssetWriter) async throws {
        let writerBox = AssetWriterBox(writer)
        try await withCheckedThrowingContinuation { continuation in
            writerBox.writer.finishWriting {
                switch writerBox.writer.status {
                case .completed:
                    continuation.resume()
                case .failed, .cancelled:
                    if let writerError = writerBox.writer.error {
                        continuation.resume(throwing: RewindError.storageWriteFailed("HEVC writer failed", underlying: writerError))
                    } else {
                        continuation.resume(throwing: RewindError.storageError("HEVC writer failed: \(Self.writerStatusDescription(writerBox.writer.status))"))
                    }
                default:
                    continuation.resume(throwing: RewindError.storageError("HEVC writer ended in unexpected state: \(Self.writerStatusDescription(writerBox.writer.status))"))
                }
            }
        }
    }

    private func waitForWriterInputReady(_ input: AVAssetWriterInput) async throws {
        let deadline = Date().addingTimeInterval(2.0)
        while !input.isReadyForMoreMediaData {
            if Date() >= deadline {
                throw RewindError.storageError("Video writer input backpressured")
            }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
    }

    private nonisolated static func writerStatusDescription(_ status: AVAssetWriter.Status) -> String {
        switch status {
        case .unknown: return "unknown"
        case .writing: return "writing"
        case .completed: return "completed"
        case .failed: return "failed"
        case .cancelled: return "cancelled"
        @unknown default: return "unrecognized"
        }
    }

    // MARK: - Cleanup

    /// Cancel any in-progress encoding and clean up
    func cancel() async {
        stalenessCheckTask?.cancel()
        stalenessCheckTask = nil

        writerInput?.markAsFinished()
        assetWriter?.cancelWriting()
        assetWriter = nil
        writerInput = nil
        pixelBufferAdaptor = nil

        frameTimestamps.removeAll()
        currentChunkStartTime = nil
        currentChunkPath = nil
        frameOffsetInChunk = 0
        currentOutputSize = nil
        currentChunkInputSize = nil
        consecutiveWriteFailures = 0
        writerNotReadyCount = 0
    }

    func resetForUserSwitch() async {
        await cancel()
        videosDirectory = nil
        isInitialized = false
        hasFinalizedAnyChunk = false
    }

    /// Emergency reset when encoding fails repeatedly or buffer overflows
    /// Clears all state and allows fresh start on next frame
    private func emergencyReset(reason: String = "failure_threshold") async throws {
        stalenessCheckTask?.cancel()
        stalenessCheckTask = nil

        let droppedFrames = frameTimestamps.count
        emergencyResetCount += 1

        // Report to Sentry for monitoring
        let breadcrumb = Breadcrumb(level: .error, category: "video_encoder")
        breadcrumb.message = "Emergency reset triggered"
        breadcrumb.data = [
            "reason": reason,
            "dropped_frames": droppedFrames,
            "consecutive_failures": consecutiveWriteFailures,
            "writer_not_ready_count": writerNotReadyCount,
            "encoder_restart_count": encoderRestartCount,
            "emergency_reset_count": emergencyResetCount,
            "buffer_limit": maxBufferFrames,
            "chunk_path": currentChunkPath ?? "none"
        ]
        SentrySDK.addBreadcrumb(breadcrumb)

        logError("VideoChunkEncoder: Emergency reset (reason=\(reason)) - dropping \(droppedFrames) frames to prevent memory leak")

        writerInput?.markAsFinished()
        assetWriter?.cancelWriting()

        resetCurrentChunkState()
        writerNotReadyCount = 0

        log("VideoChunkEncoder: Emergency reset complete, ready for new frames")
    }

    struct EncoderStatus {
        let frameCount: Int
        let maxBufferFrames: Int
        let oldestFrameAge: TimeInterval?
        let currentChunkAge: TimeInterval?
        let isEncoderRunning: Bool
        let consecutiveWriteFailures: Int
        let encoderRestartCount: Int
        let emergencyResetCount: Int
        let writerNotReadyCount: Int
    }

    /// Get current buffer and lifecycle status for memory diagnostics.
    func getBufferStatus() -> EncoderStatus {
        let now = Date()
        return EncoderStatus(
            frameCount: frameTimestamps.count,
            maxBufferFrames: maxBufferFrames,
            oldestFrameAge: frameTimestamps.first.map { now.timeIntervalSince($0) },
            currentChunkAge: currentChunkStartTime.map { now.timeIntervalSince($0) },
            isEncoderRunning: assetWriter != nil,
            consecutiveWriteFailures: consecutiveWriteFailures,
            encoderRestartCount: encoderRestartCount,
            emergencyResetCount: emergencyResetCount,
            writerNotReadyCount: writerNotReadyCount
        )
    }
}

private final class AssetWriterBox: @unchecked Sendable {
    let writer: AVAssetWriter

    init(_ writer: AVAssetWriter) {
        self.writer = writer
    }
}
