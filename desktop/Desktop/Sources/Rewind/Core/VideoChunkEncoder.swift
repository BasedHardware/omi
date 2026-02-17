import AppKit
import CoreGraphics
import Foundation
import Sentry

/// Encodes screenshot frames into H.265 video chunks using ffmpeg for efficient storage.
/// Uses fragmented MP4 format so frames can be read while the file is still being written.
actor VideoChunkEncoder {
    static let shared = VideoChunkEncoder()

    // Track if we've reported ffmpeg source this session (once per app launch)
    private static var hasReportedFFmpegSource = false

    // MARK: - Configuration

    private let chunkDuration: TimeInterval = 60.0 // 60-second chunks
    private var frameRate: Double {
        let interval = UserDefaults.standard.object(forKey: "rewindCaptureInterval") as? Double ?? 1.0
        return 1.0 / interval // e.g. 0.5s interval = 2 FPS
    }
    private let maxResolution: CGFloat = 3000 // Maximum dimension

    /// Threshold for aspect ratio change that triggers a new chunk (20% difference)
    private let aspectRatioChangeThreshold: CGFloat = 0.2

    /// Maximum frames to buffer before forcing a flush (memory safety)
    /// Calculated from chunk duration + frame rate + padding so the normal
    /// duration-based finalization always fires before this safety limit.
    private var maxBufferFrames: Int {
        Int(chunkDuration * frameRate) + 20
    }

    /// Maximum consecutive ffmpeg failures before emergency reset
    private let maxConsecutiveFailures = 5

    // MARK: - State

    /// Buffer stores only timestamps, not CGImages (memory optimization)
    /// CGImages are written to ffmpeg immediately and not retained
    private var frameTimestamps: [Date] = []

    /// Track consecutive ffmpeg write failures for recovery
    private var consecutiveWriteFailures = 0
    private var currentChunkStartTime: Date?
    private(set) var currentChunkPath: String?
    private var frameOffsetInChunk: Int = 0

    // FFmpeg process state
    private var ffmpegProcess: Process?
    private var ffmpegStdin: FileHandle?
    private var currentOutputSize: CGSize?
    private var currentChunkInputSize: CGSize?  // Track input size for aspect ratio comparison

    private var videosDirectory: URL?
    private var isInitialized = false

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
        guard !isInitialized else { return }

        self.videosDirectory = videosDirectory
        isInitialized = true
        log("VideoChunkEncoder: Initialized at \(videosDirectory.path)")
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
            try await emergencyReset()
        }

        // Check if aspect ratio changed significantly - if so, start a new chunk
        // This prevents frames from different window sizes being squished together
        if let currentInputSize = currentChunkInputSize,
           hasSignificantAspectRatioChange(from: currentInputSize, to: newFrameSize) {
            log("VideoChunkEncoder: Aspect ratio changed significantly (\(currentInputSize) -> \(newFrameSize)), starting new chunk")
            try await finalizeCurrentChunk()
        }

        // Start new chunk if needed
        if currentChunkStartTime == nil {
            currentChunkStartTime = timestamp
            currentChunkPath = generateChunkPath(for: timestamp)
            frameOffsetInChunk = 0
            currentChunkInputSize = newFrameSize

            // Start ffmpeg process for this chunk
            do {
                try await startFFmpegProcess(
                    for: currentChunkPath!,
                    videosDir: videosDir,
                    imageSize: newFrameSize
                )
                consecutiveWriteFailures = 0 // Reset on successful start
            } catch {
                consecutiveWriteFailures += 1
                logError("VideoChunkEncoder: Failed to start ffmpeg (\(consecutiveWriteFailures)/\(maxConsecutiveFailures)): \(error)")

                if consecutiveWriteFailures >= maxConsecutiveFailures {
                    logError("VideoChunkEncoder: Too many ffmpeg failures, performing emergency reset")
                    try await emergencyReset()
                }
                throw error
            }
        }

        // Record timestamp only (CGImage is not retained - memory optimization)
        frameTimestamps.append(timestamp)

        let frameInfo = EncodedFrame(
            videoChunkPath: currentChunkPath!,
            frameOffset: frameOffsetInChunk,
            timestamp: timestamp
        )

        frameOffsetInChunk += 1

        // Write frame to ffmpeg immediately (CGImage not stored after this)
        do {
            try await writeFrame(image: image)
            consecutiveWriteFailures = 0 // Reset on successful write
        } catch {
            consecutiveWriteFailures += 1
            logError("VideoChunkEncoder: Failed to write frame (\(consecutiveWriteFailures)/\(maxConsecutiveFailures)): \(error)")

            if consecutiveWriteFailures >= maxConsecutiveFailures {
                logError("VideoChunkEncoder: Too many write failures, performing emergency reset")
                try await emergencyReset()
            }
            throw error
        }

        // Check if chunk duration exceeded
        if let startTime = currentChunkStartTime,
           timestamp.timeIntervalSince(startTime) >= chunkDuration
        {
            // Finalize current chunk
            try await finalizeCurrentChunk()
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

    // MARK: - FFmpeg Process Management

    private func startFFmpegProcess(for relativePath: String, videosDir: URL, imageSize: CGSize) async throws {
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

        // Find ffmpeg path
        let ffmpegPath = findFFmpegPath()

        // Build ffmpeg command
        // Uses fragmented MP4 so the file can be read while still being written
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ffmpegPath)
        process.arguments = [
            "-f", "image2pipe",
            "-vcodec", "png",
            "-r", String(frameRate),
            "-i", "-",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", // Ensure even dimensions
            "-vcodec", "hevc_videotoolbox",
            "-tag:v", "hvc1",
            "-q:v", "65",  // Quality scale 1-100 (65 ≈ CRF 15 equivalent)
            "-allow_sw", "true",  // Fall back to software if HW encoder busy
            "-realtime", "true",  // Hint: real-time capture, don't block
            "-prio_speed", "true",  // Prioritize speed over compression
            // Fragmented MP4 - allows reading while writing
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-pix_fmt", "yuv420p",
            "-y", // Overwrite output
            fullPath.path
        ]

        // Set up pipes
        let stdinPipe = Pipe()
        process.standardInput = stdinPipe
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        try process.run()

        ffmpegProcess = process
        ffmpegStdin = stdinPipe.fileHandleForWriting

        log("VideoChunkEncoder: Started ffmpeg for chunk at \(relativePath)")

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
            "encoder": "hevc_videotoolbox",
            "max_resolution": Int(maxResolution)
        ]
        SentrySDK.addBreadcrumb(breadcrumb)
    }

    private func writeFrame(image: CGImage) async throws {
        guard let stdin = ffmpegStdin,
              let outputSize = currentOutputSize
        else {
            throw RewindError.storageError("FFmpeg not ready")
        }

        // Wrap image scaling + PNG encoding in autoreleasepool to prevent
        // CGContext/NSBitmapImageRep accumulation in async actor contexts.
        // Without this, temporary Obj-C objects from each frame pile up
        // because Swift concurrency doesn't drain autorelease pools between tasks.
        let pngData: Data = try autoreleasepool {
            let scaledImage = scaleImage(image, to: outputSize)
            guard let data = createPNGData(from: scaledImage) else {
                throw RewindError.storageError("Failed to create PNG data")
            }
            return data
        }

        // Write to ffmpeg stdin
        do {
            try stdin.write(contentsOf: pngData)
        } catch {
            throw RewindError.storageError("Failed to write frame to ffmpeg: \(error.localizedDescription)")
        }
    }

    private func finalizeCurrentChunk() async throws {
        // Close stdin to signal end of input to ffmpeg
        if let stdin = ffmpegStdin {
            try? stdin.close()
            ffmpegStdin = nil
        }

        // Wait for ffmpeg to finish
        if let process = ffmpegProcess {
            process.waitUntilExit()

            if process.terminationStatus != 0 {
                logError("VideoChunkEncoder: FFmpeg exited with status \(process.terminationStatus)")
            } else {
                log("VideoChunkEncoder: Finalized chunk with \(frameTimestamps.count) frames")
            }

            ffmpegProcess = nil
        }

        // Reset state (timestamps only - no CGImages retained)
        frameTimestamps.removeAll()
        currentChunkStartTime = nil
        currentChunkPath = nil
        frameOffsetInChunk = 0
        currentOutputSize = nil
        currentChunkInputSize = nil
        consecutiveWriteFailures = 0
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

    private func scaleImage(_ image: CGImage, to targetSize: CGSize) -> CGImage {
        let currentSize = CGSize(width: image.width, height: image.height)

        // If already the right size, return as-is
        if currentSize.width == targetSize.width && currentSize.height == targetSize.height {
            return image
        }

        // Create a context at the target size
        guard let context = CGContext(
            data: nil,
            width: Int(targetSize.width),
            height: Int(targetSize.height),
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            return image
        }

        context.interpolationQuality = .high
        context.draw(image, in: CGRect(origin: .zero, size: targetSize))

        return context.makeImage() ?? image
    }

    private func createPNGData(from image: CGImage) -> Data? {
        let bitmapRep = NSBitmapImageRep(cgImage: image)
        return bitmapRep.representation(using: .png, properties: [:])
    }

    private func findFFmpegPath() -> String {
        // Common locations for ffmpeg (bundled first for users without Homebrew)
        // Use Bundle.resourceBundle for SPM resources (they're in a nested bundle, not main bundle)
        let bundledPath = Bundle.resourceBundle.path(forResource: "ffmpeg", ofType: nil)
        let possiblePaths: [(path: String, source: String)] = [
            (bundledPath ?? "", "bundled"),
            ("/opt/homebrew/bin/ffmpeg", "homebrew"),
            ("/usr/local/bin/ffmpeg", "usr_local"),
            ("/usr/bin/ffmpeg", "system"),
        ].filter { !$0.path.isEmpty }

        for (path, source) in possiblePaths {
            if FileManager.default.fileExists(atPath: path) {
                reportFFmpegSource(source: source, path: path)
                return path
            }
        }

        // Fall back to PATH lookup
        reportFFmpegSource(source: "path_fallback", path: "ffmpeg")
        return "ffmpeg"
    }

    private func reportFFmpegSource(source: String, path: String) {
        // Only report once per app launch
        guard !Self.hasReportedFFmpegSource else { return }
        Self.hasReportedFFmpegSource = true

        Task { @MainActor in
            PostHogManager.shared.ffmpegResolved(source: source, path: path)
        }
    }

    // MARK: - Cleanup

    /// Cancel any in-progress encoding and clean up
    func cancel() async {
        // Close stdin first
        if let stdin = ffmpegStdin {
            try? stdin.close()
            ffmpegStdin = nil
        }

        // Terminate ffmpeg process
        if let process = ffmpegProcess {
            process.terminate()
            ffmpegProcess = nil
        }

        frameTimestamps.removeAll()
        currentChunkStartTime = nil
        currentChunkPath = nil
        frameOffsetInChunk = 0
        currentOutputSize = nil
        currentChunkInputSize = nil
        consecutiveWriteFailures = 0
    }

    /// Emergency reset when ffmpeg fails repeatedly or buffer overflows
    /// Clears all state and allows fresh start on next frame
    private func emergencyReset() async throws {
        let droppedFrames = frameTimestamps.count

        // Report to Sentry for monitoring
        let breadcrumb = Breadcrumb(level: .error, category: "video_encoder")
        breadcrumb.message = "Emergency reset triggered"
        breadcrumb.data = [
            "dropped_frames": droppedFrames,
            "consecutive_failures": consecutiveWriteFailures,
            "chunk_path": currentChunkPath ?? "none"
        ]
        SentrySDK.addBreadcrumb(breadcrumb)

        logError("VideoChunkEncoder: Emergency reset - dropping \(droppedFrames) frames to prevent memory leak")

        // Close stdin first (don't wait for ffmpeg to finish - it may be hung)
        if let stdin = ffmpegStdin {
            try? stdin.close()
            ffmpegStdin = nil
        }

        // Terminate ffmpeg process forcefully
        if let process = ffmpegProcess {
            process.terminate()
            ffmpegProcess = nil
        }

        // Clear all state
        frameTimestamps.removeAll()
        currentChunkStartTime = nil
        currentChunkPath = nil
        frameOffsetInChunk = 0
        currentOutputSize = nil
        currentChunkInputSize = nil
        consecutiveWriteFailures = 0

        log("VideoChunkEncoder: Emergency reset complete, ready for new frames")
    }

    /// Get current buffer status for debugging
    func getBufferStatus() -> (frameCount: Int, oldestFrameAge: TimeInterval?) {
        let count = frameTimestamps.count
        let age = frameTimestamps.first.map { Date().timeIntervalSince($0) }
        return (count, age)
    }
}
