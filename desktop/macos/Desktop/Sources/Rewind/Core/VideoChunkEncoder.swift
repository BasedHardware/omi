@preconcurrency import AVFoundation
import AppKit
import CoreGraphics
import Foundation
import Sentry
import os

/// Identifies one writer's ownership of a video chunk. The generation remains
/// necessary even though new paths include a unique suffix: older stored paths
/// and test seams can still use second-granular names.
struct RewindVideoChunkReservation: Equatable, Sendable {
  let generation: UInt64
  let relativePath: String
}

/// Signals that one exact writer generation was cancelled before it produced a
/// durable MP4 trailer. The encoder deliberately emits this ownership token
/// instead of reaching into persistence: the indexer/storage boundary owns the
/// corresponding database and filesystem recovery.
struct RewindAbandonedVideoChunkError: Error, Sendable {
  let relativePath: String
}

/// A marker could not be persisted before a writer needed cancellation. The
/// storage owner must use its DB-first fallback before it force-cancels this
/// exact reservation.
struct RewindAbandonedVideoChunkMarkerWriteError: Error, Sendable {
  let reservation: RewindVideoChunkReservation
}

enum RewindVideoChunkCancellationResult: Sendable {
  case noActiveChunk
  case markerRecorded(RewindVideoChunkReservation)
  case markerWriteFailed(RewindVideoChunkReservation)
}

private enum RewindVideoChunkLifecyclePhase: Equatable, Sendable {
  case writing
  case finalizing

  var diagnosticName: String {
    switch self {
    case .writing: return "writing"
    case .finalizing: return "finalizing"
    }
  }
}

/// Actor-local ownership for the currently installed video writer.
///
/// A finalizer captures the reservation before awaiting AVFoundation. Its later
/// cleanup may only clear that exact reservation, never a replacement writer.
struct RewindVideoChunkLifecycle: Equatable, Sendable {
  private(set) var activeReservation: RewindVideoChunkReservation?
  private var phase: RewindVideoChunkLifecyclePhase?

  mutating func install(_ reservation: RewindVideoChunkReservation) {
    activeReservation = reservation
    phase = .writing
  }

  /// Atomically transitions the current writer to finalization. A writer may
  /// only be finalized once; concurrent callers must leave the owner alone.
  @discardableResult
  mutating func beginFinalization(of reservation: RewindVideoChunkReservation) -> Bool {
    guard activeReservation == reservation, phase == .writing else {
      return false
    }
    phase = .finalizing
    return true
  }

  /// Clears the active reservation when it is still owned by `expected`.
  /// `nil` is an unconditional lifecycle reset used by explicit cancellation.
  @discardableResult
  mutating func reset(onlyIfCurrent expected: RewindVideoChunkReservation? = nil) -> RewindVideoChunkReservation? {
    if let expected, activeReservation != expected {
      return nil
    }
    let releasedReservation = activeReservation
    activeReservation = nil
    phase = nil
    return releasedReservation
  }

  func owns(_ reservation: RewindVideoChunkReservation) -> Bool {
    activeReservation == reservation
  }

  func isWriting(_ reservation: RewindVideoChunkReservation) -> Bool {
    activeReservation == reservation && phase == .writing
  }

  var diagnosticPhase: String {
    phase?.diagnosticName ?? "idle"
  }
}

