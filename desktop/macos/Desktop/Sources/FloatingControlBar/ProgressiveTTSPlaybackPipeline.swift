import Foundation

@MainActor
protocol ProgressiveAudioPlaying: AnyObject {
  var onStarted: (() -> Void)? { get set }
  var onDrained: ((TimeInterval) -> Void)? { get set }

  func append(_ data: Data) throws
  func finish()
  func stop()
}

enum ProgressiveTTSPlaybackError: LocalizedError, Equatable {
  case stalled
  case noPlayableAudio

  var errorDescription: String? {
    switch self {
    case .stalled:
      return "The TTS audio stream stopped delivering bytes"
    case .noPlayableAudio:
      return "The TTS audio stream contained no playable audio"
    }
  }
}

/// Converts played media time into a conservative system-voice suffix after a
/// truncated cloud stream. Five words per media second intentionally skips the
/// word that may have been in flight at the cut: avoiding repeated speech is
/// more important than replaying an uncertain boundary word.
enum ProgressiveSpeechRemainder {
  static func untouchedSuffix(text: String, playedMediaDuration: TimeInterval) -> String {
    let words = text.split(whereSeparator: \Character.isWhitespace).map(String.init)
    guard !words.isEmpty else { return "" }
    guard playedMediaDuration > 0 else { return text }
    let wordsToSkip = Int(ceil(playedMediaDuration * 5)) + 1
    guard wordsToSkip < words.count else { return "" }
    return words.dropFirst(wordsToSkip).joined(separator: " ")
  }
}

/// Owns progressive request/playback ordering for the selected desktop voice.
/// Only the head chunk gets a physical player. Later requests may finish while
/// it is speaking, but their compressed bytes stay inert until every earlier
/// chunk (including any system-voice fallback) has drained.
@MainActor
final class ProgressiveTTSPlaybackPipeline {
  typealias StreamFactory = @Sendable (String) async throws -> AsyncThrowingStream<Data, Error>
  typealias PlayerFactory = () throws -> any ProgressiveAudioPlaying
  typealias StallWaiter = @Sendable () async throws -> Void

  var onPlaybackStarted: ((String) -> Void)?
  var onFallback: ((String, Error, @escaping () -> Void) -> Void)?
  var onStreamFailure: ((Error) -> Void)?
  var onActivityChanged: ((Bool) -> Void)?

  var isActive: Bool { !chunks.isEmpty || fallbackInProgress }

  private enum StreamState {
    case pending
    case streaming
    case completed
    case failed(Error)
  }

  private final class Chunk {
    let id = UUID()
    let text: String
    var state: StreamState = .pending
    var bufferedData: [Data] = []
    var player: (any ProgressiveAudioPlaying)?
    var didStartPlayback = false

    init(text: String) {
      self.text = text
    }
  }

  private let streamFactory: StreamFactory
  private let playerFactory: PlayerFactory
  private let stallWaiter: StallWaiter
  private var chunks: [Chunk] = []
  private var networkTask: Task<Void, Never>?
  private var networkChunkID: UUID?
  private var stallTask: Task<Void, Never>?
  private var fallbackInProgress = false
  private var generation: UInt64 = 0

  init(
    stallTimeout: TimeInterval = 10,
    streamFactory: @escaping StreamFactory,
    playerFactory: @escaping PlayerFactory,
    stallWaiter: StallWaiter? = nil
  ) {
    self.streamFactory = streamFactory
    self.playerFactory = playerFactory
    if let stallWaiter {
      self.stallWaiter = stallWaiter
    } else {
      self.stallWaiter = {
        try await Task.sleep(for: .seconds(stallTimeout))
      }
    }
  }

