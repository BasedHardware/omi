import AVFoundation
import AppKit
import Foundation

/// A chat video reduced on device to what the backend reads: still frames and the audio track.
///
/// Uploading a whole clip costs the user bandwidth and the backend a decode; the chat model only
/// ever sees stills (`backend/utils/media/video_frames.py`). This samples the same candidate set
/// the server would (at most 48 frames, at most 4 per second, longest edge 384 px) and exports
/// the audio as AAC, for `POST /v2/files/video`.
struct SampledChatVideo {
  let frames: [Data]
  let times: [Double]
  let duration: Double
  /// AAC (.m4a) audio track, or nil when the clip is silent.
  let audio: Data?
  /// The clip has speech this Mac can't export (macOS 14): upload the clip whole instead,
  /// so the server transcribes it.
  var audioNeedsServer = false
}

enum ChatVideoSamplerError: Error, LocalizedError {
  case noPicture
  case noFrames

  var errorDescription: String? {
    switch self {
    case .noPicture: return "That file has no video to read."
    case .noFrames: return "Couldn't read frames from that video."
    }
  }
}

enum ChatVideoSampler {
  static let maxFrames = 48
  static let maxFramesPerSecond = 4.0
  static let frameEdge: CGFloat = 384
  /// Matches the backend's transcription cap (MAX_MEDIA_SECONDS).
  static let maxAudioSeconds = 600.0

  /// Evenly spaced sample times from 0 to the end: at most `maxFramesPerSecond`, at most `maxFrames`.
  static func sampleTimes(duration: Double) -> [Double] {
    guard duration.isFinite, duration > 0 else { return [0] }
    // As many frames as fit at most 4 per second from 0 to just before the end, spread to the end.
    let reach = max(0, duration - 0.05)
    let count = min(maxFrames, Int(reach * maxFramesPerSecond) + 1)
    guard count > 1 else { return [0] }
    let step = reach / Double(count - 1)
    return (0..<count).map { (Double($0) * step * 100).rounded() / 100 }
  }

  static func sample(url: URL) async throws -> SampledChatVideo {
    let asset = AVURLAsset(url: url)
    guard try await !asset.loadTracks(withMediaType: .video).isEmpty else {
      throw ChatVideoSamplerError.noPicture
    }
    let duration = try await asset.load(.duration).seconds
    let times = sampleTimes(duration: duration)

    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(width: frameEdge, height: frameEdge)
    // Nearby keyframes are fine: frames are already a quarter second or more apart.
    let tolerance = CMTime(seconds: 0.1, preferredTimescale: 600)
    generator.requestedTimeToleranceBefore = tolerance
    generator.requestedTimeToleranceAfter = tolerance

    var frames: [Data] = []
    var kept: [Double] = []
    let requested = times.map { CMTime(seconds: $0, preferredTimescale: 600) }
    for await result in generator.images(for: requested) {
      guard let image = try? result.image, let jpeg = jpegData(image) else { continue }
      frames.append(jpeg)
      // The decoded frame's own time (within the tolerance), not the requested one.
      kept.append((try? result.actualTime.seconds) ?? result.requestedTime.seconds)
    }
    guard !frames.isEmpty else { throw ChatVideoSamplerError.noFrames }
    // The async sequence answers in request order; keep times ascending regardless.
    let order = kept.indices.sorted { kept[$0] < kept[$1] }
    let audio = try? await exportAudio(asset: asset, duration: duration)
    let hasAudio = (try? await !asset.loadTracks(withMediaType: .audio).isEmpty) ?? false
    var sampled = SampledChatVideo(
      frames: order.map { frames[$0] },
      times: order.map { (kept[$0] * 100).rounded() / 100 },
      duration: duration.isFinite ? duration : (kept.max() ?? 0),
      audio: audio
    )
    sampled.audioNeedsServer = hasAudio && audio == nil
    return sampled
  }

  private static func jpegData(_ image: CGImage) -> Data? {
    NSBitmapImageRep(cgImage: image).representation(
      using: .jpeg, properties: [.compressionFactor: 0.75])
  }

  /// AAC export uses the macOS 15 async API; on macOS 14 a clip with audio uploads whole.
  private static func exportAudio(asset: AVURLAsset, duration: Double) async throws -> Data? {
    guard #available(macOS 15, *) else { return nil }
    guard try await !asset.loadTracks(withMediaType: .audio).isEmpty,
      let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A)
    else { return nil }
    let output = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-chat-video-\(UUID().uuidString).m4a")
    defer { try? FileManager.default.removeItem(at: output) }
    session.timeRange = CMTimeRange(
      start: .zero,
      duration: CMTime(seconds: min(duration, maxAudioSeconds), preferredTimescale: 600))
    try await session.export(to: output, as: .m4a)
    return try Data(contentsOf: output)
  }
}