/// Encodes screenshot frames into H.265 video chunks using VideoToolbox for efficient storage.
actor VideoChunkEncoder {
  static let shared = VideoChunkEncoder()

  // MARK: - Configuration

  private let chunkDuration: TimeInterval = 60.0  // 60-second chunks
  /// First chunk after launch finalizes faster so Rewind shows screenshots within
  /// seconds of monitoring starting, instead of waiting up to 60s + 10s stale grace.
  /// The Rewind UI filters out the active (unfinalized) chunk, so without this you'd
  /// see nothing on the Rewind page for ~1-2 minutes after every launch.
  private let firstChunkDuration: TimeInterval = 5.0
  private var frameRate: Double {
    let interval = RewindSettings.shared.effectiveCaptureInterval(isOnBattery: PowerMonitor.cachedBatteryState())
    return 1.0 / interval  // e.g. 0.5s interval = 2 FPS
  }
  private let maxResolution: CGFloat = 3000  // Maximum dimension

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
    // Use the chunk's frozen rate while a chunk is active so a mid-chunk rate
    // change can't shrink the cap and trip a spurious buffer-overflow reset.
    Int(chunkDuration * (currentChunkFrameRate ?? frameRate)) + 20
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
  /// Capture frame rate frozen at chunk start. Presentation timestamps and the
  /// buffer cap must use one rate for a chunk's whole lifetime: `frameRate` is a
  /// live property of the battery state, and a mid-chunk change (AC power plugged
  /// in shrinks the capture interval 3x → higher rate) would make a later frame's
  /// PTS (`frameOffset / rate`) fall below an already-appended sample's PTS,
  /// which AVAssetWriter rejects as non-monotonic — dropping frames and, past the
  /// failure threshold, discarding the entire in-progress chunk.
  private var currentChunkFrameRate: Double?
  private(set) var currentChunkPath: String?
  private var chunkLifecycle = RewindVideoChunkLifecycle()
  /// Completion waiters for the reservation currently writing its MP4 trailer.
  /// A flush is a durability barrier: callers that arrive during finalization
  /// must wait for that same writer rather than treating it as an empty buffer.
  private var inFlightFinalization: InFlightFinalization?
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

  // Test-only synchronization hooks. They are unset in production and let the
  // behavioral regression test hold a real writer after the in-flight state is
  // published, without relying on wall-clock scheduling.
  private var beforeFinishWritingForTesting: (@Sendable () async -> Void)?
  private var finalizationJoinedForTesting: (@Sendable () -> Void)?
  /// When set, appends succeed this many times before every later append fails.
  /// This intentionally models an AVFoundation append failure after rows may
  /// already have been persisted for earlier frames in the same chunk.
  private var appendFailureAfterSuccessfulFramesForTesting: Int?
  /// Exercises the DB-first owner-transition fallback when a sidecar cannot
  /// be created before cancellation.
  private var abandonmentMarkerWriteFailuresForTesting = 0
  /// Exercises finalization recovery at the indexer stop boundary without
  /// relying on an AVFoundation codec failure.
  private var finishWritingFailuresForTesting = 0

  // MARK: - Types

  struct EncodedFrame: Sendable {
    let videoChunkPath: String  // Relative path to .mp4
    let frameOffset: Int  // Frame index within chunk
    let timestamp: Date
  }

  struct ChunkFlushResult: Sendable {
    let videoChunkPath: String
    let frames: [EncodedFrame]
  }

  private struct InFlightFinalization {
    let reservation: RewindVideoChunkReservation
    var waiters: [CheckedContinuation<Bool, Error>] = []
  }

  // MARK: - Initialization

  private init() {}

  /// Initialize the encoder with the videos directory
  func initialize(videosDirectory: URL) async throws {
    if isInitialized {
      guard self.videosDirectory != videosDirectory else { return }
      throw RewindError.storageError("Video encoder must reset before changing storage owner")
    }

    self.videosDirectory = videosDirectory
    isInitialized = true
    log("VideoChunkEncoder: Initialized at \(videosDirectory.path)")
  }

  func videosDirectoryForTesting() -> URL? {
    videosDirectory
  }

  func setFinalizationHooksForTesting(
    beforeFinishWriting: (@Sendable () async -> Void)?,
    finalizationJoined: (@Sendable () -> Void)?
  ) {
    beforeFinishWritingForTesting = beforeFinishWriting
    finalizationJoinedForTesting = finalizationJoined
  }

  func setAppendFailureAfterSuccessfulFramesForTesting(_ successfulFrames: Int?) {
    if let successfulFrames {
      precondition(successfulFrames >= 0)
    }
    appendFailureAfterSuccessfulFramesForTesting = successfulFrames
  }

  func setAbandonmentMarkerWriteFailuresForTesting(_ failures: Int) {
    precondition(failures >= 0)
    abandonmentMarkerWriteFailuresForTesting = failures
  }

  func setFinishWritingFailuresForTesting(_ failures: Int) {
    precondition(failures >= 0)
    finishWritingFailuresForTesting = failures
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
      if let abandonment = try await emergencyReset(reason: "buffer_overflow") {
        throw abandonment
      }
    }

    // Check if aspect ratio changed significantly.
    // Debounce: require the new ratio to be stable for aspectRatioStabilityDelay before
    // switching chunks. Rapid app switching (e.g. Firefox ↔ terminal) previously caused
    // bursts of 1-3 frame chunks whose hevc_videotoolbox encoder hung on finalization,
    // blocking the actor for 10s per event and chaining into a cascade.
    if let currentInputSize = currentChunkInputSize,
      hasSignificantAspectRatioChange(from: currentInputSize, to: newFrameSize)
    {
      let now = Date()
      let pendingMatches =
        pendingAspectRatioSize.map {
          !hasSignificantAspectRatioChange(from: $0, to: newFrameSize)
        } ?? false

      if pendingMatches,
        let since = pendingAspectRatioSince,
        now.timeIntervalSince(since) >= aspectRatioStabilityDelay
      {
        // New aspect ratio has been stable for the required delay — commit the switch
        log(
          "VideoChunkEncoder: Aspect ratio changed significantly (\(currentInputSize) -> \(newFrameSize)), starting new chunk"
        )
        pendingAspectRatioSize = nil
        pendingAspectRatioSince = nil
        // Finalization can suspend while AVFoundation finishes the old writer.
        // A cancellation/restart that wins during that suspension owns the
        // encoder now, so this stale frame must not continue into the new chunk.
        guard try await finalizeCurrentChunk() else {
          return nil
        }
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
      currentChunkFrameRate = frameRate  // freeze for this chunk's whole lifetime
      let chunkPath = Self.generateChunkPath(for: timestamp)
      currentChunkPath = chunkPath
      frameOffsetInChunk = 0
      currentChunkInputSize = newFrameSize

      // Start native HEVC writer for this chunk
      do {
        chunkLifecycle.install(
          try startVideoWriter(
            for: chunkPath,
            videosDir: videosDir,
            imageSize: newFrameSize
          ))
        consecutiveWriteFailures = 0  // Reset on successful start
        writerNotReadyCount = 0
        encoderRestartCount += 1
      } catch {
        consecutiveWriteFailures += 1
        logError(
          "VideoChunkEncoder: Failed to start video writer (\(consecutiveWriteFailures)/\(maxConsecutiveFailures))",
          error: error)

        // Reset the half-initialized chunk state so the NEXT frame cleanly retries
        // starting the writer. Without this, currentChunkStartTime stays set while
        // writer state is nil, so every subsequent frame skips the start path and
        // fails inside writeFrame() with "Video writer not ready" — needlessly dropping
        // ~5 frames (2.5s of Rewind footage) and emitting misleading write-failure
        // errors until the emergency-reset threshold finally clears the state.
        currentChunkStartTime = nil
        currentChunkFrameRate = nil
        currentChunkPath = nil
        _ = chunkLifecycle.reset()
        currentChunkInputSize = nil
        currentOutputSize = nil
        frameOffsetInChunk = 0

        if consecutiveWriteFailures >= maxConsecutiveFailures {
          logError("VideoChunkEncoder: Too many video writer failures, performing emergency reset")
          if let abandonment = try await emergencyReset(reason: "writer_start_failure") {
            throw abandonment
          }
        }
        throw error
      }
    }

    guard let reservation = chunkLifecycle.activeReservation else {
      return nil
    }

    // Write frame to the encoder FIRST (CGImage not stored after this). Only a
    // successful write may consume a frame index: if the write throws, the
    // caller skips the DB insert for this frame, so advancing frameOffsetInChunk
    // / appending a timestamp here would desync every later frame in the chunk
    // by one (DB frameOffset N pointing at real sample N-1, and the last record
    // pointing past the end of the video). Record the frame only after success.
    do {
      guard try await writeFrame(image: image, reservation: reservation) else {
        return nil
      }
      guard chunkLifecycle.isWriting(reservation) else {
        return nil
      }
      consecutiveWriteFailures = 0  // Reset on successful write
      resetStalenessTimer()
    } catch let abandonment as RewindAbandonedVideoChunkError {
      throw abandonment
    } catch {
      // `waitForWriterInputReady` can suspend. If a cancel/restart replaced
      // this writer while it was waiting, the old call must not increment or
      // emergency-reset the replacement writer.
      guard chunkLifecycle.isWriting(reservation) else {
        return nil
      }
      consecutiveWriteFailures += 1
      logError(
        "VideoChunkEncoder: Failed to write frame (\(consecutiveWriteFailures)/\(maxConsecutiveFailures))", error: error
      )

      if consecutiveWriteFailures >= maxConsecutiveFailures {
        logError("VideoChunkEncoder: Too many write failures, performing emergency reset")
        if let abandonment = try await emergencyReset(reason: "write_failure") {
          throw abandonment
        }
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
      guard try await finalizeCurrentChunk() else {
        return nil
      }
      hasFinalizedAnyChunk = true
      return frameInfo
    }

    return frameInfo
  }

  /// Force flush current buffer (app termination, etc.)
  func flushCurrentChunk() async throws -> ChunkFlushResult? {
    guard let chunkPath = currentChunkPath,
      !frameTimestamps.isEmpty,
      let reservation = chunkLifecycle.activeReservation
    else {
      return nil
    }

    let frames = frameTimestamps.enumerated().map { index, timestamp in
      EncodedFrame(
        videoChunkPath: chunkPath,
        frameOffset: index,
        timestamp: timestamp
      )
    }

    // A second flush can arrive while the owner is suspended in
    // `finishWriting`. Joining that completion makes shutdown wait until the
    // MP4 trailer is durable instead of incorrectly reporting an empty buffer.
    if inFlightFinalization?.reservation == reservation {
      guard try await joinInFlightFinalization(reservation) else {
        throw RewindError.storageError("Video chunk finalization was cancelled before flush completed")
      }
      return ChunkFlushResult(videoChunkPath: chunkPath, frames: frames)
    }

    guard try await finalizeCurrentChunk() else {
      throw RewindError.storageError("Video chunk finalization was cancelled before flush completed")
    }

    return ChunkFlushResult(videoChunkPath: chunkPath, frames: frames)
  }

  // MARK: - Video Writer Management

  private func startVideoWriter(
    for relativePath: String,
    videosDir: URL,
    imageSize: CGSize
  ) throws -> RewindVideoChunkReservation {
    try RewindVideoDirectoryMutation.startActiveChunk(at: relativePath) {
      try startVideoWriterLocked(for: relativePath, videosDir: videosDir, imageSize: imageSize)
    }
  }

  /// Holds the shared directory mutation lock through day-directory creation and
  /// `AVAssetWriter.startWriting()`. Retention cleanup can otherwise remove an
  /// empty just-created day directory before the writer materializes its file.
  private func startVideoWriterLocked(for relativePath: String, videosDir: URL, imageSize: CGSize) throws {
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

    let settings = Self.hevcVideoSettings(
      width: width,
      height: height,
      bitrate: bitrate,
      frameRate: frameRate
    )

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
        kCVPixelBufferIOSurfacePropertiesKey as String: [:],
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
      "max_resolution": Int(maxResolution),
    ]
    SentrySDK.addBreadcrumb(breadcrumb)
  }

  /// HEVC's VideoToolbox encoder rejects
  /// `AVVideoMaxKeyFrameIntervalDurationKey` on some Intel/macOS combinations
  /// (including hvc1), terminating the app while constructing the writer input.
  /// Keep the common HEVC settings in one testable factory and omit that
  /// unsupported property; keyframe cadence is encoder-controlled instead.
  nonisolated static func hevcVideoSettings(
    width: Int,
    height: Int,
    bitrate: Int,
    frameRate: Double
  ) -> [String: Any] {
    [
      AVVideoCodecKey: AVVideoCodecType.hevc,
      AVVideoWidthKey: width,
      AVVideoHeightKey: height,
      AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: bitrate,
        AVVideoExpectedSourceFrameRateKey: max(1, Int(ceil(frameRate))),
        AVVideoAllowFrameReorderingKey: false,
      ],
    ]
  }

  /// Presentation timestamp (in seconds) for the frame at `frameOffset` within a chunk.
  /// Callers pass the offset of the frame being written now; the writer requires strictly
  /// increasing timestamps, so this must be a strictly increasing function of frameOffset
  /// for 0, 1, 2, … `nonisolated static` so it is synchronously unit-testable.
  nonisolated static func framePresentationSeconds(frameOffset: Int, frameRate: Double) -> Double {
    Double(max(0, frameOffset)) / frameRate
  }

  /// The frame rate a chunk's presentation timestamps are computed against: the
  /// rate frozen when the chunk started, falling back to the live rate only
  /// before the first frame. Using a single rate for the whole chunk keeps
  /// `framePresentationSeconds(frameOffset:)` strictly increasing even when the
  /// live capture rate changes mid-chunk (e.g. AC power connected). `nonisolated
  /// static` so it is synchronously unit-testable.
  nonisolated static func chunkPresentationFrameRate(frozen: Double?, live: Double) -> Double {
    frozen ?? live
  }

  /// Appends a frame only while `reservation` still owns a writing-phase
  /// chunk. `false` means a cancel, restart, or finalization won while this
  /// method was suspended and the caller must not touch replacement state.
  private func writeFrame(image: CGImage, reservation: RewindVideoChunkReservation) async throws -> Bool {
    guard chunkLifecycle.isWriting(reservation) else {
      return false
    }

    guard let input = writerInput,
      let adaptor = pixelBufferAdaptor,
      let outputSize = currentOutputSize
    else {
      writerNotReadyCount += 1

      if writerNotReadyCount >= maxConsecutiveNotReadyFailures {
        logError("VideoChunkEncoder: Video writer not ready \(writerNotReadyCount)x, resetting encoder state")
        if let abandonment = try await emergencyReset(reason: "writer_not_ready_loop") {
          throw abandonment
        }
      } else {
        log("VideoChunkEncoder: Video writer not ready (\(writerNotReadyCount)/\(maxConsecutiveNotReadyFailures))")
      }

      throw RewindError.storageError("Video writer not ready")
    }

    guard try await waitForWriterInputReady(input, reservation: reservation) else {
      return false
    }
    guard chunkLifecycle.isWriting(reservation) else {
      return false
    }

    // Keep this actor-isolated: autoreleasepool's closure is treated as a sending
    // boundary by Swift 6, which cannot safely retain the AVFoundation adaptor.
    let pixelBuffer = try createPixelBuffer(from: image, size: outputSize, adaptor: adaptor)

    // frameOffsetInChunk is the index of the frame being written RIGHT NOW; it is
    // incremented in addFrame only AFTER this write succeeds (so a failed write does
    // not consume an offset). The presentation timestamp must therefore be derived
    // from the current offset directly. A stale `- 1` here (left over from when the
    // offset was pre-incremented before writeFrame) makes frame 0 and frame 1 both
    // resolve to PTS 0, and AVAssetWriterInputPixelBufferAdaptor.append requires
    // strictly increasing timestamps — so every chunk's second frame is rejected,
    // failures cascade to an emergency reset, and no video chunk is ever persisted.
    let presentationTime = CMTime(
      seconds: Self.framePresentationSeconds(
        frameOffset: frameOffsetInChunk,
        frameRate: Self.chunkPresentationFrameRate(frozen: currentChunkFrameRate, live: frameRate)
      ),
      preferredTimescale: 600
    )
    if let successfulFrames = appendFailureAfterSuccessfulFramesForTesting {
      guard successfulFrames > 0 else {
        throw RewindError.storageError("Injected append failure for abandoned-chunk recovery test")
      }
      appendFailureAfterSuccessfulFramesForTesting = successfulFrames - 1
    }
    guard adaptor.append(pixelBuffer, withPresentationTime: presentationTime) else {
      if let writerError = assetWriter?.error {
        throw RewindError.storageWriteFailed("Failed to append frame to HEVC writer", underlying: writerError)
      }
      throw RewindError.storageError("Failed to append frame to HEVC writer: unknown error")
    }
    writerNotReadyCount = 0
    return true
  }

  /// Finalize the writer that owned the encoder at entry.
  ///
  /// `finishWriting` suspends this actor. A cancellation can therefore install a
  /// newer writer before this continuation resumes. Returning `false` tells the
  /// caller that its captured writer lost ownership, so it must not mutate the
  /// newer chunk after the await.
  private func finalizeCurrentChunk() async throws -> Bool {
    stalenessCheckTask?.cancel()
    stalenessCheckTask = nil

    guard let reservation = chunkLifecycle.activeReservation,
      chunkLifecycle.beginFinalization(of: reservation)
    else {
      return false
    }

    guard let input = writerInput, let writer = assetWriter else {
      return resetCurrentChunkState(onlyIfCurrent: reservation)
    }

    let frameCount = frameTimestamps.count
    input.markAsFinished()
    inFlightFinalization = InFlightFinalization(reservation: reservation)
    if let beforeFinishWritingForTesting {
      await beforeFinishWritingForTesting()
    }
    guard chunkLifecycle.owns(reservation) else {
      resolveInFlightFinalization(reservation, with: .success(false))
      return false
    }

    do {
      try await finishWriting(writer)
    } catch {
      // A cancellation/restart may have replaced this writer while its finish
      // callback was pending. That stale completion is an expected no-op for
      // the caller rather than an error from the newer generation.
      guard chunkLifecycle.owns(reservation) else {
        resolveInFlightFinalization(reservation, with: .success(false))
        return false
      }

      // A failed finish may leave an MP4 without its trailer. Record its exact
      // path before cancelling the writer so recovery survives a crash between
      // this failure and the indexer/storage cleanup.
      switch cancelCurrentChunkAfterRecordingAbandonment() {
      case .markerRecorded(let abandonedReservation):
        let abandonment = RewindAbandonedVideoChunkError(relativePath: abandonedReservation.relativePath)
        resolveInFlightFinalization(reservation, with: .failure(abandonment))
        throw abandonment
      case .markerWriteFailed(let failedReservation):
        let markerFailure = RewindAbandonedVideoChunkMarkerWriteError(reservation: failedReservation)
        resolveInFlightFinalization(reservation, with: .failure(markerFailure))
        throw markerFailure
      case .noActiveChunk:
        resolveInFlightFinalization(reservation, with: .success(false))
        return false
      }
    }

    guard resetCurrentChunkState(onlyIfCurrent: reservation) else {
      resolveInFlightFinalization(reservation, with: .success(false))
      return false
    }
    resolveInFlightFinalization(reservation, with: .success(true))

    log(
      "VideoChunkEncoder: Finalized chunk with \(frameCount) frames (restartCount=\(encoderRestartCount), emergencyResets=\(emergencyResetCount))"
    )
    return true
  }

  /// Joins the active writer's trailer write without cancelling it. A flush is
  /// a durability boundary; explicit `cancel()` remains the only path that can
  /// abandon a finalization and resolve its waiters with `false`.
  private func joinInFlightFinalization(_ reservation: RewindVideoChunkReservation) async throws -> Bool {
    guard inFlightFinalization?.reservation == reservation else {
      return false
    }

    return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Bool, Error>) in
      guard var finalization = inFlightFinalization, finalization.reservation == reservation else {
        continuation.resume(returning: false)
        return
      }

      finalization.waiters.append(continuation)
      inFlightFinalization = finalization
      finalizationJoinedForTesting?()
    }
  }

  /// Resolves every flush that joined this exact writer. Clearing the stored
  /// continuations before resuming them prevents a resumed caller from joining
  /// the completed generation again.
  private func resolveInFlightFinalization(
    _ reservation: RewindVideoChunkReservation,
    with result: Result<Bool, Error>
  ) {
    guard let finalization = inFlightFinalization, finalization.reservation == reservation else {
      return
    }

    inFlightFinalization = nil
    finalization.waiters.forEach { $0.resume(with: result) }
  }

  /// Clears encoder state only if the expected reservation still owns it.
  /// This guard must run before changing any field: a stale finalizer is not
  /// allowed to touch a newer writer after an actor reentrancy point.
  @discardableResult
  private func resetCurrentChunkState(onlyIfCurrent expectedReservation: RewindVideoChunkReservation? = nil) -> Bool {
    if let expectedReservation, !chunkLifecycle.owns(expectedReservation) {
      return false
    }
    let activeChunkReservation = chunkLifecycle.reset()

    // Reset state (timestamps only - no CGImages retained)
    frameTimestamps.removeAll()
    currentChunkStartTime = nil
    currentChunkFrameRate = nil
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

    RewindVideoDirectoryMutation.finishActiveChunk(activeChunkReservation)
    return true
  }

  // MARK: - Staleness Detection

  /// Reset the staleness timer after each successful frame write.
  /// If no new frame arrives within chunkDuration + 10s, finalize the chunk
  /// to release the H.265 hardware encoder context.
  private func resetStalenessTimer() {
    stalenessCheckTask?.cancel()
    guard let reservation = chunkLifecycle.activeReservation,
      chunkLifecycle.isWriting(reservation)
    else {
      stalenessCheckTask = nil
      return
    }
    let timeout = chunkDuration + 10.0
    stalenessCheckTask = Task { [weak self, reservation] in
      try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
      guard !Task.isCancelled else { return }
      await self?.finalizeStaleChunkIfNeeded(onlyIfCurrent: reservation)
    }
  }

  /// Finalize a chunk that has gone stale (no new frames for longer than chunk duration).
  private func finalizeStaleChunkIfNeeded(onlyIfCurrent reservation: RewindVideoChunkReservation) async {
    guard chunkLifecycle.isWriting(reservation) else { return }
    guard let startTime = currentChunkStartTime else { return }

    let age = Date().timeIntervalSince(startTime)
    guard age >= chunkDuration else { return }

    log(
      "VideoChunkEncoder: Stale chunk detected (age: \(String(format: "%.0f", age))s, no new frames) — finalizing to release encoder resources"
    )

    let breadcrumb = Breadcrumb(level: .warning, category: "video_encoder")
    breadcrumb.message = "Stale chunk finalized"
    breadcrumb.data = [
      "age_seconds": Int(age),
      "frame_count": frameTimestamps.count,
      "chunk_path": currentChunkPath ?? "none",
    ]
    SentrySDK.addBreadcrumb(breadcrumb)

    do {
      _ = try await finalizeCurrentChunk()
    } catch {
      do {
        let recovered = try await RewindStorage.shared.recoverAbandonedVideoChunkIfNeeded(error)
        if !recovered {
          logError("VideoChunkEncoder: Failed to finalize stale video chunk", error: error)
        }
      } catch {
        logError("VideoChunkEncoder: Failed to recover stale video chunk", error: error)
      }
    }
  }

  func finalizeStaleChunkForTesting() async {
    guard let reservation = chunkLifecycle.activeReservation else { return }
    await finalizeStaleChunkIfNeeded(onlyIfCurrent: reservation)
  }

  // MARK: - Helpers

  /// Builds a collision-proof chunk path while keeping absolute capture time
  /// in the filename for recovery. The UUID prevents a cancel/restart within
  /// one millisecond from overwriting a prior durable chunk.
  nonisolated static func generateChunkPath(for timestamp: Date, uniqueID: UUID = UUID()) -> String {
    let dateFormatter = DateFormatter()
    dateFormatter.locale = Locale(identifier: "en_US_POSIX")
    dateFormatter.timeZone = .current
    dateFormatter.dateFormat = "yyyy-MM-dd"
    let dayString = dateFormatter.string(from: timestamp)

    let timeFormatter = DateFormatter()
    timeFormatter.locale = Locale(identifier: "en_US_POSIX")
    timeFormatter.timeZone = .current
    timeFormatter.dateFormat = "HHmmss"
    let timeString = timeFormatter.string(from: timestamp)
    let epochMilliseconds = Int64((timestamp.timeIntervalSince1970 * 1_000).rounded(.down))

    return "\(dayString)/chunk_\(timeString)_\(epochMilliseconds)_\(uniqueID.uuidString.lowercased()).mp4"
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
    guard
      let context = CGContext(
        data: baseAddress,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: bytesPerRow,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
      )
    else {
      throw RewindError.storageError("Failed to create pixel buffer context")
    }

    context.interpolationQuality = .high
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return pixelBuffer
  }

  private func finishWriting(_ writer: AVAssetWriter) async throws {
    guard finishWritingFailuresForTesting == 0 else {
      finishWritingFailuresForTesting -= 1
      throw RewindError.storageError("Injected finishWriting failure for abandoned-chunk recovery test")
    }
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
            continuation.resume(
              throwing: RewindError.storageError(
                "HEVC writer failed: \(Self.writerStatusDescription(writerBox.writer.status))"))
          }
        default:
          continuation.resume(
            throwing: RewindError.storageError(
              "HEVC writer ended in unexpected state: \(Self.writerStatusDescription(writerBox.writer.status))"))
        }
      }
    }
  }

  /// Waits for readiness without letting a stale caller resume into a newer
  /// generation. The ownership check runs both before and after each suspend.
  private func waitForWriterInputReady(
    _ input: AVAssetWriterInput,
    reservation: RewindVideoChunkReservation
  ) async throws -> Bool {
    let deadline = Date().addingTimeInterval(2.0)
    while !input.isReadyForMoreMediaData {
      guard chunkLifecycle.isWriting(reservation) else {
        return false
      }
      if Date() >= deadline {
        throw RewindError.storageError("Video writer input backpressured")
      }
      try await Task.sleep(nanoseconds: 10_000_000)
      guard chunkLifecycle.isWriting(reservation) else {
        return false
      }
    }
    return chunkLifecycle.isWriting(reservation)
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

  /// Cancel any in-progress encoding. A marker is written before the writer is
  /// touched; callers that own persistence can use the marker-write-failure
  /// result to execute the DB-first fallback.
  @discardableResult
  func cancel() -> RewindVideoChunkCancellationResult {
    cancelCurrentChunkAfterRecordingAbandonment()
  }

  /// Stop the current owner before its database/directory configuration is
  /// released. RewindStorage reconciles the marker or performs the fallback,
  /// then calls `clearConfigurationAfterUserSwitch`.
  @discardableResult
  func resetForUserSwitch() -> RewindVideoChunkCancellationResult {
    cancelCurrentChunkAfterRecordingAbandonment()
  }

  func clearConfigurationAfterUserSwitch() {
    videosDirectory = nil
    isInitialized = false
    hasFinalizedAnyChunk = false
  }

  /// This is intentionally only callable by the storage owner after it has
  /// tombstoned the old path in the still-open old-user database.
  func forceCancelAfterStorageFallback(for reservation: RewindVideoChunkReservation) {
    guard chunkLifecycle.owns(reservation) else { return }
    cancelCurrentChunkState()
  }

  /// Emergency reset when encoding fails repeatedly or buffer overflows
  /// Clears all state and allows fresh start on next frame
  private func emergencyReset(reason: String = "failure_threshold") async throws -> RewindAbandonedVideoChunkError? {
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
      "chunk_path": currentChunkPath ?? "none",
    ]
    SentrySDK.addBreadcrumb(breadcrumb)

    logError(
      "VideoChunkEncoder: Emergency reset (reason=\(reason)) - dropping \(droppedFrames) frames to prevent memory leak")

    switch cancelCurrentChunkAfterRecordingAbandonment() {
    case .noActiveChunk:
      log("VideoChunkEncoder: Emergency reset complete, ready for new frames")
      return nil
    case .markerRecorded(let abandonedReservation):
      log("VideoChunkEncoder: Emergency reset complete, ready for new frames")
      return RewindAbandonedVideoChunkError(relativePath: abandonedReservation.relativePath)
    case .markerWriteFailed(let failedReservation):
      throw RewindAbandonedVideoChunkMarkerWriteError(reservation: failedReservation)
    }
  }

  /// Records the recovery sidecar before an AVFoundation cancellation can make
  /// the partial MP4 unreadable. This actor contains no persistence dependency;
  /// RewindStorage later consumes the durable record.
  private func cancelCurrentChunkAfterRecordingAbandonment() -> RewindVideoChunkCancellationResult {
    if let reservation = chunkLifecycle.activeReservation {
      do {
        try recordAbandonment(reservation)
      } catch {
        logError("VideoChunkEncoder: Refusing to cancel chunk without durable recovery marker", error: error)
        return .markerWriteFailed(reservation)
      }
      cancelCurrentChunkState()
      return .markerRecorded(reservation)
    }

    cancelCurrentChunkState()
    return .noActiveChunk
  }

  private func recordAbandonment(_ reservation: RewindVideoChunkReservation) throws {
    guard let videosDirectory else {
      throw RewindError.storageError("Video encoder has no storage directory for abandoned chunk")
    }
    guard abandonmentMarkerWriteFailuresForTesting == 0 else {
      abandonmentMarkerWriteFailuresForTesting -= 1
      throw RewindError.storageError("Injected abandoned-chunk marker write failure")
    }
    _ = try RewindAbandonedVideoChunkJournal.record(reservation: reservation, in: videosDirectory)
  }

  private func cancelCurrentChunkState() {
    stalenessCheckTask?.cancel()
    stalenessCheckTask = nil
    let cancelledFinalization = inFlightFinalization?.reservation
    writerInput?.markAsFinished()
    assetWriter?.cancelWriting()
    _ = resetCurrentChunkState()
    if let cancelledFinalization {
      resolveInFlightFinalization(cancelledFinalization, with: .success(false))
    }
    writerNotReadyCount = 0
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
    let lifecyclePhase: String
    let queueBucket: String
    let isInitialized: Bool
    let hasStalenessTimer: Bool
    let finalizationWaiterBucket: String
  }

  nonisolated static func diagnosticCountBucket(_ count: Int) -> String {
    switch count {
    case ...0: return "none"
    case 1: return "one"
    case 2...10: return "few"
    default: return "many"
    }
  }

  /// Get current buffer and lifecycle status for memory diagnostics.
  func getBufferStatus() -> EncoderStatus {
    let now = Date()
    let finalizationWaiterCount = inFlightFinalization?.waiters.count ?? 0
    return EncoderStatus(
      frameCount: frameTimestamps.count,
      maxBufferFrames: maxBufferFrames,
      oldestFrameAge: frameTimestamps.first.map { now.timeIntervalSince($0) },
      currentChunkAge: currentChunkStartTime.map { now.timeIntervalSince($0) },
      isEncoderRunning: assetWriter != nil,
      consecutiveWriteFailures: consecutiveWriteFailures,
      encoderRestartCount: encoderRestartCount,
      emergencyResetCount: emergencyResetCount,
      writerNotReadyCount: writerNotReadyCount,
      lifecyclePhase: chunkLifecycle.diagnosticPhase,
      queueBucket: Self.diagnosticCountBucket(frameTimestamps.count),
      isInitialized: isInitialized,
      hasStalenessTimer: stalenessCheckTask != nil,
      finalizationWaiterBucket: Self.diagnosticCountBucket(finalizationWaiterCount)
    )
  }
}

