import Foundation
import XCTest

@testable import Omi_Computer

final class LocalBackgroundSmokeHarnessTests: XCTestCase {
  func testRunHarness() async throws {
    let environment = ProcessInfo.processInfo.environment
    guard environment["OMI_LOCAL_BACKGROUND_ASR_HARNESS"] == "1" else {
      throw XCTSkip("Set OMI_LOCAL_BACKGROUND_ASR_HARNESS=1 to run the harness")
    }
    guard let pcmPath = environment["OMI_LOCAL_BACKGROUND_ASR_PCM_PATH"], !pcmPath.isEmpty else {
      XCTFail("OMI_LOCAL_BACKGROUND_ASR_PCM_PATH is required")
      return
    }
    guard let outputPath = environment["OMI_LOCAL_BACKGROUND_ASR_OUTPUT_PATH"], !outputPath.isEmpty
    else {
      XCTFail("OMI_LOCAL_BACKGROUND_ASR_OUTPUT_PATH is required")
      return
    }

    let mode = environment["OMI_LOCAL_BACKGROUND_ASR_MODE"] ?? "fixture"
    let sampleRate = Int(environment["OMI_LOCAL_BACKGROUND_ASR_SAMPLE_RATE"] ?? "16000") ?? 16000
    let model = LocalTranscriptionModel(rawValue: environment["OMI_LOCAL_ASR_MODEL"] ?? "base")
      ?? .base
    let engine = LocalTranscriptionEngine(rawValue: environment["OMI_LOCAL_ASR_ENGINE"] ?? "")
      ?? .mlxWhisper
    let quality = TranscriptionQualityPreset(rawValue: environment["OMI_LOCAL_ASR_QUALITY"] ?? "fast")
      ?? .fast
    let language = environment["OMI_LOCAL_ASR_LANGUAGE"] ?? "en"
    let audioData = try Data(contentsOf: URL(fileURLWithPath: pcmPath))
    let fixtureText = environment["OMI_LOCAL_BACKGROUND_ASR_FIXTURE_TEXT"]
      ?? "hello local background transcription"
    let start = Date()
    var requestCounter = 0

    let session: LocalBackgroundTranscriptionSession
    let plan = LocalTranscriptionPlan(engine: engine, model: model, quality: quality)
    let configuration = LocalBackgroundChunkerConfiguration(
      sampleRate: sampleRate,
      bytesPerSample: 2,
      maxChunkDuration: Double(environment["OMI_LOCAL_BACKGROUND_ASR_MAX_CHUNK_SECONDS"] ?? "2")
        ?? 2,
      minChunkDuration: Double(environment["OMI_LOCAL_BACKGROUND_ASR_MIN_CHUNK_SECONDS"] ?? "0.4")
        ?? 0.4,
      overlapDuration: Double(environment["OMI_LOCAL_BACKGROUND_ASR_OVERLAP_SECONDS"] ?? "0.25")
        ?? 0.25,
      silenceWindowDuration: 0.25,
      silenceAmplitudeThreshold: 256,
      maxPendingChunks: 64
    )

    if mode == "local" {
      guard let helperURL = LocalASRHelperLocator.defaultExecutableURL() else {
        XCTFail("Local ASR helper is unavailable; run fixture mode or set OMI_LOCAL_ASR_HELPER_PATH")
        return
      }
      session = LocalBackgroundTranscriptionSession(
        language: language,
        plan: plan,
        configuration: configuration,
        executableURL: helperURL,
        timeoutSeconds: Double(environment["OMI_LOCAL_ASR_TIMEOUT_SECONDS"] ?? "120") ?? 120
      )
    } else {
      session = LocalBackgroundTranscriptionSession(
        language: language,
        plan: plan,
        configuration: configuration,
        requestHandler: { request in
          let current = requestCounter
          requestCounter += 1
          let bytes = (try? Data(contentsOf: URL(fileURLWithPath: request.audioPath)).count) ?? 0
          let duration = Double(bytes) / Double(max(1, sampleRate * 2))
          let words = fixtureText.split(separator: " ").map(String.init)
          let word = words.isEmpty ? "fixture" : words[current % words.count]
          return LocalASRTranscriptionResponse(
            requestId: request.requestId,
            engine: request.engine,
            model: request.model,
            language: request.language,
            segments: [
              LocalASRTranscriptSegment(
                id: "fixture-\(current)",
                speaker: 0,
                text: "\(word) chunk \(current)",
                start: 0,
                end: max(0.01, duration)
              )
            ],
            fixture: true
          )
        }
      )
    }

    let inputStepBytes = max(2, sampleRate * 2 / 2)
    var offset = 0
    var startTime = 0.0
    var droppedChunkCount = 0
    while offset < audioData.count {
      let end = min(audioData.count, offset + inputStepBytes)
      let result = session.append(pcmData: audioData[offset..<end], startTime: startTime)
      droppedChunkCount += result.droppedChunks.count
      let samples = (end - offset) / 2
      startTime += Double(samples) / Double(sampleRate)
      offset = end
    }
    let finishResult = session.finishInput()
    droppedChunkCount += finishResult.droppedChunks.count

    _ = try await session.transcribePending()
    let snapshot = session.snapshot()
    let elapsed = Date().timeIntervalSince(start)
    let audioDuration = Double(audioData.count / 2) / Double(sampleRate)
    let joinedTranscript = snapshot.joinedTranscript
    let reference = environment["OMI_LOCAL_BACKGROUND_ASR_REFERENCE"]
    let scores = reference.map {
      HarnessScores(
        reference: $0,
        normalizedReference: TranscriptComparison.normalizedText($0),
        normalizedHypothesis: TranscriptComparison.normalizedText(joinedTranscript),
        wordErrorRate: TranscriptComparison.wordErrorRate(reference: $0, hypothesis: joinedTranscript),
        characterErrorRate: TranscriptComparison.characterErrorRate(
          reference: $0,
          hypothesis: joinedTranscript
        )
      )
    }
    let report = HarnessReport(
      mode: mode,
      pcmPath: pcmPath,
      language: language,
      sampleRate: sampleRate,
      engine: plan.engine.rawValue,
      model: plan.model.rawValue,
      quality: plan.quality.rawValue,
      audioDurationSeconds: audioDuration,
      elapsedSeconds: elapsed,
      realTimeFactor: audioDuration > 0 ? elapsed / audioDuration : nil,
      droppedChunkCount: droppedChunkCount + session.droppedChunkCount,
      chunkResults: snapshot.rawChunkResults.map(HarnessChunkResult.init),
      joinedTranscript: joinedTranscript,
      scores: scores
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let outputURL = URL(fileURLWithPath: outputPath)
    try FileManager.default.createDirectory(
      at: outputURL.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try encoder.encode(report).write(to: outputURL, options: .atomic)
  }
}

private struct HarnessReport: Encodable {
  var mode: String
  var pcmPath: String
  var language: String
  var sampleRate: Int
  var engine: String
  var model: String
  var quality: String
  var audioDurationSeconds: Double
  var elapsedSeconds: Double
  var realTimeFactor: Double?
  var droppedChunkCount: Int
  var chunkResults: [HarnessChunkResult]
  var joinedTranscript: String
  var scores: HarnessScores?
}

private struct HarnessChunkResult: Encodable {
  var sequence: Int
  var startTime: Double
  var endTime: Double
  var overlappedStartTime: Double?
  var latencySeconds: Double
  var helperEngine: String
  var helperModel: String
  var fixture: Bool
  var rawSegments: [LocalASRTranscriptSegment]
  var remappedSegments: [NormalizedTranscriptSegment]
  var joinedText: String

  init(_ result: LocalBackgroundASRRawChunkResult) {
    sequence = result.chunk.sequence
    startTime = result.chunk.startTime
    endTime = result.chunk.endTime
    overlappedStartTime = result.chunk.overlappedStartTime
    latencySeconds = result.latencySeconds
    helperEngine = result.response.engine.rawValue
    helperModel = result.response.model.rawValue
    fixture = result.response.fixture
    rawSegments = result.response.segments
    remappedSegments = result.remappedSegments
    joinedText = result.joinedText
  }
}

private struct HarnessScores: Encodable {
  var reference: String
  var normalizedReference: String
  var normalizedHypothesis: String
  var wordErrorRate: Double
  var characterErrorRate: Double
}
