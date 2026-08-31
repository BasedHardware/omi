import AVFoundation
import Combine
import Foundation

/// Narrow playback boundary owned by the canonical conversation detail. A ready
/// aggregate artifact is the only state that promises exact moment seeking.
protocol CapturePlaybackProviding: Sendable {
  func resolvePlayback(for capture: ServerConversation) async -> CapturePlaybackResolution
}

enum CapturePlaybackResolution: Equatable, Sendable {
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

struct CapturePlaybackFile: Equatable, Sendable {
  let id: String
  let signedURL: URL
  let duration: TimeInterval
}

struct CapturePlaybackArtifact: Equatable, Sendable {
  let signedURL: URL
  let duration: TimeInterval
  let spans: [CaptureAudioURLSpan]

  /// Converts the source capture's wall-clock offset into the aggregate
  /// artifact's media offset. It returns nil across a gap or missing span;
  /// callers must not seek a per-file fallback and claim accuracy.
  func artifactOffset(forWallOffset wallOffset: TimeInterval) -> TimeInterval? {
    guard
      let span = spans.first(where: {
        let end = $0.wallOffset + $0.length
        return wallOffset >= $0.wallOffset && wallOffset < end
      })
    else {
      return nil
    }
    return span.artifactOffset + (wallOffset - span.wallOffset)
  }

  /// Converts the aggregate player's media time back to the source capture's
  /// wall-clock time so the transcript can follow playback without drifting
  /// across gaps between captured audio spans.
  func wallOffset(forArtifactOffset artifactOffset: TimeInterval) -> TimeInterval? {
    guard
      let span = spans.first(where: {
        let end = $0.artifactOffset + $0.length
        return artifactOffset >= $0.artifactOffset && artifactOffset < end
      })
    else {
      return nil
    }
    return span.wallOffset + (artifactOffset - span.artifactOffset)
  }
}

enum CaptureTranscriptFollowPolicy {
  static func wallOffset(
    forPlaybackOffset playbackOffset: TimeInterval,
    resolution: CapturePlaybackResolution
  ) -> TimeInterval? {
    switch resolution {
    case .readyAggregate(let artifact):
      return artifact.wallOffset(forArtifactOffset: playbackOffset)
    case .fileFallback:
      // The fallback is exposed only as a single capture part, whose media
      // timeline begins at the capture's first transcript timestamp.
      return max(0, playbackOffset)
    case .pending, .locked, .unavailable, .noAudio:
      return nil
    }
  }