private final class AssetWriterBox: @unchecked Sendable {
  let writer: AVAssetWriter

  init(_ writer: AVAssetWriter) {
    self.writer = writer
  }
}

/// State owned exclusively by `RewindVideoDirectoryMutation`'s lock.
///
/// The generation disambiguates writers even for legacy or test paths that
/// retain a second-granular name.
private struct RewindVideoDirectoryMutationState: Sendable {
  var activeReservation: RewindVideoChunkReservation?
  var nextGeneration: UInt64 = 0
}

/// Coordinates video-directory mutation and the active writer reservation.
/// No actor hop or asynchronous work occurs while its lock is held. The
/// `withLockUnchecked` calls below are confined to this synchronous critical
/// section, so actor-isolated startup and cleanup closures cannot escape or
/// suspend while they hold the lock.
enum RewindVideoDirectoryMutation {
  private static let lock = OSAllocatedUnfairLock<RewindVideoDirectoryMutationState>(
    initialState: RewindVideoDirectoryMutationState()
  )

  /// Claims the active chunk before its writer creates the day directory. The
  /// reservation remains after a successful startup and is released by
  /// `finishActiveChunk(_:)` once that exact writer has finalized or been
  /// cancelled.
  static func startActiveChunk(
    at relativePath: String,
    _ startup: () throws -> Void
  ) rethrows -> RewindVideoChunkReservation {
    try lock.withLockUnchecked { state in
      state.nextGeneration &+= 1
      let reservation = RewindVideoChunkReservation(
        generation: state.nextGeneration,
        relativePath: relativePath
      )
      state.activeReservation = reservation
      do {
        try startup()
        return reservation
      } catch {
        if state.activeReservation == reservation {
          state.activeReservation = nil
        }
        throw error
      }
    }
  }

  /// Reads the active reservation while holding the same lock that protects
  /// writer startup, so cleanup cannot observe a stale nil before a new day
  /// directory is created.
  static func withActiveChunk<T>(_ body: (RewindVideoChunkReservation?) throws -> T) rethrows -> T {
    try lock.withLockUnchecked { state in
      try body(state.activeReservation)
    }
  }

  static func finishActiveChunk(_ reservation: RewindVideoChunkReservation?) {
    guard let reservation else { return }
    lock.withLockUnchecked { state in
      guard state.activeReservation == reservation else { return }
      state.activeReservation = nil
    }
  }
}
