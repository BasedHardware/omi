import Foundation

struct BackgroundIngestResult: Equatable {
  let enqueuedChunks: Int
  let pendingChunkCount: Int
  let acceptedInputBytes: Int
  let didFinishInput: Bool
  let isBackpressured: Bool
}

struct BackgroundTranscriptionResult {
  let chunk: BackgroundAudioChunk
  let segments: [TranscriptionService.BackendSegment]
}

struct BackgroundTranscriptSnapshot {
  let pendingChunkCount: Int
  let processedChunkCount: Int
  let isInputFinished: Bool
  let segments: [TranscriptionService.BackendSegment]
}

final class CloudBackgroundTranscriptionSession {
  typealias TranscribeHandler = (BackgroundAudioChunk) async throws -> [TranscriptionService.BackendSegment]

  private let configuration: BackgroundTranscriptionConfiguration
  private let transcribe: TranscribeHandler
  private var chunker: BackgroundAudioChunker
  private var pendingChunks: [BackgroundAudioChunk] = []
  private var processedChunkCount = 0
  private var isInputFinished = false
  private var processedSegments: [TranscriptionService.BackendSegment] = []

  init(
    configuration: BackgroundTranscriptionConfiguration = BackgroundTranscriptionConfiguration(),
    transcribe: @escaping TranscribeHandler
  ) {
    self.configuration = configuration
    self.transcribe = transcribe
    self.chunker = BackgroundAudioChunker(configuration: configuration)
  }

  var pendingChunkCount: Int {
    pendingChunks.count
  }

  func append(pcmData: Data, startTime: Double) -> BackgroundIngestResult {
    guard !isInputFinished else {
      return BackgroundIngestResult(
        enqueuedChunks: 0,
        pendingChunkCount: pendingChunks.count,
        acceptedInputBytes: 0,
        didFinishInput: true,
        isBackpressured: pendingChunks.count >= configuration.maxPendingChunks
      )
    }

    let chunks = chunker.append(pcmData: pcmData, startTime: startTime)
    pendingChunks.append(contentsOf: chunks)
    return BackgroundIngestResult(
      enqueuedChunks: chunks.count,
      pendingChunkCount: pendingChunks.count,
      acceptedInputBytes: pcmData.count,
      didFinishInput: false,
      isBackpressured: pendingChunks.count >= configuration.maxPendingChunks
    )
  }

  func finishInput() -> BackgroundIngestResult {
    guard !isInputFinished else {
      return BackgroundIngestResult(
        enqueuedChunks: 0,
        pendingChunkCount: pendingChunks.count,
        acceptedInputBytes: 0,
        didFinishInput: true,
        isBackpressured: pendingChunks.count >= configuration.maxPendingChunks
      )
    }

    let chunks = chunker.finishInput()
    pendingChunks.append(contentsOf: chunks)
    isInputFinished = true
    return BackgroundIngestResult(
      enqueuedChunks: chunks.count,
      pendingChunkCount: pendingChunks.count,
      acceptedInputBytes: 0,
      didFinishInput: true,
      isBackpressured: pendingChunks.count >= configuration.maxPendingChunks
    )
  }

  func transcribeNext() async throws -> BackgroundTranscriptionResult? {
    guard !pendingChunks.isEmpty else { return nil }
    let chunk = pendingChunks[0]
    let segments = try await transcribe(chunk)
    pendingChunks.removeFirst()
    processedChunkCount += 1
    processedSegments.append(contentsOf: segments)
    return BackgroundTranscriptionResult(chunk: chunk, segments: segments)
  }

  func snapshot() -> BackgroundTranscriptSnapshot {
    BackgroundTranscriptSnapshot(
      pendingChunkCount: pendingChunks.count,
      processedChunkCount: processedChunkCount,
      isInputFinished: isInputFinished,
      segments: processedSegments
    )
  }
}
