@preconcurrency import AVFoundation
@preconcurrency import AppKit
import CoreImage
import Foundation
import ImageIO
import OmiSupport
import Sentry

/// A Sendable inspection sample for a decoded video frame. This lets callers
/// verify video readback without moving AppKit's non-Sendable `NSImage` outside
/// `RewindStorage`'s actor.
struct RewindVideoFrameCenterPixel: Equatable, Sendable {
  let red: Int
  let green: Int
  let blue: Int
}

/// File storage manager for Rewind screenshots
actor RewindStorage {
  static let shared = RewindStorage()

  private let fileManager = FileManager.default
  private var screenshotsDirectory: URL?
  private var videosDirectory: URL?

  // Frame extraction cache. Holds the decoded `CGImage` rather than an `NSImage` so a cache hit can
  // be handed to the main actor as-is; see `RewindDecodedFrame`.
  private var frameCache = NSCache<NSString, RewindDecodedFrameBox>()

  /// The reader kept parked on the chunk last decoded from, so a forward scrub costs one sample
  /// buffer per step instead of a rescan from frame 0. See `RewindVideoFrameCursor`.
  private var frameCursor: RewindVideoFrameCursor?

  // Track corrupted video chunks to avoid repeated frame extraction attempts
  private var corruptedChunks = Set<String>()
  /// A deterministic seam proving sidecar retention across a one-shot cleanup
  /// failure. Production leaves this at zero.
  private var abandonedChunkCleanupFailuresForTesting = 0
  /// Deterministic failure injection for the DB half of abandoned-chunk
  /// recovery. Production leaves this at zero.
  private var abandonedChunkDatabaseFailuresForTesting = 0

  // MARK: - Initialization

  private init() {
    // Configure cache limits
    frameCache.countLimit = 100  // Max 100 frames in cache
    frameCache.totalCostLimit = 100 * 1024 * 1024  // ~100MB
  }

  /// Reset storage state (called on user switch / sign-out)
  func reset() async {
    do {
      try await resetForOwnerTransition()
    } catch {
      logError("RewindStorage: Could not safely reset old video owner", error: error)
    }
  }

  /// The throwing owner-transition boundary. A marker-write failure may leave
  /// the old writer live, so callers changing the effective owner must stop
  /// before publishing new defaults when the DB-first fallback also fails.
  func resetForOwnerTransition() async throws {
    let cancellation = await VideoChunkEncoder.shared.resetForUserSwitch()
    switch cancellation {
    case .markerWriteFailed(let reservation):
      // Do not clear the old owner configuration while its writer remains
      // active or its database has not accepted the durable tombstone.
      try await recoverAfterMarkerWriteFailure(reservation: reservation)
    case .markerRecorded:
      do {
        try await reconcileAbandonedVideoChunks()
      } catch {
        // The sidecar is deliberately retained. A later initialization for
        // this user retries the DB/file cleanup before capture starts again.
        logError("RewindStorage: Deferred abandoned video chunk recovery", error: error)
      }
    case .noActiveChunk:
      if videosDirectory != nil {
        do {
          try await reconcileAbandonedVideoChunks()
        } catch {
          logError("RewindStorage: Deferred abandoned video chunk recovery", error: error)
        }
      }
    }

    await VideoChunkEncoder.shared.clearConfigurationAfterUserSwitch()
    screenshotsDirectory = nil
    videosDirectory = nil
    clearCache()
    corruptedChunks.removeAll()
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

    // Finish any previous crashed/cancelled writer before this owner can start
    // another one. A marker remains until both database and file cleanup work.
    try await reconcileAbandonedVideoChunks()

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

  // MARK: - Live Frames

  /// Frames in the active (unfinalized) video chunk cannot be decoded yet, so ingest also writes
  /// each JPEG here and the timeline falls back to it until the chunk finalizes. Lives in its own
  /// subdirectory so pruning can never touch legacy per-frame history under the day directories.
  private static let liveFramesDirectoryName = "live"
  /// Comfortably above the 60s chunk duration plus finalization time.
  private static let liveFrameMaxAge: TimeInterval = 10 * 60
  private var lastLiveFramePruneAt: Date = .distantPast

  /// Save a JPEG for a frame whose video chunk has not finalized yet; returns the relative path.
  func saveLiveScreenshot(jpegData: Data, timestamp: Date) async throws -> String {
    guard let screenshotsDirectory = screenshotsDirectory else {
      throw RewindError.storageError("Storage not initialized")
    }
    let liveDirectory = screenshotsDirectory.appendingPathComponent(
      Self.liveFramesDirectoryName, isDirectory: true)
    try fileManager.createDirectory(at: liveDirectory, withIntermediateDirectories: true)

    let filename = "frame_\(Int64(timestamp.timeIntervalSince1970 * 1000)).jpg"
    let relativePath = "\(Self.liveFramesDirectoryName)/\(filename)"
    try jpegData.write(to: screenshotsDirectory.appendingPathComponent(relativePath))

    pruneLiveScreenshotsIfDue()
    return relativePath
  }

  /// Delete live JPEGs old enough that their chunk has long since finalized (video storage wins
  /// once available, so these files are only read while the frame's chunk is active or corrupted).
  private func pruneLiveScreenshotsIfDue(now: Date = Date()) {
    guard now.timeIntervalSince(lastLiveFramePruneAt) >= 60 else { return }
    lastLiveFramePruneAt = now
    guard let screenshotsDirectory = screenshotsDirectory else { return }
    let liveDirectory = screenshotsDirectory.appendingPathComponent(
      Self.liveFramesDirectoryName, isDirectory: true)
    guard
      let files = try? fileManager.contentsOfDirectory(
        at: liveDirectory, includingPropertiesForKeys: [.contentModificationDateKey])
    else { return }
    for file in files {
      let modified =
        (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
        ?? .distantPast
      if now.timeIntervalSince(modified) > Self.liveFrameMaxAge {
        try? fileManager.removeItem(at: file)
      }
    }
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

  /// Load a legacy JPEG on the main actor so AppKit stays on its owning executor.
  @MainActor
  func loadScreenshotImage(relativePath: String) async throws -> NSImage {
    let data = try await loadScreenshot(relativePath: relativePath)
    guard let image = NSImage(data: data) else {
      throw RewindError.invalidImage
    }
    return image
  }

  // MARK: - Video Frame Loading

  /// Load a frame from a video chunk as an AppKit image. AppKit images stay actor-local; callers
  /// outside this actor use a Sendable representation such as
  /// `videoFrameCenterPixel(videoPath:frameOffset:)` or `videoFrame(videoPath:frameOffset:)`.
  private func loadVideoFrame(videoPath: String, frameOffset: Int) async throws -> NSImage {
    let frame = try await videoFrame(videoPath: videoPath, frameOffset: frameOffset)
    return NSImage(cgImage: frame.cgImage, size: frame.pixelSize)
  }

  /// Load a frame from a video chunk in the form that may leave this actor.
  func videoFrame(videoPath: String, frameOffset: Int) async throws -> RewindDecodedFrame {
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
      return cached.frame
    }

    let fullPath = videosDirectory.appendingPathComponent(videoPath)

    guard fileManager.fileExists(atPath: fullPath.path) else {
      throw RewindError.screenshotNotFound
    }

    do {
      let cgImage = try await extractFrame(
        videoPath: videoPath, fullPath: fullPath.path, frameOffset: frameOffset)
      let frame = RewindDecodedFrame(cgImage: cgImage)

      // Cache for reuse (estimate ~4MB per frame for cost)
      frameCache.setObject(RewindDecodedFrameBox(frame), forKey: cacheKey, cost: 4 * 1024 * 1024)

      return frame
    } catch let error as RewindError {
      // Check if this is a corruption error
      if case .corruptedVideoChunk = error {
        throw error
      }
      // Check error message for corruption indicators
      if case .storageError(let message) = error,
        isUnreadableVideoChunkError(message)
      {
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

  private func extractFrame(videoPath: String, fullPath: String, frameOffset: Int) async throws -> CGImage {
    do {
      return try await extractFrameWithAVFoundation(
        videoPath: videoPath, fullPath: fullPath, frameOffset: frameOffset)
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

  /// Read the decoded frame's center pixel without sending an AppKit image
  /// across the storage actor boundary. This is useful for deterministic local
  /// diagnostics and gauntlets that only need to inspect the decoded output.
  func videoFrameCenterPixel(videoPath: String, frameOffset: Int) async throws -> RewindVideoFrameCenterPixel {
    let image = try await loadVideoFrame(videoPath: videoPath, frameOffset: frameOffset)
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
      throw RewindError.invalidImage
    }

    let bitmap = NSBitmapImageRep(cgImage: cgImage)
    let x = max(0, bitmap.pixelsWide / 2)
    let y = max(0, bitmap.pixelsHigh / 2)
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
      throw RewindError.invalidImage
    }

    return RewindVideoFrameCenterPixel(
      red: Int(color.redComponent * 255),
      green: Int(color.greenComponent * 255),
      blue: Int(color.blueComponent * 255)
    )
  }

  /// Extract a frame from finalized AVAssetWriter MP4 chunks using the system decoder.
  ///
  /// A chunk is inter-frame compressed, so reaching frame *n* means decoding everything before it.
  /// The cursor keeps the reader that already did that work parked between calls, which is what
  /// turns a forward scrub from a rescan per step into one sample buffer per step — see
  /// `RewindVideoFrameCursor` for the measurement.
  private func extractFrameWithAVFoundation(
    videoPath: String, fullPath: String, frameOffset: Int
  ) async throws -> CGImage {
    guard frameOffset >= 0 else {
      throw RewindError.screenshotNotFound
    }

    let fileURL = URL(fileURLWithPath: fullPath)

    // Take ownership of the parked cursor for the duration of this call. This method suspends while
    // opening a reader, and the actor is reentrant, so a second load arriving in that window must
    // find no cursor and open its own rather than share a half-advanced tape.
    var cursor = frameCursor
    frameCursor = nil
    if let parked = cursor, !parked.canServe(videoPath: videoPath, frameOffset: frameOffset) {
      // Backward step, or a step into another chunk: nothing cheaper than reopening exists for
      // either, and reopening is what happened on every single request before this cursor.
      parked.cancel()
      cursor = nil
    }

    var active: RewindVideoFrameCursor
    if let reusable = cursor {
      active = reusable
    } else {
      active = try await RewindVideoFrameCursor.open(videoPath: videoPath, fileURL: fileURL)
    }

    // A cursor that runs off the end of a chunk still being written is not an error; reopening once
    // picks up whatever the writer has flushed since. Only the reopened reader reports absence.
    var decoded = try decode(frameOffset, with: active)
    if decoded == nil {
      active.cancel()
      active = try await RewindVideoFrameCursor.open(videoPath: videoPath, fileURL: fileURL)
      decoded = try decode(frameOffset, with: active)
    }
    guard let cgImage = decoded else {
      active.cancel()
      throw RewindError.screenshotNotFound
    }

    // Park the cursor for the next step. A reentrant call may have parked its own in the meantime;
    // that one is retired rather than leaked, because only one open reader is worth keeping.
    frameCursor?.cancel()
    frameCursor = active

    let breadcrumb = Breadcrumb(level: .info, category: "frame_extraction")
    breadcrumb.message = "Extracted frame from video"
    breadcrumb.data = [
      "video_path": videoPath,
      "frame_offset": frameOffset,
      "image_width": cgImage.width,
      "image_height": cgImage.height,
      "decoder": "AVAssetReader",
    ]
    SentrySDK.addBreadcrumb(breadcrumb)

    return cgImage
  }

  /// Decode one offset, retiring the cursor if it fails so a broken reader is never parked.
  private func decode(_ frameOffset: Int, with cursor: RewindVideoFrameCursor) throws -> CGImage? {
    do {
      return try cursor.frame(at: frameOffset)
    } catch {
      cursor.cancel()
      throw error
    }
  }

  /// Extract a frame from video using ffmpeg
  private func extractFrameWithFFmpeg(from videoPath: String, frameOffset: Int) async throws -> CGImage {
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
      "-pix_fmt", "yuvj420p",  // Full-range YUV required by MJPEG
      "-q:v", "2",  // High quality JPEG
      "-y",  // Overwrite
      outputPath.path,
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
      let memoryMB =
        ProcessInfo.processInfo.physicalMemory > 0
        ? Int(Double(ProcessInfo.processInfo.physicalMemory) / 1_048_576)
        : -1
      let detail =
        "fileExists=\(fileExists), fileSize=\(fileSize), dataLoaded=\(imageData != nil), imageDecoded=\(image != nil), systemMemoryMB=\(memoryMB), videoPath=\(videoPath), frameOffset=\(frameOffset)"
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
      "data_size_bytes": imageData.count,
    ]
    SentrySDK.addBreadcrumb(breadcrumb)

    // Clean up temp file
    try? FileManager.default.removeItem(at: outputPath)

    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
      throw RewindError.invalidImage
    }
    return cgImage
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

  /// Unified AppKit loading interface for UI callers. Storage keeps its image work
  /// actor-local; the image itself is constructed only after hopping to MainActor.
  ///
  /// Video-backed frames take the decoded `CGImage` straight across rather than going through
  /// `loadScreenshotData`. That path exists for OCR, which genuinely wants encoded bytes, and it
  /// reaches them by re-encoding the decoded frame to JPEG at quality 1.0 so the caller can decode
  /// it again — a measured **14.4 ms per frame**, paid on every load including frame-cache hits, to
  /// rebuild pixels the decoder had already produced. The scrub is latency-bound (a `sample` of a
  /// live scrub found the main thread 98% idle in its event wait), so that round trip was most of
  /// what a step actually cost.
  @MainActor
  func loadScreenshotImage(for screenshot: Screenshot) async throws -> NSImage {
    if screenshot.usesVideoStorage,
      let videoPath = screenshot.videoChunkPath,
      let frameOffset = screenshot.frameOffset
    {
      do {
        let frame = try await videoFrame(videoPath: videoPath, frameOffset: frameOffset)
        return NSImage(cgImage: frame.cgImage, size: frame.pixelSize)
      } catch {
        // Frame's chunk is still active (or unreadable) — fall back to the live JPEG if we have one.
        guard let imagePath = screenshot.imagePath, !imagePath.isEmpty else { throw error }
        return try await loadScreenshotImage(relativePath: imagePath)
      }
    }

    let data = try await loadScreenshotData(for: screenshot)
    guard let image = NSImage(data: data) else {
      throw RewindError.invalidImage
    }
    return image
  }

  /// Thumbnail loader for list rows: decodes only a downsampled image via
  /// ImageIO instead of the full-resolution screenshot, so a long search list
  /// doesn't retain full-size NSImages behind a small (e.g. 120×80) view.
  @MainActor
  func loadScreenshotThumbnail(for screenshot: Screenshot, maxPixelSize: Int) async throws -> NSImage {
    let data = try await loadScreenshotData(for: screenshot)
    guard let thumbnail = Self.downsampledImage(from: data, maxPixelSize: maxPixelSize) else {
      throw RewindError.invalidImage
    }
    return thumbnail
  }

  /// Downsample encoded image data to a thumbnail no larger than `maxPixelSize`
  /// on its longest edge, decoding only the reduced image. `nonisolated` + pure
  /// so it is unit-testable and does not touch actor state.
  nonisolated static func downsampledImage(from data: Data, maxPixelSize: Int) -> NSImage? {
    guard maxPixelSize > 0,
      let source = CGImageSourceCreateWithData(data as CFData, nil)
    else { return nil }
    let options: [CFString: Any] = [
      kCGImageSourceCreateThumbnailFromImageAlways: true,
      kCGImageSourceCreateThumbnailWithTransform: true,
      kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
    ]
    guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
      return nil
    }
    return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
  }

  /// Get raw image data for a screenshot (for OCR processing)
  func loadScreenshotData(for screenshot: Screenshot) async throws -> Data {
    if screenshot.usesVideoStorage,
      let videoPath = screenshot.videoChunkPath,
      let offset = screenshot.frameOffset
    {
      do {
        // Load frame and convert to JPEG data
        let image = try await loadVideoFrame(videoPath: videoPath, frameOffset: offset)
        guard let tiffData = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiffData),
          let jpegData = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 1.0])
        else {
          throw RewindError.invalidImage
        }
        return jpegData
      } catch {
        // Frame's chunk is still active (or unreadable) — fall back to the live JPEG if we have one.
        guard let imagePath = screenshot.imagePath, !imagePath.isEmpty else { throw error }
        return try await loadScreenshot(relativePath: imagePath)
      }
    } else if let imagePath = screenshot.imagePath, !imagePath.isEmpty {
      return try await loadScreenshot(relativePath: imagePath)
    } else {
      throw RewindError.screenshotNotFound
    }
  }

  /// Clear the frame cache, and close the reader parked on the last chunk decoded from. The cursor
  /// holds an open file handle for a specific owner's chunk, so it must not outlive their data.
  func clearCache() {
    frameCache.removeAllObjects()
    frameCursor?.cancel()
    frameCursor = nil
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

  /// Reconcile every durable cancellation marker for the current owner. The
  /// marker is removed only after the tombstone/row deletion and file deletion
  /// both succeed; repeating the operation is therefore safe after a restart.
  func reconcileAbandonedVideoChunks() async throws {
    guard let videosDirectory else {
      throw RewindError.storageError("Videos directory not initialized")
    }

    for marker in try RewindAbandonedVideoChunkJournal.markers(in: videosDirectory) {
      let deletedCount = try await abandonVideoChunk(relativePath: marker.relativePath)
      try deleteAbandonedVideoChunkFile(relativePath: marker.relativePath, videosDirectory: videosDirectory)
      try RewindAbandonedVideoChunkJournal.remove(marker)
      corruptedChunks.remove(marker.relativePath)
      log("RewindStorage: Recovered abandoned video chunk, deleted \(deletedCount) DB rows")
    }
  }

  /// Marker creation can fail (for example, transient disk exhaustion). The
  /// owner-transition fallback tombstones the old path first, then cancels only
  /// that still-current writer and removes the file before retargeting storage.
  func recoverAfterMarkerWriteFailure(reservation: RewindVideoChunkReservation) async throws {
    guard let videosDirectory else {
      throw RewindError.storageError("Videos directory not initialized for marker fallback")
    }

    _ = try await abandonVideoChunk(relativePath: reservation.relativePath)
    // The DB tombstone is already durable. Retry the sidecar opportunistically
    // so a post-cancel filesystem failure still has a startup retry path.
    let fallbackMarker = try? RewindAbandonedVideoChunkJournal.record(
      reservation: reservation,
      in: videosDirectory
    )
    await VideoChunkEncoder.shared.forceCancelAfterStorageFallback(for: reservation)
    do {
      try deleteAbandonedVideoChunkFile(relativePath: reservation.relativePath, videosDirectory: videosDirectory)
      if let fallbackMarker {
        try RewindAbandonedVideoChunkJournal.remove(fallbackMarker)
      }
    } catch {
      // The durable tombstone prevents an orphaned partial file from appearing
      // in the timeline. Keep a fallback marker when possible and do not block
      // the nonthrowing effective-owner transition on filesystem cleanup.
      logError("RewindStorage: Could not delete tombstoned fallback chunk", error: error)
    }
    corruptedChunks.remove(reservation.relativePath)
    log("RewindStorage: Recovered abandoned chunk after marker write failure")
  }

  /// Shared recovery classifier for every producer path, including indexer
  /// frame processing, explicit flush, and the encoder's staleness timer.
  func recoverAbandonedVideoChunkIfNeeded(_ error: Error) async throws -> Bool {
    if error is RewindAbandonedVideoChunkError {
      try await reconcileAbandonedVideoChunks()
      return true
    }
    if let markerFailure = error as? RewindAbandonedVideoChunkMarkerWriteError {
      try await recoverAfterMarkerWriteFailure(reservation: markerFailure.reservation)
      return true
    }
    return false
  }

  /// Finalize the active encoder generation and reconcile any durable
  /// abandonment marker before returning an error to non-indexer callers.
  func flushCurrentVideoChunk() async throws -> VideoChunkEncoder.ChunkFlushResult? {
    do {
      return try await VideoChunkEncoder.shared.flushCurrentChunk()
    } catch {
      _ = try await recoverAbandonedVideoChunkIfNeeded(error)
      throw error
    }
  }

  func setAbandonedChunkCleanupFailuresForTesting(_ failures: Int) {
    precondition(failures >= 0)
    abandonedChunkCleanupFailuresForTesting = failures
  }

  func setAbandonedChunkDatabaseFailuresForTesting(_ failures: Int) {
    precondition(failures >= 0)
    abandonedChunkDatabaseFailuresForTesting = failures
  }

  func abandonedVideoChunkMarkerCountForTesting() throws -> Int {
    guard let videosDirectory else {
      throw RewindError.storageError("Videos directory not initialized")
    }
    return try RewindAbandonedVideoChunkJournal.markers(in: videosDirectory).count
  }

  /// Models a process relaunch after the sidecar was durably written but before
  /// any in-process DB reconciliation ran. Tests seed the marker and live rows,
  /// clear only volatile configuration, then exercise normal initialization.
  func clearVolatileConfigurationForProcessRestartTesting() async {
    await VideoChunkEncoder.shared.clearConfigurationAfterUserSwitch()
    screenshotsDirectory = nil
    videosDirectory = nil
    frameCache.removeAllObjects()
    corruptedChunks.removeAll()
  }

  private func abandonVideoChunk(relativePath: String) async throws -> Int {
    guard abandonedChunkDatabaseFailuresForTesting == 0 else {
      abandonedChunkDatabaseFailuresForTesting -= 1
      throw RewindError.storageError("Injected abandoned-chunk database failure")
    }
    return try await RewindDatabase.shared.abandonVideoChunk(relativePath: relativePath)
  }

  private func deleteAbandonedVideoChunkFile(relativePath: String, videosDirectory: URL) throws {
    let fullPath = try RewindAbandonedVideoChunkJournal.videoURL(relativePath: relativePath, in: videosDirectory)
    guard abandonedChunkCleanupFailuresForTesting == 0 else {
      abandonedChunkCleanupFailuresForTesting -= 1
      throw RewindError.storageError("Injected abandoned-chunk cleanup failure")
    }
    if fileManager.fileExists(atPath: fullPath.path) {
      try fileManager.removeItem(at: fullPath)
    }
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

    // The parked reader does hold this file open, so retire it rather than let a deleted chunk keep
    // its bytes on disk until the next unrelated scrub happens to displace the cursor.
    if frameCursor?.videoPath == relativePath {
      frameCursor?.cancel()
      frameCursor = nil
    }

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

  /// Delete empty day directories in both Screenshots and Videos folders.
  ///
  /// The active video path is claimed before `VideoChunkEncoder` creates its
  /// day directory, then read under that same directory-mutation lock below.
  /// This keeps cleanup from observing a stale nil and deleting the empty day
  /// directory during the first-frame writer startup interval.
  func cleanupEmptyDirectories() throws {
    try cleanupEmptyDirectories(beforeVideoCleanupLock: nil)
  }

  /// Performs the cleanup sweep, optionally notifying a synchronous diagnostic
  /// seam immediately before it acquires the video-directory lock. The seam
  /// keeps the writer/cleanup interleaving test deterministic without changing
  /// the production lock scope.
  func cleanupEmptyDirectories(beforeVideoCleanupLock: (@Sendable () -> Void)?) throws {
    // Clean up Screenshots directory
    if let screenshotsDirectory = screenshotsDirectory {
      try cleanupEmptySubdirectories(in: screenshotsDirectory)
    }

    // Clean up Videos directory
    if let videosDirectory = videosDirectory {
      try cleanupEmptyVideoSubdirectories(
        in: videosDirectory,
        beforeVideoCleanupLock: beforeVideoCleanupLock
      )
    }
  }

  /// Resolves the one-level day directory containing an active encoder chunk.
  /// Invalid or nested paths deliberately get no protection: encoder-generated
  /// paths are exactly `<day>/chunk_<time>_<epochMillis>_<unique>.mp4`, and cleanup only owns immediate
  /// day directories beneath the Videos root.
  private static func activeVideoDayDirectory(for relativePath: String?, in videosDirectory: URL) -> URL? {
    guard let relativePath, !relativePath.isEmpty else { return nil }

    let components = relativePath.split(separator: "/", omittingEmptySubsequences: false)
    guard
      components.count == 2,
      components.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." })
    else {
      return nil
    }

    let root = videosDirectory.standardizedFileURL
    let parent =
      root
      .appendingPathComponent(String(components[0]), isDirectory: true)
      .standardizedFileURL

    guard parent.deletingLastPathComponent().standardizedFileURL == root else { return nil }
    return parent
  }

  private func cleanupEmptySubdirectories(in directory: URL, preserving protectedDirectory: URL? = nil) throws {
    // The legacy Screenshots dir may not exist for video-only users — skip it
    // rather than aborting the whole cleanup sweep.
    guard fileManager.fileExists(atPath: directory.path) else { return }

    let contents = try fileManager.contentsOfDirectory(
      at: directory,
      includingPropertiesForKeys: [.isDirectoryKey],
      options: .skipsHiddenFiles
    )

    for url in contents {
      if url.standardizedFileURL == protectedDirectory {
        continue
      }

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

  /// Serializes directory removal with writer startup and derives the active
  /// day-directory protection from the reservation inside that same lock.
  private func cleanupEmptyVideoSubdirectories(
    in directory: URL,
    beforeVideoCleanupLock: (@Sendable () -> Void)?
  ) throws {
    beforeVideoCleanupLock?()
    try RewindVideoDirectoryMutation.withActiveChunk { activeVideoChunkReservation in
      let protectedDirectory = Self.activeVideoDayDirectory(
        for: activeVideoChunkReservation?.relativePath,
        in: directory
      )
      try cleanupEmptySubdirectories(in: directory, preserving: protectedDirectory)
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
  /// The storage roots to measure, or `nil` when none is resolved.
  ///
  /// "Not initialized" and "zero bytes on disk" are different facts, and summing
  /// an unresolved root as 0 conflated them: both directories are `nil` until
  /// `initialize()` runs and again after `resetForUserSwitch()`, so a store
  /// holding tens of megabytes reported a confident zero. Observed live on a
  /// running bundle as `total_frames: 328` alongside `storage_bytes: 0`, while
  /// two sibling bundles on the same account reported ~44–48 MB.
  static func resolvedStorageRoots(screenshots: URL?, videos: URL?) -> [URL]? {
    let roots = [screenshots, videos].compactMap { $0 }
    return roots.isEmpty ? nil : roots
  }

  func getTotalStorageSize() async throws -> Int64 {
    guard
      let roots = Self.resolvedStorageRoots(
        screenshots: screenshotsDirectory, videos: videosDirectory)
    else {
      throw RewindError.storageError("Rewind storage is not initialized; total size is unknown")
    }

    var totalSize: Int64 = 0
    for root in roots {
      totalSize += try calculateDirectorySize(at: root)
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

      chunks.append(
        VideoChunkInfo(
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
