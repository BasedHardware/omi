import AVFoundation
import Combine
import Foundation

/// Narrow, page-owned playback boundary for the capture archive. A ready
/// aggregate artifact is the only state that promises exact moment seeking.
protocol CapturePlaybackProviding {
  func resolvePlayback(for capture: ServerConversation) async -> CapturePlaybackResolution
}

enum CapturePlaybackResolution: Equatable {
  case readyAggregate(CapturePlaybackArtifact)
  case fileFallback(CapturePlaybackFile)
  case pending(pollAfterMs: Int?)
  case locked
  case unavailable
  case noAudio

  var userFacingMessage: String {
    switch self {
    case .readyAggregate: return "Playback ready"
    case .fileFallback: return "A single audio part is ready. Timestamped seeking is preparing."
    case .pending: return "Audio is preparing. Try again shortly."
    case .locked: return "Audio is locked for this capture."
    case .unavailable: return "Audio is unavailable for this capture."
    case .noAudio: return "No audio is available for this capture."
    }
  }
}

struct CapturePlaybackFile: Equatable {
  let id: String
  let signedURL: URL
  let duration: TimeInterval
}

struct CapturePlaybackArtifact: Equatable {
  let signedURL: URL
  let duration: TimeInterval
  let spans: [CaptureAudioURLSpan]

  /// Converts the source capture's wall-clock offset into the aggregate
  /// artifact's media offset. It returns nil across a gap or missing span;
  /// callers must not seek a per-file fallback and claim accuracy.
  func artifactOffset(forWallOffset wallOffset: TimeInterval) -> TimeInterval? {
    guard let span = spans.first(where: {
      let end = $0.wallOffset + $0.length
      return wallOffset >= $0.wallOffset && wallOffset < end
    }) else {
      return nil
    }
    return span.artifactOffset + (wallOffset - span.wallOffset)
  }
}

enum CaptureFocusAcknowledgementPolicy {
  /// A capture with no moment is visible as soon as its detail is selected. A
  /// moment deep link is acknowledged only after the aggregate seek callback
  /// succeeds; pending/fallback/unavailable playback deliberately stays pending.
  static func canAcknowledge(
    requestedMoment: TimeInterval?,
    resolution: CapturePlaybackResolution,
    didCompleteSeek: Bool = false
  ) -> Bool {
    guard requestedMoment != nil else { return true }
    guard case .readyAggregate = resolution else { return false }
    return didCompleteSeek
  }
}

struct LiveCapturePlaybackProvider: CapturePlaybackProviding {
  func resolvePlayback(for capture: ServerConversation) async -> CapturePlaybackResolution {
    guard !capture.isLocked else { return .locked }
    guard !capture.audioFiles.isEmpty || capture.conversationAudio != nil else { return .noAudio }

    do {
      let precache = try await APIClient.shared.precacheCaptureAudio(conversationID: capture.id)
      if precache.status == "no_audio" { return .noAudio }
      let response = try await APIClient.shared.captureAudioURLs(conversationID: capture.id)
      return Self.resolution(from: response)
    } catch let APIError.httpError(statusCode, _) where statusCode == 402 {
      return .locked
    } catch {
      // URL endpoints do not distinguish a transient error from an absent
      // capture in their stable contract. Never expose an invented URL or
      // treat a generic file as exact timestamp playback.
      return .unavailable
    }
  }

  static func resolution(from response: CaptureAudioURLsResponse) -> CapturePlaybackResolution {
    if let artifact = response.conversationAudio {
      switch artifact.status {
      case "cached":
        if let signedURL = artifact.signedURL {
          return .readyAggregate(
            CapturePlaybackArtifact(
              signedURL: signedURL,
              duration: artifact.duration ?? artifact.capturedDuration ?? 0,
              spans: artifact.spans
            )
          )
        }
        return .unavailable
      case "pending":
        return .pending(pollAfterMs: response.pollAfterMs)
      case "unavailable":
        return .unavailable
      default:
        return .unavailable
      }
    }

    if let file = response.audioFiles.first(where: { $0.status == "cached" && $0.signedURL != nil }),
      let signedURL = file.signedURL
    {
      return .fileFallback(CapturePlaybackFile(id: file.id, signedURL: signedURL, duration: file.duration))
    }

    if response.audioFiles.contains(where: { $0.status == "pending" }) {
      return .pending(pollAfterMs: response.pollAfterMs)
    }
    if response.audioFiles.isEmpty { return .noAudio }
    return .unavailable
  }
}

/// `AVPlayer` lifecycle stays inside the archive. Signed URLs are held only in
/// the player item for the active page and are never persisted or logged.
@MainActor
final class CapturePlaybackController: ObservableObject {
  @Published private(set) var resolution: CapturePlaybackResolution?
  @Published private(set) var isResolving = false

  private let provider: any CapturePlaybackProviding
  private var player: AVPlayer?
  private var activeCaptureID: String?

  init(provider: any CapturePlaybackProviding = LiveCapturePlaybackProvider()) {
    self.provider = provider
  }

  func prepare(
    for capture: ServerConversation,
    forceRefresh: Bool = false
  ) async -> CapturePlaybackResolution {
    if !forceRefresh, activeCaptureID == capture.id, let resolution { return resolution }
    isResolving = true
    defer { isResolving = false }

    let next = await provider.resolvePlayback(for: capture)
    activeCaptureID = capture.id
    resolution = next
    switch next {
    case .readyAggregate(let artifact):
      player = AVPlayer(url: artifact.signedURL)
    case .fileFallback(let file):
      player = AVPlayer(url: file.signedURL)
    case .pending, .locked, .unavailable, .noAudio:
      player = nil
    }
    return next
  }

  func playOrPause() {
    guard let player else { return }
    if player.timeControlStatus == .playing {
      player.pause()
    } else {
      player.play()
    }
  }

  /// Returns true only when an aggregate artifact translated the requested
  /// wall offset and AVFoundation confirmed the exact seek completed.
  func seekToMoment(wallOffset: TimeInterval) async -> Bool {
    guard case .readyAggregate(let artifact) = resolution,
      let target = artifact.artifactOffset(forWallOffset: wallOffset),
      let player
    else { return false }

    let time = CMTime(seconds: target, preferredTimescale: 600)
    return await withCheckedContinuation { continuation in
      player.seek(to: time, toleranceBefore: .zero, toleranceAfter: .zero) { finished in
        continuation.resume(returning: finished)
      }
    }
  }
}
