import AVFoundation
import Flutter
import UIKit

/// `com.omi/chat_video` — reduce a picked clip to what chat reads: stills and the audio track.
///
/// Mirrors the desktop sampler (desktop/macos/.../ChatVideoSampler.swift) and the backend's
/// candidate set (backend/utils/media/video_frames.py): at most 48 frames, at most 4 per
/// second, longest edge 384 px, plus AAC audio, written to temp files for
/// `POST /v2/files/video`. The caller deletes the files after upload.
final class ChatVideoSampler {
  static let maxFrames = 48
  static let maxFramesPerSecond = 4.0
  static let frameEdge: CGFloat = 384
  static let maxAudioSeconds = 600.0

  private let channel: FlutterMethodChannel
  private let queue = DispatchQueue(label: "com.omi.chat-video", qos: .userInitiated)

  init(messenger: FlutterBinaryMessenger) {
    channel = FlutterMethodChannel(name: "com.omi/chat_video", binaryMessenger: messenger)
    channel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "sample",
        let args = call.arguments as? [String: Any],
        let path = args["path"] as? String
      else {
        result(FlutterMethodNotImplemented)
        return
      }
      self?.sample(path: path, result: result)
    }
  }

  static func sampleTimes(duration: Double) -> [Double] {
    guard duration.isFinite, duration > 0 else { return [0] }
    // As many frames as fit at most 4 per second from 0 to just before the end, spread to the end.
    let reach = max(0, duration - 0.05)
    let count = min(maxFrames, Int(reach * maxFramesPerSecond) + 1)
    guard count > 1 else { return [0] }
    let step = reach / Double(count - 1)
    return (0..<count).map { (Double($0) * step * 100).rounded() / 100 }
  }

  private func sample(path: String, result: @escaping FlutterResult) {
    let asset = AVURLAsset(url: URL(fileURLWithPath: path))
    guard !asset.tracks(withMediaType: .video).isEmpty else {
      result(FlutterError(code: "no_picture", message: "That file has no video to read.", details: nil))
      return
    }
    let duration = asset.duration.seconds
    let times = Self.sampleTimes(duration: duration)
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-chat-video-\(UUID().uuidString)", isDirectory: true)
    do {
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    } catch {
      result(FlutterError(code: "io", message: error.localizedDescription, details: nil))
      return
    }

    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(width: Self.frameEdge, height: Self.frameEdge)
    let tolerance = CMTime(seconds: 0.1, preferredTimescale: 600)
    generator.requestedTimeToleranceBefore = tolerance
    generator.requestedTimeToleranceAfter = tolerance

    var frames: [(time: Double, path: String)] = []
    var remaining = times.count
    let lock = NSLock()
    let requested = times.map { NSValue(time: CMTime(seconds: $0, preferredTimescale: 600)) }
    generator.generateCGImagesAsynchronously(forTimes: requested) { [queue] requestedTime, image, actualTime, status, _ in
      lock.lock()
      if status == .succeeded, let image,
        let jpeg = UIImage(cgImage: image).jpegData(compressionQuality: 0.75)
      {
        let file = directory.appendingPathComponent("frame-\(frames.count).jpg")
        if (try? jpeg.write(to: file)) != nil {
          // The decoded frame's own time (within the tolerance), not the requested one.
          frames.append((actualTime.isValid ? actualTime.seconds : requestedTime.seconds, file.path))
        }
      }
      remaining -= 1
      let done = remaining == 0
      lock.unlock()
      guard done else { return }
      queue.async {
        let ordered = frames.sorted { $0.time < $1.time }
        guard !ordered.isEmpty else {
          try? FileManager.default.removeItem(at: directory)
          DispatchQueue.main.async {
            result(FlutterError(code: "no_frames", message: "Couldn't read frames from that video.", details: nil))
          }
          return
        }
        Self.exportAudio(asset: asset, duration: duration, directory: directory) { audioPath in
          if audioPath == nil && !asset.tracks(withMediaType: .audio).isEmpty {
            // Sound we couldn't export: Dart uploads the clip whole and the server transcribes it.
            try? FileManager.default.removeItem(at: directory)
            DispatchQueue.main.async { result(["audio_unsupported": true]) }
            return
          }
          var payload: [String: Any] = [
            "frames": ordered.map { $0.path },
            "times": ordered.map { ($0.time * 100).rounded() / 100 },
            "duration": duration.isFinite ? duration : (ordered.last?.time ?? 0),
            "directory": directory.path,
          ]
          if let audioPath { payload["audio"] = audioPath }
          DispatchQueue.main.async { result(payload) }
        }
      }
    }
  }

  private static func exportAudio(
    asset: AVURLAsset, duration: Double, directory: URL, completion: @escaping (String?) -> Void
  ) {
    guard !asset.tracks(withMediaType: .audio).isEmpty,
      let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A)
    else {
      completion(nil)
      return
    }
    let output = directory.appendingPathComponent("audio.m4a")
    session.outputURL = output
    session.outputFileType = .m4a
    session.timeRange = CMTimeRange(
      start: .zero, duration: CMTime(seconds: min(duration, maxAudioSeconds), preferredTimescale: 600))
    session.exportAsynchronously {
      completion(session.status == .completed ? output.path : nil)
    }
  }
}
