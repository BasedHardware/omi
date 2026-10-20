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
    let step = max(duration / Double(maxFrames), 1 / maxFramesPerSecond)
    var times: [Double] = []
    var t = 0.0
    while t < duration, times.count < maxFrames {
      times.append((t * 100).rounded() / 100)
      t += step
    }
    return times.isEmpty ? [0] : times
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
    generator.generateCGImagesAsynchronously(forTimes: requested) { [queue] requestedTime, image, _, status, _ in
      lock.lock()
      if status == .succeeded, let image,
        let jpeg = UIImage(cgImage: image).jpegData(compressionQuality: 0.75)
      {
        let file = directory.appendingPathComponent("frame-\(frames.count).jpg")
        if (try? jpeg.write(to: file)) != nil {
          frames.append((requestedTime.seconds, file.path))
        }
      }
      remaining -= 1
      let done = remaining == 0
      lock.unlock()
      guard done else { return }
      queue.async {
        let ordered = frames.sorted { $0.time < $1.time }
        guard !ordered.isEmpty else {
          DispatchQueue.main.async {
            result(FlutterError(code: "no_frames", message: "Couldn't read frames from that video.", details: nil))
          }
          return
        }
        Self.exportAudio(asset: asset, duration: duration, directory: directory) { audioPath in
          let payload: [String: Any] = [
            "frames": ordered.map { $0.path },
            "times": ordered.map { ($0.time * 100).rounded() / 100 },
            "duration": duration.isFinite ? duration : (ordered.last?.time ?? 0),
            "audio": audioPath as Any,
            "directory": directory.path,
          ]
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
