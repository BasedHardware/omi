import AVFoundation
import AppKit
import Foundation

/// A chat video reduced on device to what the backend reads: still frames and the audio track.
///
/// Uploading a whole clip costs the user bandwidth and the backend a decode; the chat model only
/// ever sees stills (`backend/utils/media/video_frames.py`). This samples the same candidate set
/// the server would (at most 48 frames, at most 4 per second, longest edge 384 px) and exports
/// the audio (AAC on macOS 15+, 16 kHz mono WAV on macOS 14), for `POST /v2/files/video`.
struct SampledChatVideo {
  let frames: [Data]
  let times: [Double]
  let duration: Double
  /// The audio track, or nil when the clip is silent.
  let audio: SampledChatAudio?
}

struct SampledChatAudio {
  let data: Data
  let fileName: String
  let mimeType: String
}

enum ChatVideoSamplerError: Error, LocalizedError {
  case noPicture
  case noFrames
  case audioUnreadable

  var errorDescription: String? {
    switch self {
    case .noPicture: return "That file has no video to read."
    case .noFrames: return "Couldn't read frames from that video."
    case .audioUnreadable: return "Couldn't read that video's sound. Try exporting it again."
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
    // A clip with a sound track whose audio can't be read fails visibly rather than
    // uploading as if it were silent.
    let audio = try await exportAudio(asset: asset, duration: duration)
    return SampledChatVideo(
      frames: order.map { frames[$0] },
      times: order.map { (kept[$0] * 100).rounded() / 100 },
      duration: duration.isFinite ? duration : (kept.max() ?? 0),
      audio: audio
    )
  }

  private static func jpegData(_ image: CGImage) -> Data? {
    NSBitmapImageRep(cgImage: image).representation(
      using: .jpeg, properties: [.compressionFactor: 0.75])
  }

  /// AAC through the macOS 15 async export API; macOS 14 reads 16 kHz mono PCM into a WAV.
  private static func exportAudio(asset: AVURLAsset, duration: Double) async throws -> SampledChatAudio? {
    let tracks = try await asset.loadTracks(withMediaType: .audio)
    guard let track = tracks.first else { return nil }
    guard #available(macOS 15, *) else {
      guard let wav = try? wavAudio(asset: asset, track: track, duration: duration) else {
        throw ChatVideoSamplerError.audioUnreadable
      }
      return SampledChatAudio(data: wav, fileName: "audio.wav", mimeType: "audio/wav")
    }
    guard let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A)
    else { throw ChatVideoSamplerError.audioUnreadable }
    let output = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-chat-video-\(UUID().uuidString).m4a")
    defer { try? FileManager.default.removeItem(at: output) }
    session.timeRange = CMTimeRange(
      start: .zero,
      duration: CMTime(seconds: min(duration, maxAudioSeconds), preferredTimescale: 600))
    do {
      try await session.export(to: output, as: .m4a)
    } catch {
      throw ChatVideoSamplerError.audioUnreadable
    }
    return SampledChatAudio(data: try Data(contentsOf: output), fileName: "audio.m4a", mimeType: "audio/mp4")
  }

  /// 16 kHz mono 16-bit PCM in a WAV container (about 19 MB for the 10-minute cap).
  static func wavAudio(asset: AVURLAsset, track: AVAssetTrack, duration: Double) throws -> Data? {
    let reader = try AVAssetReader(asset: asset)
    reader.timeRange = CMTimeRange(
      start: .zero, duration: CMTime(seconds: min(duration, maxAudioSeconds), preferredTimescale: 600))
    let output = AVAssetReaderTrackOutput(
      track: track,
      outputSettings: [
        AVFormatIDKey: kAudioFormatLinearPCM,
        AVSampleRateKey: 16_000,
        AVNumberOfChannelsKey: 1,
        AVLinearPCMBitDepthKey: 16,
        AVLinearPCMIsFloatKey: false,
        AVLinearPCMIsBigEndianKey: false,
        AVLinearPCMIsNonInterleaved: false,
      ])
    guard reader.canAdd(output) else { return nil }
    reader.add(output)
    guard reader.startReading() else { return nil }
    var pcm = Data()
    while let buffer = output.copyNextSampleBuffer() {
      if let block = CMSampleBufferGetDataBuffer(buffer) {
        let length = CMBlockBufferGetDataLength(block)
        var chunk = Data(count: length)
        _ = chunk.withUnsafeMutableBytes { bytes in
          bytes.baseAddress.map { CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: length, destination: $0) }
        }
        pcm.append(chunk)
      }
    }
    guard reader.status == .completed, !pcm.isEmpty else { return nil }
    return wavHeader(pcmBytes: pcm.count) + pcm
  }

  static func wavHeader(pcmBytes: Int, sampleRate: UInt32 = 16_000) -> Data {
    var header = Data()
    func append<T: FixedWidthInteger>(_ value: T) {
      withUnsafeBytes(of: value.littleEndian) { header.append(contentsOf: $0) }
    }
    header.append(contentsOf: Array("RIFF".utf8))
    append(UInt32(36 + pcmBytes))
    header.append(contentsOf: Array("WAVEfmt ".utf8))
    append(UInt32(16))
    append(UInt16(1))  // PCM
    append(UInt16(1))  // mono
    append(sampleRate)
    append(sampleRate * 2)  // byte rate
    append(UInt16(2))  // block align
    append(UInt16(16))  // bits per sample
    header.append(contentsOf: Array("data".utf8))
    append(UInt32(pcmBytes))
    return header
  }
}