  func enqueue(_ text: String) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    let wasActive = isActive
    chunks.append(Chunk(text: trimmed))
    if !wasActive { onActivityChanged?(true) }
    activateHeadIfNeeded()
    startNextNetworkIfNeeded()
  }

  func cancel() {
    let wasActive = isActive
    generation &+= 1
    networkTask?.cancel()
    networkTask = nil
    networkChunkID = nil
    stallTask?.cancel()
    stallTask = nil
    for chunk in chunks {
      chunk.player?.stop()
      chunk.player = nil
      chunk.bufferedData.removeAll()
    }
    chunks.removeAll()
    fallbackInProgress = false
    if wasActive { onActivityChanged?(false) }
  }

  private func activateHeadIfNeeded() {
    guard !fallbackInProgress, let chunk = chunks.first, chunk.player == nil else { return }
    if case .failed(let error) = chunk.state {
      beginFallback(for: chunk, text: chunk.text, error: error)
      return
    }

    do {
      let player = try playerFactory()
      chunk.player = player
      let chunkID = chunk.id
      player.onStarted = { [weak self] in
        guard let self else { return }
        self.playerDidStart(chunkID: chunkID)
      }
      player.onDrained = { [weak self] playedDuration in
        guard let self else { return }
        self.playerDidDrain(chunkID: chunkID, playedDuration: playedDuration)
      }
      let buffered = chunk.bufferedData
      chunk.bufferedData.removeAll(keepingCapacity: false)
      for data in buffered {
        try player.append(data)
      }
      if case .completed = chunk.state {
        player.finish()
      }
    } catch {
      handleStreamFailure(error, chunkID: chunk.id)
    }
  }

  private func startNextNetworkIfNeeded() {
    guard networkTask == nil else { return }
    guard
      // Keep at most the active chunk and one successor in flight. This gives
      // gapless next-chunk prefetch without allowing a long response to build
      // an unbounded compressed-audio backlog behind slow playback.
      let chunk = chunks.prefix(2).first(where: {
        if case .pending = $0.state { return true }
        return false
      })
    else { return }

    chunk.state = .streaming
    networkChunkID = chunk.id
    let chunkID = chunk.id
    let text = chunk.text
    let currentGeneration = generation
    armStallTimeout(for: chunkID, generation: currentGeneration)
    networkTask = Task { [weak self, streamFactory] in
      do {
        let stream = try await streamFactory(text)
        for try await data in stream {
          try Task.checkCancellation()
          guard let self, self.generation == currentGeneration else { return }
          self.receive(data, chunkID: chunkID)
        }
        guard let self, self.generation == currentGeneration else { return }
        self.handleStreamCompletion(chunkID: chunkID)
      } catch {
        guard let self, self.generation == currentGeneration else { return }
        self.handleStreamFailure(error, chunkID: chunkID)
      }
    }
  }

  private func receive(_ data: Data, chunkID: UUID) {
    guard !data.isEmpty, let chunk = chunks.first(where: { $0.id == chunkID }) else { return }
    guard case .streaming = chunk.state else { return }
    armStallTimeout(for: chunkID, generation: generation)
    do {
      if let player = chunk.player {
        try player.append(data)
      } else {
        chunk.bufferedData.append(data)
      }
    } catch {
      handleStreamFailure(error, chunkID: chunkID)
    }
  }

  private func handleStreamCompletion(chunkID: UUID) {
    guard let chunk = chunks.first(where: { $0.id == chunkID }) else { return }
    guard case .streaming = chunk.state else { return }
    chunk.state = .completed
    clearNetworkState(ifOwnedBy: chunkID)
    chunk.player?.finish()
    startNextNetworkIfNeeded()
  }

  private func handleStreamFailure(_ error: Error, chunkID: UUID) {
    guard let chunk = chunks.first(where: { $0.id == chunkID }) else { return }
    guard case .streaming = chunk.state else { return }
    chunk.state = .failed(error)
    clearNetworkState(ifOwnedBy: chunkID)
    onStreamFailure?(error)

    if chunks.first?.id == chunkID, let player = chunk.player {
      if chunk.didStartPlayback {
        // Flush the parser and let every already-enqueued packet drain before
        // the untouched text suffix moves to the system voice.
        player.finish()
      } else {
        player.stop()
        chunk.player = nil
        beginFallback(for: chunk, text: chunk.text, error: error)
      }
    }
  }

  private func playerDidStart(chunkID: UUID) {
    guard let chunk = chunks.first, chunk.id == chunkID else { return }
    chunk.didStartPlayback = true
    onPlaybackStarted?(chunk.text)
  }

  private func playerDidDrain(chunkID: UUID, playedDuration: TimeInterval) {
    guard let chunk = chunks.first, chunk.id == chunkID else { return }
    chunk.player?.stop()
    chunk.player = nil

    switch chunk.state {
    case .failed(let error):
      let remainder =
        chunk.didStartPlayback
        ? ProgressiveSpeechRemainder.untouchedSuffix(
          text: chunk.text,
          playedMediaDuration: playedDuration)
        : chunk.text
      beginFallback(for: chunk, text: remainder, error: error)
    case .completed:
      if chunk.didStartPlayback {
        finishHeadChunk(chunkID: chunkID)
      } else {
        beginFallback(
          for: chunk,
          text: chunk.text,
          error: ProgressiveTTSPlaybackError.noPlayableAudio)
      }
    case .pending, .streaming:
      break
    }
  }

  private func beginFallback(for chunk: Chunk, text: String, error: Error) {
    guard chunks.first?.id == chunk.id, !fallbackInProgress else { return }
    let fallbackText = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !fallbackText.isEmpty else {
      finishHeadChunk(chunkID: chunk.id)
      return
    }
    fallbackInProgress = true
    let fallbackGeneration = generation
    let chunkID = chunk.id
    let completion = { [weak self] in
      guard let self, self.generation == fallbackGeneration else { return }
      guard self.chunks.first?.id == chunkID else { return }
      self.fallbackInProgress = false
      self.finishHeadChunk(chunkID: chunkID)
    }
    if let onFallback {
      onFallback(fallbackText, error, completion)
    } else {
      completion()
    }
  }

  private func finishHeadChunk(chunkID: UUID) {
    guard chunks.first?.id == chunkID else { return }
    chunks.removeFirst()
    activateHeadIfNeeded()
    startNextNetworkIfNeeded()
    if !isActive { onActivityChanged?(false) }
  }

  private func armStallTimeout(for chunkID: UUID, generation: UInt64) {
    stallTask?.cancel()
    stallTask = Task { [weak self, stallWaiter] in
      do {
        try await stallWaiter()
        try Task.checkCancellation()
        guard let self, self.generation == generation else { return }
        self.handleStreamFailure(ProgressiveTTSPlaybackError.stalled, chunkID: chunkID)
      } catch {
        return
      }
    }
  }

  private func clearNetworkState(ifOwnedBy chunkID: UUID) {
    guard networkChunkID == chunkID else { return }
    stallTask?.cancel()
    stallTask = nil
    networkTask?.cancel()
    networkTask = nil
    networkChunkID = nil
  }
}
