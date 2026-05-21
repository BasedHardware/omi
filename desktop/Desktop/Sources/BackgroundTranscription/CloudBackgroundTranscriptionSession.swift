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
  let droppedChunkCount: Int
  let isInputFinished: Bool
  let segments: [TranscriptionService.BackendSegment]
  let lastSpeechActivityDecision: SpeechActivityDecision?
}

final class CloudBackgroundTranscriptionSession {
  typealias TranscribeHandler = (BackgroundAudioChunk) async throws -> [TranscriptionService
    .BackendSegment]

  private let configuration: BackgroundTranscriptionConfiguration
  private let transcribe: TranscribeHandler
  private let speechActivityDetector: SpeechActivityDetector
  private var chunker: BackgroundAudioChunker
  private var pendingChunks: [BackgroundAudioChunk] = []
  private var processedChunkCount = 0
  private var droppedChunkCount = 0
  private var isInputFinished = false
  private var processedSegments: [TranscriptionService.BackendSegment] = []
  private var lastSpeechActivityDecision: SpeechActivityDecision?

  init(
    configuration: BackgroundTranscriptionConfiguration = BackgroundTranscriptionConfiguration(),
    transcribe: @escaping TranscribeHandler
  ) {
    self.configuration = configuration
    self.transcribe = transcribe
    self.speechActivityDetector = SpeechActivityDetector(
      configuration: configuration.speechActivityDetection,
      sampleRate: configuration.sampleRate,
      bytesPerSample: configuration.bytesPerSample
    )
    self.chunker = BackgroundAudioChunker(configuration: configuration)
  }

  var pendingChunkCount: Int {
    pendingChunks.count
  }

  var isBackpressured: Bool {
    pendingChunks.count >= configuration.maxPendingChunks
  }

  func append(pcmData: Data, startTime: Double) -> BackgroundIngestResult {
    guard !isInputFinished else {
      return BackgroundIngestResult(
        enqueuedChunks: 0,
        pendingChunkCount: pendingChunks.count,
        acceptedInputBytes: 0,
        didFinishInput: true,
        isBackpressured: isBackpressured
      )
    }
    guard !isBackpressured else {
      return BackgroundIngestResult(
        enqueuedChunks: 0,
        pendingChunkCount: pendingChunks.count,
        acceptedInputBytes: 0,
        didFinishInput: false,
        isBackpressured: true
      )
    }

    let chunks = chunker.append(pcmData: pcmData, startTime: startTime)
    var enqueuedChunks = 0
    for chunk in chunks where pendingChunks.count < configuration.maxPendingChunks {
      guard shouldUpload(chunk) else {
        droppedChunkCount += 1
        continue
      }
      pendingChunks.append(chunk)
      enqueuedChunks += 1
    }
    return BackgroundIngestResult(
      enqueuedChunks: enqueuedChunks,
      pendingChunkCount: pendingChunks.count,
      acceptedInputBytes: pcmData.count,
      didFinishInput: false,
      isBackpressured: isBackpressured
    )
  }

  func finishInput() -> BackgroundIngestResult {
    guard !isInputFinished else {
      return BackgroundIngestResult(
        enqueuedChunks: 0,
        pendingChunkCount: pendingChunks.count,
        acceptedInputBytes: 0,
        didFinishInput: true,
        isBackpressured: isBackpressured
      )
    }

    var enqueuedChunks = 0
    for chunk in chunker.finishInput() {
      guard shouldUpload(chunk) else {
        droppedChunkCount += 1
        continue
      }
      pendingChunks.append(chunk)
      enqueuedChunks += 1
    }
    isInputFinished = true
    return BackgroundIngestResult(
      enqueuedChunks: enqueuedChunks,
      pendingChunkCount: pendingChunks.count,
      acceptedInputBytes: 0,
      didFinishInput: true,
      isBackpressured: isBackpressured
    )
  }

  func transcribeNext() async throws -> BackgroundTranscriptionResult? {
    guard !pendingChunks.isEmpty else { return nil }
    let chunk = pendingChunks.removeFirst()
    do {
      let segments = try await transcribe(chunk)
      processedChunkCount += 1
      processedSegments.append(contentsOf: segments)
      return BackgroundTranscriptionResult(chunk: chunk, segments: segments)
    } catch {
      droppedChunkCount += 1
      throw error
    }
  }

  func snapshot() -> BackgroundTranscriptSnapshot {
    BackgroundTranscriptSnapshot(
      pendingChunkCount: pendingChunks.count,
      processedChunkCount: processedChunkCount,
      droppedChunkCount: droppedChunkCount,
      isInputFinished: isInputFinished,
      segments: processedSegments,
      lastSpeechActivityDecision: lastSpeechActivityDecision
    )
  }

  private func shouldUpload(_ chunk: BackgroundAudioChunk) -> Bool {
    guard configuration.requiresSpeechBeforeUpload else { return true }
    let decision = speechActivityDetector.evaluate(pcmData: chunk.pcmData)
    lastSpeechActivityDecision = decision
    return decision.shouldUpload
  }
}
