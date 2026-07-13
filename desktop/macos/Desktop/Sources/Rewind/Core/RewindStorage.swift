import AppKit
import AVFoundation
import CoreImage
import Foundation
import OmiSupport
import Sentry

/// File storage manager for Rewind screenshots
actor RewindStorage {
    static let shared = RewindStorage()

    private let fileManager = FileManager.default
    private var screenshotsDirectory: URL?
    private var videosDirectory: URL?

    // Frame extraction cache
    private var frameCache = NSCache<NSString, NSImage>()

    // Track corrupted video chunks to avoid repeated frame extraction attempts
    private var corruptedChunks = Set<String>()

    // MARK: - Initialization

    private init() {
        // Configure cache limits
        frameCache.countLimit = 100 // Max 100 frames in cache
        frameCache.totalCostLimit = 100 * 1024 * 1024 // ~100MB
    }

    /// Reset storage state (called on user switch / sign-out)
    func reset() async {
        screenshotsDirectory = nil
        videosDirectory = nil
        frameCache.removeAllObjects()
        corruptedChunks.removeAll()
        await VideoChunkEncoder.shared.resetForUserSwitch()
        log("RewindStorage: Reset for user switch")
    }

    /// Initialize the storage directories
    func initialize() async throws {
        let userId = RewindDatabase.currentUserId ?? "anonymous"
        let omiDir = DesktopLocalProfile.applicationSupportURL()
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(userId, isDirectory: true)

        // Screenshots directory (legacy JPEG storage)
        screenshotsDirectory = omiDir.appendingPathComponent("Screenshots", isDirectory: true)

        // Videos directory (new H.265 chunk storage)
        videosDirectory = omiDir.appendingPathComponent("Videos", isDirectory: true)

        guard let screenshotsDirectory = screenshotsDirectory,
              let videosDirectory = videosDirectory
        else {
            throw RewindError.storageError("Failed to create storage directory paths")
        }

        try fileManager.createDirectory(at: screenshotsDirectory, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: videosDirectory, withIntermediateDirectories: true)

        // Initialize video encoder with videos directory
        try await VideoChunkEncoder.shared.initialize(videosDirectory: videosDirectory)

        log("RewindStorage: Initialized at \(omiDir.path)")
    }

    /// Get the videos directory URL for external use
    func getVideosDirectory() -> URL? {
        return videosDirectory
    }

    // MARK: - Save Screenshot

    /// Save JPEG data to disk and return the relative path
    func saveScreenshot(jpegData: Data, timestamp: Date) async throws -> String {
        guard let screenshotsDirectory = screenshotsDirectory else {
            throw RewindError.storageError("Storage not initialized")
        }

        // Create day subdirectory
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let dayString = dateFormatter.string(from: timestamp)

        let dayDirectory = screenshotsDirectory.appendingPathComponent(dayString, isDirectory: true)
        try fileManager.createDirectory(at: dayDirectory, withIntermediateDirectories: true)

        // Create filename with timestamp
        let timestampFormatter = DateFormatter()
        timestampFormatter.dateFormat = "HHmmss_SSS"
        let timeString = timestampFormatter.string(from: timestamp)

        let filename = "screenshot_\(timeString).jpg"
        let relativePath = "\(dayString)/\(filename)"
        let fullPath = screenshotsDirectory.appendingPathComponent(relativePath)

        // Write the file
        try jpegData.write(to: fullPath)

        return relativePath
    }

    // MARK: - Load Screenshot

    /// Load image data from a relative path
    func loadScreenshot(relativePath: String) async throws -> Data {
        guard let screenshotsDirectory = screenshotsDirectory else {
            throw RewindError.storageError("Storage not initialized")
        }

        let fullPath = screenshotsDirectory.appendingPathComponent(relativePath)

        guard fileManager.fileExists(atPath: fullPath.path) else {
            throw RewindError.screenshotNotFound
        }

        return try Data(contentsOf: fullPath)
    }

    /// Get the full URL for a screenshot
    func getScreenshotURL(relativePath: String) async -> URL? {
        guard let screenshotsDirectory = screenshotsDirectory else {
            return nil
        }

        let fullPath = screenshotsDirectory.appendingPathComponent(relativePath)

        guard fileManager.fileExists(atPath: fullPath.path) else {
            return nil
        }

        return fullPath
    }

    /// Load screenshot as NSImage (legacy JPEG path)
    func loadScreenshotImage(relativePath: String) async throws -> NSImage {
        let data = try await loadScreenshot(relativePath: relativePath)
        guard let image = NSImage(data: data) else {
            throw RewindError.invalidImage
        }
        return image
    }

    // MARK: - Video Frame Loading

    /// Load a frame from a video chunk.
    func loadVideoFrame(videoPath: String, frameOffset: Int) async throws -> NSImage {
        guard let videosDirectory = videosDirectory else {
            throw RewindError.storageError("Videos directory not initialized")
        }

        // Skip known corrupted chunks immediately
        if corruptedChunks.contains(videoPath) {
            throw RewindError.corruptedVideoChunk(videoPath)
        }

        // Check cache first
        let cacheKey = "\(videoPath):\(frameOffset)" as NSString
        if let cached = frameCache.object(forKey: cacheKey) {
            return cached
        }

        let fullPath = videosDirectory.appendingPathComponent(videoPath)

        guard fileManager.fileExists(atPath: fullPath.path) else {
            throw RewindError.screenshotNotFound
        }

        do {
            let image = try await extractFrame(from: fullPath.path, frameOffset: frameOffset)

            // Cache for reuse (estimate ~4MB per frame for cost)
            frameCache.setObject(image, forKey: cacheKey, cost: 4 * 1024 * 1024)

            return image
        } catch let error as RewindError {
            // Check if this is a corruption error
            if case .corruptedVideoChunk = error {
                throw error
            }
            // Check error message for corruption indicators
            if case .storageError(let message) = error,
               isUnreadableVideoChunkError(message) {
                // Don't mark the active chunk as corrupted — it's still being written
                let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
                if videoPath == activeChunk {
                    log("RewindStorage: Frame in active chunk not yet available: \(videoPath)")
                    throw RewindError.screenshotNotFound
                }
                log("RewindStorage: Marking video chunk as corrupted: \(videoPath)")
                corruptedChunks.insert(videoPath)
                throw RewindError.corruptedVideoChunk(videoPath)
            }
            throw error
        }
    }

    private func extractFrame(from fullPath: String, frameOffset: Int) async throws -> NSImage {
        do {
            return try await extractFrameWithAVFoundation(from: fullPath, frameOffset: frameOffset)
        } catch let nativeError as RewindError {
            if case .screenshotNotFound = nativeError {
                throw nativeError
            }

            do {
                return try await extractFrameWithFFmpeg(from: fullPath, frameOffset: frameOffset)
            } catch {
                if isFFmpegUnavailable(error) {
                    throw nativeError
                }
                throw error
            }
        } catch {
            let nativeError = error
            do {
                return try await extractFrameWithFFmpeg(from: fullPath, frameOffset: frameOffset)
            } catch {
                if isFFmpegUnavailable(error) {
                    throw RewindError.storageError("AVFoundation failed: \(nativeError.localizedDescription)")
                }
                throw error
            }
        }
    }

    /// Extract a frame from finalized AVAssetWriter MP4 chunks using the system decoder.
    private func extractFrameWithAVFoundation(from videoPath: String, frameOffset: Int) async throws -> NSImage {
        guard frameOffset >= 0 else {
            throw RewindError.screenshotNotFound
        }

        let asset = AVURLAsset(url: URL(fileURLWithPath: videoPath))
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard let track = tracks.first else {
            throw RewindError.storageError("AVFoundation found no video track")
        }

        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(
            track: track,
            outputSettings: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
            ]
        )
        output.alwaysCopiesSampleData = false

        guard reader.canAdd(output) else {
            throw RewindError.storageError("AVFoundation cannot add video track output")
        }
        reader.add(output)

        guard reader.startReading() else {
            let message = reader.error?.localizedDescription ?? "unknown error"
            throw RewindError.storageError("AVFoundation reader failed to start: \(message)")
        }

        var sampleIndex = 0
        while let sampleBuffer = output.copyNextSampleBuffer() {
            defer { CMSampleBufferInvalidate(sampleBuffer) }

            guard sampleIndex == frameOffset else {
                sampleIndex += 1
                continue
            }

            guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
                reader.cancelReading()
                throw RewindError.storageError("AVFoundation sample had no image buffer")
            }

            let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
            let context = CIContext(options: [.useSoftwareRenderer: false])
            let rect = CGRect(
                x: 0,
                y: 0,
                width: CVPixelBufferGetWidth(pixelBuffer),
                height: CVPixelBufferGetHeight(pixelBuffer)
            )
            guard let cgImage = context.createCGImage(ciImage, from: rect) else {
                reader.cancelReading()
                throw RewindError.storageError("AVFoundation failed to render decoded frame")
            }

            let image = NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))

            let breadcrumb = Breadcrumb(level: .info, category: "frame_extraction")
            breadcrumb.message = "Extracted frame from video"
            breadcrumb.data = [
                "video_path": videoPath,
                "frame_offset": frameOffset,
                "image_width": cgImage.width,
                "image_height": cgImage.height,
                "decoder": "AVAssetReader"
            ]
            SentrySDK.addBreadcrumb(breadcrumb)

            return image
        }

        if reader.status == .failed {
            let message = reader.error?.localizedDescription ?? "unknown error"
            throw RewindError.storageError("AVFoundation reader failed: \(message)")
        }

        throw RewindError.screenshotNotFound
    }

    /// Extract a frame from video using ffmpeg
    private func extractFrameWithFFmpeg(from videoPath: String, frameOffset: Int) async throws -> NSImage {
        let ffmpegPath = findFFmpegPath()

        // Create a temporary file for the output
        let tempDir = FileManager.default.temporaryDirectory
        let outputPath = tempDir.appendingPathComponent("frame_\(UUID().uuidString).jpg")

        // Build ffmpeg command to extract single frame
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ffmpegPath)
        process.arguments = [
            "-i", videoPath,
            "-vf", "select=eq(n\\,\(frameOffset))",
            "-vsync", "0",
            "-vframes", "1",
            "-f", "image2",
            "-c:v", "mjpeg",
            "-pix_fmt", "yuvj420p", // Full-range YUV required by MJPEG
            "-q:v", "2", // High quality JPEG
            "-y", // Overwrite
            outputPath.path
        ]

        // Capture stderr for error handling
        let stderrPipe = Pipe()
        process.standardOutput = FileHandle.nullDevice
        process.standardError = stderrPipe

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            throw RewindError.storageError("Failed to run ffmpeg: \(error.localizedDescription)")
        }

        if process.terminationStatus != 0 {
            let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
            let stderrString = String(data: stderrData, encoding: .utf8) ?? "unknown error"
            throw RewindError.storageError("FFmpeg failed: \(stderrString)")
        }

        // Load the extracted frame
        let fileExists = FileManager.default.fileExists(atPath: outputPath.path)
        let fileSize = (try? FileManager.default.attributesOfItem(atPath: outputPath.path)[.size] as? Int) ?? 0
        let imageData = try? Data(contentsOf: outputPath)
        let image = imageData.flatMap { NSImage(data: $0) }

        guard let imageData, let image else {
            // ffmpeg exited 0 but produced no output — selected frame was not present.
            // Treat as missing frame (not a real error) so the backfill silently skips it.
            if !fileExists || fileSize == 0 {
                throw RewindError.screenshotNotFound
            }
            // File exists but couldn't be loaded/decoded — genuine error worth logging.
            let memoryMB = ProcessInfo.processInfo.physicalMemory > 0
                ? Int(Double(ProcessInfo.processInfo.physicalMemory) / 1_048_576)
                : -1
            let detail = "fileExists=\(fileExists), fileSize=\(fileSize), dataLoaded=\(imageData != nil), imageDecoded=\(image != nil), systemMemoryMB=\(memoryMB), videoPath=\(videoPath), frameOffset=\(frameOffset)"
            throw RewindError.storageError("Failed to load extracted frame, \(detail)")
        }

        // Log extracted frame dimensions to Sentry for debugging quality issues
        let breadcrumb = Breadcrumb(level: .info, category: "frame_extraction")
        breadcrumb.message = "Extracted frame from video"
        breadcrumb.data = [
            "video_path": videoPath,
            "frame_offset": frameOffset,
            "image_width": Int(image.size.width),
            "image_height": Int(image.size.height),
            "data_size_bytes": imageData.count
        ]
        SentrySDK.addBreadcrumb(breadcrumb)

        // Clean up temp file
        try? FileManager.default.removeItem(at: outputPath)

        return image
    }

    private func isFFmpegUnavailable(_ error: Error) -> Bool {
        guard case RewindError.storageError(let message) = error else {
            return false
        }

        return message.contains("Failed to run ffmpeg")
    }

    private func isUnreadableVideoChunkError(_ message: String) -> Bool {
        message.contains("moov atom not found")
            || message.contains("Invalid data found")
            || message.contains("AVFoundation failed")
            || message.contains("Cannot Open")
            || message.contains("media may be damaged")
    }

    /// Find ffmpeg executable path
    private func findFFmpegPath() -> String {
        // Bundled ffmpeg first for users without Homebrew
        // SwiftPM resources are in a nested bundle, but avoid Bundle.resourceBundle
        // here because that accessor fatal-errors in test contexts with no app bundle.
        let bundleName = "Omi Computer_Omi Computer.bundle"
        let resourceBundlePath = Bundle.main.bundleURL
            .appendingPathComponent("Contents/Resources")
            .appendingPathComponent(bundleName)
            .appendingPathComponent("ffmpeg")
            .path
        let developmentBundlePath = Bundle.main.bundleURL
            .appendingPathComponent(bundleName)
            .appendingPathComponent("ffmpeg")
            .path

        let possiblePaths = [
            resourceBundlePath,
            developmentBundlePath,
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
        ]

        for path in possiblePaths {
            if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }

        return "ffmpeg"
    }

    /// Unified loading interface - loads from either JPEG or video storage
    func loadScreenshotImage(for screenshot: Screenshot) async throws -> NSImage {
        if screenshot.usesVideoStorage,
           let videoPath = screenshot.videoChunkPath,
           let offset = screenshot.frameOffset
        {
            return try await loadVideoFrame(videoPath: videoPath, frameOffset: offset)
        } else if let imagePath = screenshot.imagePath, !imagePath.isEmpty {
            return try await loadScreenshotImage(relativePath: imagePath)
        } else {
            throw RewindError.screenshotNotFound
        }
    }

    /// Get raw image data for a screenshot (for OCR processing)
    func loadScreenshotData(for screenshot: Screenshot) async throws -> Data {
        if screenshot.usesVideoStorage,
           let videoPath = screenshot.videoChunkPath,
           let offset = screenshot.frameOffset
        {
            // Load frame and convert to JPEG data
            let image = try await loadVideoFrame(videoPath: videoPath, frameOffset: offset)
            guard let tiffData = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiffData),
                  let jpegData = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 1.0])
            else {
                throw RewindError.invalidImage
            }
            return jpegData
        } else if let imagePath = screenshot.imagePath, !imagePath.isEmpty {
            return try await loadScreenshot(relativePath: imagePath)
        } else {
            throw RewindError.screenshotNotFound
        }
    }

    /// Clear the frame cache
    func clearCache() {
        frameCache.removeAllObjects()
    }

    /// Check if a video chunk is known to be corrupted
    func isChunkCorrupted(_ videoPath: String) -> Bool {
        return corruptedChunks.contains(videoPath)
    }

    /// Mark a video chunk as corrupted (called when corruption is detected)
    func markChunkAsCorrupted(_ videoPath: String) {
        corruptedChunks.insert(videoPath)
        log("RewindStorage: Marked chunk as corrupted: \(videoPath)")
    }

    /// Clean up a corrupted video chunk - deletes DB entries and optionally the file
    /// Returns the number of deleted database records
    func cleanupCorruptedChunk(_ videoPath: String, deleteFile: Bool = true) async throws -> Int {
        // Delete database entries for this chunk
        let deletedCount = try await RewindDatabase.shared.deleteScreenshotsFromVideoChunk(videoChunkPath: videoPath)

        // Optionally delete the corrupted file
        if deleteFile {
            try await deleteVideoChunk(relativePath: videoPath)
        }

        // Remove from corrupted set since it's cleaned up
        corruptedChunks.remove(videoPath)

        log("RewindStorage: Cleaned up corrupted chunk \(videoPath), deleted \(deletedCount) DB entries")
        return deletedCount
    }

    /// Get all currently known corrupted chunks
    func getCorruptedChunks() -> Set<String> {
        return corruptedChunks
    }

    // MARK: - Delete Screenshot

    /// Resolve the on-disk file to delete for a stored screenshot relative path,
    /// or `nil` when the path is unsafe to delete.
    ///
    /// Video-based screenshots persist `imagePath` as "" (see
    /// `RewindDatabase.insertScreenshot`), and retention cleanup can hand those
    /// empty strings back. `root.appendingPathComponent("")` resolves to the
    /// Screenshots directory itself, so a naive `removeItem` would recursively
    /// wipe the entire screenshot store. Refuse empty/whitespace paths, the
    /// storage root itself, and any path that escapes the root via `..`
    /// (e.g. "../outside.jpg") so retention cleanup can never delete a file
    /// outside the screenshot store.
    static func screenshotDeletionURL(relativePath: String, in root: URL) -> URL? {
        let trimmed = relativePath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        // Use the trimmed value for the component too (not the raw relativePath),
        // so a whitespace-padded stored path resolves consistently.
        let candidate = root.appendingPathComponent(trimmed).standardizedFileURL
        let standardizedRoot = root.standardizedFileURL
        // Require the candidate to sit strictly inside the root: reject the root
        // itself, and require the root path + "/" as a prefix so a standardized
        // "../" escape (which lands beside or above the root) is refused.
        let rootPath = standardizedRoot.path
        let rootPrefix = rootPath.hasSuffix("/") ? rootPath : rootPath + "/"
        guard candidate.path != rootPath, candidate.path.hasPrefix(rootPrefix) else {
            return nil
        }
        return candidate
    }

    /// Delete a screenshot file
    func deleteScreenshot(relativePath: String) async throws {
        guard let screenshotsDirectory = screenshotsDirectory else {
            throw RewindError.storageError("Storage not initialized")
        }

        guard
            let fullPath = Self.screenshotDeletionURL(
                relativePath: relativePath, in: screenshotsDirectory)
        else {
            return
        }

        if fileManager.fileExists(atPath: fullPath.path) {
            try fileManager.removeItem(at: fullPath)
        }
    }

    /// Delete multiple screenshots
    func deleteScreenshots(relativePaths: [String]) async throws {
        for path in relativePaths {
            try await deleteScreenshot(relativePath: path)
        }
    }

    // MARK: - Video Chunk Deletion

    /// Delete a video chunk file
    func deleteVideoChunk(relativePath: String) async throws {
        guard let videosDirectory = videosDirectory else {
            throw RewindError.storageError("Videos directory not initialized")
        }

        let fullPath = videosDirectory.appendingPathComponent(relativePath)

        // Invalidate cache entries for this chunk (we can't iterate NSCache, so just clear relevant entries by rebuilding)
        // The cache will naturally evict old entries

        if fileManager.fileExists(atPath: fullPath.path) {
            try fileManager.removeItem(at: fullPath)
            log("RewindStorage: Deleted video chunk \(relativePath)")
        }
    }

    /// Delete multiple video chunks
    func deleteVideoChunks(relativePaths: [String]) async throws {
        for path in relativePaths {
            try await deleteVideoChunk(relativePath: path)
        }
    }

    // MARK: - Cleanup

    /// Delete empty day directories in both Screenshots and Videos folders
    func cleanupEmptyDirectories() async throws {
        // Clean up Screenshots directory
        if let screenshotsDirectory = screenshotsDirectory {
            try cleanupEmptySubdirectories(in: screenshotsDirectory)
        }

        // Clean up Videos directory
        if let videosDirectory = videosDirectory {
            try cleanupEmptySubdirectories(in: videosDirectory)
        }
    }

    private func cleanupEmptySubdirectories(in directory: URL) throws {
        // The legacy Screenshots dir may not exist for video-only users — skip it
        // rather than aborting the whole cleanup sweep.
        guard fileManager.fileExists(atPath: directory.path) else { return }

        let contents = try fileManager.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        )

        for url in contents {
            let resourceValues = try url.resourceValues(forKeys: [.isDirectoryKey])
            if resourceValues.isDirectory == true {
                let subContents = try fileManager.contentsOfDirectory(atPath: url.path)
                if subContents.isEmpty {
                    try fileManager.removeItem(at: url)
                    log("RewindStorage: Removed empty directory \(url.lastPathComponent)")
                }
            }
        }
    }

    /// Delete screenshots older than the specified number of days
    func deleteOldScreenshots(olderThanDays days: Int) async throws -> Int {
        guard let screenshotsDirectory = screenshotsDirectory else {
            throw RewindError.storageError("Storage not initialized")
        }

        let cutoffDate = Calendar.current.date(byAdding: .day, value: -days, to: Date())!
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let cutoffString = dateFormatter.string(from: cutoffDate)

        var deletedCount = 0

        let contents = try fileManager.contentsOfDirectory(
            at: screenshotsDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: .skipsHiddenFiles
        )

        for url in contents {
            let resourceValues = try url.resourceValues(forKeys: [.isDirectoryKey])
            if resourceValues.isDirectory == true {
                let dirName = url.lastPathComponent
                // Compare directory name (yyyy-MM-dd) with cutoff
                if dirName < cutoffString {
                    let subContents = try fileManager.contentsOfDirectory(atPath: url.path)
                    deletedCount += subContents.count
                    try fileManager.removeItem(at: url)
                    log("RewindStorage: Deleted old directory \(dirName) with \(subContents.count) files")
                }
            }
        }

        return deletedCount
    }

    // MARK: - Storage Stats

    /// Get total storage size in bytes (both Screenshots and Videos)
    func getTotalStorageSize() async throws -> Int64 {
        var totalSize: Int64 = 0

        if let screenshotsDirectory = screenshotsDirectory {
            totalSize += try calculateDirectorySize(at: screenshotsDirectory)
        }

        if let videosDirectory = videosDirectory {
            totalSize += try calculateDirectorySize(at: videosDirectory)
        }

        return totalSize
    }

    private func calculateDirectorySize(at url: URL) throws -> Int64 {
        var totalSize: Int64 = 0

        let resourceKeys: Set<URLResourceKey> = [.fileSizeKey, .isDirectoryKey]
        let enumerator = fileManager.enumerator(
            at: url,
            includingPropertiesForKeys: Array(resourceKeys),
            options: .skipsHiddenFiles
        )

        while let fileURL = enumerator?.nextObject() as? URL {
            let resourceValues = try fileURL.resourceValues(forKeys: resourceKeys)
            if resourceValues.isDirectory == false {
                totalSize += Int64(resourceValues.fileSize ?? 0)
            }
        }

        return totalSize
    }

    /// Format bytes as human-readable string
    static func formatBytes(_ bytes: Int64) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        return formatter.string(fromByteCount: bytes)
    }

    // MARK: - Video Chunk Discovery

    /// Get all video chunk files for database rebuild
    /// Returns info about each video chunk including path and filename
    func getAllVideoChunks() async throws -> [VideoChunkInfo] {
        guard let videosDirectory = videosDirectory else {
            throw RewindError.storageError("Storage not initialized")
        }

        var chunks: [VideoChunkInfo] = []

        // Enumerate all video chunk files in the videos directory (recursively).
        // The encoder writes .mp4 chunks (VideoChunkEncoder.generateChunkPath);
        // .hevc is only matched for legacy installs. Filtering on .hevc alone made
        // "Rebuild Index" recover ZERO frames from a store full of .mp4 chunks.
        let enumerator = fileManager.enumerator(
            at: videosDirectory,
            includingPropertiesForKeys: [.isRegularFileKey, .creationDateKey],
            options: .skipsHiddenFiles
        )

        while let fileURL = enumerator?.nextObject() as? URL {
            let ext = fileURL.pathExtension.lowercased()
            guard ext == "mp4" || ext == "hevc" else { continue }

            // Get relative path from videos directory
            let relativePath = fileURL.path.replacingOccurrences(of: videosDirectory.path + "/", with: "")

            chunks.append(VideoChunkInfo(
                filename: fileURL.lastPathComponent,
                relativePath: relativePath,
                fullPath: fileURL
            ))
        }

        // The active AVAssetWriter file is not a valid rebuild source yet. Reading
        // it can expose an incomplete sample table and turn a healthy in-progress
        // capture into a reported rebuild failure. This discovery API exists only
        // for rebuild, so finalized-chunk ownership belongs here rather than at
        // each caller.
        let activeChunkPath = await VideoChunkEncoder.shared.currentChunkPath
        chunks = Self.filterFinalizedVideoChunks(chunks, excluding: activeChunkPath)

        // Sort by filename (which contains timestamp)
        chunks.sort { $0.filename < $1.filename }

        log("RewindStorage: Found \(chunks.count) video chunks")
        return chunks
    }

    /// Production-used pure boundary for finalized rebuild candidates.
    static func filterFinalizedVideoChunks(
        _ chunks: [VideoChunkInfo],
        excluding activeChunkPath: String?
    ) -> [VideoChunkInfo] {
        guard let activeChunkPath, !activeChunkPath.isEmpty else {
            return chunks
        }
        return chunks.filter { $0.relativePath != activeChunkPath }
    }
}