  static func activeSegmentID(
    atPlaybackOffset playbackOffset: TimeInterval,
    resolution: CapturePlaybackResolution,
    segments: [TranscriptSegment]
  ) -> String? {
    guard let wallOffset = wallOffset(forPlaybackOffset: playbackOffset, resolution: resolution)
    else { return nil }
    return segments.last(where: { $0.start <= wallOffset }).map { $0.backendId ?? $0.id }
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

/// `AVPlayer` lifecycle stays inside the visible canonical detail. Signed URLs
/// are held only in the player item and are never persisted or logged.
@MainActor
final class CapturePlaybackController: ObservableObject {
  @Published private(set) var resolution: CapturePlaybackResolution?
  @Published private(set) var isResolving = false
  @Published private(set) var isPlaybackRequested = false
  @Published private(set) var isPlaying = false
  @Published private(set) var isBuffering = false
  @Published private(set) var currentTime: TimeInterval = 0
  @Published private(set) var duration: TimeInterval = 0
  @Published private(set) var playbackError: String?

  private let provider: any CapturePlaybackProviding
  private var player: AVPlayer?
  private var timeObserver: Any?
  private var playerCancellables: Set<AnyCancellable> = []
  private var activeCaptureID: String?
  private var activeResolutionToken: UUID?

  init(provider: any CapturePlaybackProviding = LiveCapturePlaybackProvider()) {
    self.provider = provider
  }

  func prepare(
    for capture: ServerConversation,
    forceRefresh: Bool = false
  ) async -> CapturePlaybackResolution? {
    if !forceRefresh, activeCaptureID == capture.id, let resolution { return resolution }
    let token = UUID()
    activeResolutionToken = token
    activeCaptureID = capture.id
    isResolving = true
    defer {
      if activeResolutionToken == token {
        isResolving = false
      }
    }

    let next = await provider.resolvePlayback(for: capture)
    guard activeResolutionToken == token, activeCaptureID == capture.id, !Task.isCancelled else { return nil }
    resolution = next
    resetPlaybackStatus()
    switch next {
    case .readyAggregate(let artifact):
      installPlayer(url: artifact.signedURL, expectedDuration: artifact.duration)
    case .fileFallback(let file):
      installPlayer(url: file.signedURL, expectedDuration: file.duration)
    case .pending, .locked, .unavailable, .noAudio:
      removePlayer()
    }
    return next
  }

  /// Selection owns playback identity. Clearing pauses the old capture before
  /// the new detail request begins and invalidates every outstanding resolver.
  func clear() {
    activeResolutionToken = nil
    activeCaptureID = nil
    resolution = nil
    isResolving = false
    resetPlaybackStatus()
    removePlayer()
  }

  /// Returns false only when no playable item exists. Once accepted, the
  /// user's request becomes visible immediately while AVFoundation buffers;
  /// the old control changed nothing on screen and made a waiting or failed
  /// player indistinguishable from a missed click.
  @discardableResult
  func playOrPause() -> Bool {
    guard let player else {
      playbackError = "Audio is not ready. Check audio and try again."
      return false
    }

    if isPlaybackRequested {
      isPlaybackRequested = false
      isBuffering = false
      isPlaying = false
      player.pause()
      return true
    }

    playbackError = nil
    if duration > 0, currentTime >= duration - 0.1 {
      player.seek(to: .zero)
      currentTime = 0
    }
    player.isMuted = false
    player.volume = 1
    isPlaybackRequested = true
    isBuffering = true
    player.playImmediately(atRate: 1)
    return true
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

  private func installPlayer(url: URL, expectedDuration: TimeInterval) {
    removePlayer()

    let item = AVPlayerItem(url: url)
    let player = AVPlayer(playerItem: item)
    player.automaticallyWaitsToMinimizeStalling = true
    self.player = player
    duration = max(0, expectedDuration)

    player.publisher(for: \.timeControlStatus)
      .receive(on: DispatchQueue.main)
      .sink { [weak self] status in
        guard let self else { return }
        switch status {
        case .playing:
          isPlaying = true
          isBuffering = false
        case .waitingToPlayAtSpecifiedRate:
          isPlaying = false
          isBuffering = isPlaybackRequested
        case .paused:
          isPlaying = false
          isBuffering = false
        @unknown default:
          isPlaying = false
          isBuffering = false
        }
      }
      .store(in: &playerCancellables)

    item.publisher(for: \.status)
      .receive(on: DispatchQueue.main)
      .sink { [weak self, weak item] status in
        guard let self else { return }
        switch status {
        case .readyToPlay:
          if let seconds = item?.duration.seconds, seconds.isFinite, seconds > 0 {
            duration = seconds
          }
        case .failed:
          isPlaybackRequested = false
          isPlaying = false
          isBuffering = false
          playbackError = "Audio could not be played. Check audio to refresh the link."
        case .unknown:
          break
        @unknown default:
          break
        }
      }
      .store(in: &playerCancellables)

    NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime, object: item)
      .receive(on: DispatchQueue.main)
      .sink { [weak self] _ in
        guard let self else { return }
        isPlaybackRequested = false
        isPlaying = false
        isBuffering = false
        currentTime = duration
      }
      .store(in: &playerCancellables)

    NotificationCenter.default.publisher(for: .AVPlayerItemFailedToPlayToEndTime, object: item)
      .receive(on: DispatchQueue.main)
      .sink { [weak self] _ in
        guard let self else { return }
        isPlaybackRequested = false
        isPlaying = false
        isBuffering = false
        playbackError = "Audio stopped unexpectedly. Check audio to try again."
      }
      .store(in: &playerCancellables)

    timeObserver = player.addPeriodicTimeObserver(
      forInterval: CMTime(seconds: 0.25, preferredTimescale: 600),
      queue: .main
    ) { [weak self] time in
      Task { @MainActor [weak self] in
        guard let self else { return }
        let seconds = time.seconds
        if seconds.isFinite {
          self.currentTime = max(0, seconds)
        }
      }
    }
  }

  private func removePlayer() {
    if let timeObserver, let player {
      player.removeTimeObserver(timeObserver)
    }
    timeObserver = nil
    playerCancellables.removeAll()
    player?.pause()
    player = nil
  }

  private func resetPlaybackStatus() {
    isPlaybackRequested = false
    isPlaying = false
    isBuffering = false
    currentTime = 0
    duration = 0
    playbackError = nil
  }
}
