@preconcurrency import AVFoundation
import CoreGraphics
import CoreImage
import Foundation

/// One decoded video frame, in the only form that may cross an actor boundary.
///
/// `RewindStorage` decodes on its own actor but the timeline draws on the main one, and `NSImage`
/// is not `Sendable`. The pre-existing way across was to re-encode the decoded frame to JPEG at
/// quality 1.0 and hand over `Data` — which cost a measured 14.4 ms on *every* load, cache hits
/// included, to reconstruct pixels the decoder had already produced.
///
/// `CGImage` is immutable once created and Core Graphics documents it as such, so the box below is
/// a genuine `@unchecked Sendable` rather than a silenced warning: there is no mutating API to race
/// on. The main actor wraps it in an `NSImage` at the point of use.
struct RewindDecodedFrame: @unchecked Sendable {
  let cgImage: CGImage

  var pixelSize: CGSize { CGSize(width: cgImage.width, height: cgImage.height) }
}

/// A reference box so decoded frames can live in `NSCache`, which only holds objects.
final class RewindDecodedFrameBox {
  let frame: RewindDecodedFrame

  init(_ frame: RewindDecodedFrame) { self.frame = frame }
}

/// A sequential decode cursor over one video chunk.
///
/// **Why this exists.** A Rewind chunk is inter-frame compressed, so there is no random access to
/// frame *n*: reaching it means decoding everything before it. The shipped reader opened a fresh
/// `AVAssetReader` per request and walked from frame 0 every time, which makes a scrub through a
/// chunk quadratic in its length — the user pays for frame 0 again on every step. Measured on a
/// real 18-frame 1512×948 chunk, scrubbing the whole thing cost **728 ms (40.5 ms/frame)**.
///
/// Keeping the reader alive between requests makes a forward step cost exactly one
/// `copyNextSampleBuffer()`. The same scrub measured **59 ms (3.3 ms/frame)**, 12.3× faster, and
/// pixel-identical at every offset. Longer chunks separate the two further, because the cost the
/// cursor removes is the one that grows.
///
/// A backward step, or a step into a different chunk, reopens — there is nothing cheaper available
/// for either, and reopening is exactly what happens today.
///
/// `@unchecked Sendable` because every stored property is touched only from `RewindStorage`'s actor
/// isolation, which the compiler cannot see. An earlier comment here claimed the type "never crosses
/// a boundary" — that was wrong, and Xcode 16.4 said so: `open` is a nonisolated `async` factory, so
/// returning the cursor into the actor *is* a crossing. It is a safe one, because the only reference
/// at that instant is the one being returned, and from then on the cursor lives as actor state.
final class RewindVideoFrameCursor: @unchecked Sendable {
  /// The chunk-relative path this cursor decodes, used to decide whether it can serve a request.
  let videoPath: String

  private let reader: AVAssetReader
  private let output: AVAssetReaderTrackOutput
  /// One context per cursor rather than per frame. Measured as *neutral* (22.8 ms vs 23.0 ms for a
  /// single decode either way), so this is about the object having an obvious lifetime, not speed.
  private let renderContext: CIContext
  /// The offset the next `copyNextSampleBuffer()` will return. A cursor can only move forward.
  private var nextOffset = 0
  private var isFinished = false

  private init(videoPath: String, reader: AVAssetReader, output: AVAssetReaderTrackOutput) {
    self.videoPath = videoPath
    self.reader = reader
    self.output = output
    self.renderContext = CIContext(options: [.useSoftwareRenderer: false])
  }

  /// Open a reader positioned at the start of `fileURL`.
  static func open(videoPath: String, fileURL: URL) async throws -> RewindVideoFrameCursor {
    let asset = AVURLAsset(url: fileURL)
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

    return RewindVideoFrameCursor(videoPath: videoPath, reader: reader, output: output)
  }

  /// Whether this cursor can reach `frameOffset` without reopening.
  ///
  /// A cursor is a one-way tape: it can serve any offset at or after the one it is parked on.
  func canServe(videoPath: String, frameOffset: Int) -> Bool {
    !isFinished && self.videoPath == videoPath && frameOffset >= nextOffset
  }

  /// Decode `frameOffset`, advancing the tape to it.
  ///
  /// Returns `nil` when the chunk ends before that offset — which is a real outcome for the chunk
  /// still being written, not an error. The caller retires the cursor and decides whether to reopen.
  /// Synchronous by design: it must not suspend, so a reentrant call on the owning actor cannot
  /// interleave with a half-advanced tape.
  func frame(at frameOffset: Int) throws -> CGImage? {
    guard frameOffset >= nextOffset else { return nil }

    while let sampleBuffer = output.copyNextSampleBuffer() {
      defer { CMSampleBufferInvalidate(sampleBuffer) }
      let current = nextOffset
      nextOffset += 1
      guard current == frameOffset else { continue }

      guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
        throw RewindError.storageError("AVFoundation sample had no image buffer")
      }
      let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
      let rect = CGRect(
        x: 0,
        y: 0,
        width: CVPixelBufferGetWidth(pixelBuffer),
        height: CVPixelBufferGetHeight(pixelBuffer)
      )
      guard let cgImage = renderContext.createCGImage(ciImage, from: rect) else {
        throw RewindError.storageError("AVFoundation failed to render decoded frame")
      }
      return cgImage
    }

    isFinished = true
    if reader.status == .failed {
      let message = reader.error?.localizedDescription ?? "unknown error"
      throw RewindError.storageError("AVFoundation reader failed: \(message)")
    }
    return nil
  }

  func cancel() {
    isFinished = true
    reader.cancelReading()
  }
}
