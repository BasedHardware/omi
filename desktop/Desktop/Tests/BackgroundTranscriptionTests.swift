import XCTest
@testable import Omi_Computer

final class BackgroundTranscriptionTests: XCTestCase {
  func testChunkerCutsAtSilenceAndRetainsOverlap() {
    var chunker = BackgroundAudioChunker(
      configuration: BackgroundTranscriptionConfiguration(
        sampleRate: 10,
        maxChunkDuration: 3.0,
        minChunkDuration: 1.0,
        overlapDuration: 0.5,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 10,
        speechPeakAmplitudeThreshold: 100,
        speechRMSAmplitudeThreshold: 20,
        maxPendingChunks: 4
      )
    )

    let chunks = chunker.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 10) + [0, 0, 0]), startTime: 0)

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(chunks[0].startTime, 0)
    XCTAssertEqual(sampleCount(chunks[0].pcmData), 10)
    XCTAssertFalse(chunks[0].isFinal)

    let final = chunker.finishInput()
    XCTAssertEqual(final.count, 1)
    XCTAssertEqual(final[0].startTime, 0.5, accuracy: 0.001)
    XCTAssertEqual(sampleCount(final[0].pcmData), 8)
    XCTAssertTrue(final[0].isFinal)
  }

  func testChunkerHardCutsAtMaxDurationWithoutSilence() {
    var chunker = BackgroundAudioChunker(
      configuration: BackgroundTranscriptionConfiguration(
        sampleRate: 10,
        maxChunkDuration: 1.0,
        minChunkDuration: 0.5,
        overlapDuration: 0.2,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 10,
        speechPeakAmplitudeThreshold: 100,
        speechRMSAmplitudeThreshold: 20,
        maxPendingChunks: 4
      )
    )

    let chunks = chunker.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 3)

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(chunks[0].startTime, 3)
    XCTAssertEqual(sampleCount(chunks[0].pcmData), 10)
    XCTAssertEqual(sampleCount(chunker.finishInput()[0].pcmData), 4)
  }

  func testSessionQueuesChunksAndSignalsBackpressureWithoutDropping() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 1.0,
      minChunkDuration: 0.5,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 1
    )
    var transcribedStarts: [Double] = []
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      transcribedStarts.append(chunk.startTime)
      return [Self.backendSegment(id: "chunk-\(chunk.startTime)", text: "hello", start: chunk.startTime, end: chunk.startTime + 1)]
    }

    let result = session.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 22)), startTime: 0)

    XCTAssertEqual(result.enqueuedChunks, 2)
    XCTAssertEqual(result.pendingChunkCount, 2)
    XCTAssertTrue(result.isBackpressured)
    XCTAssertEqual(session.pendingChunkCount, 2)

    let first = try await session.transcribeNext()
    let second = try await session.transcribeNext()

    XCTAssertEqual(first?.chunk.startTime, 0)
    XCTAssertEqual(second?.chunk.startTime, 1)
    XCTAssertEqual(transcribedStarts, [0, 1])
    let empty = try await session.transcribeNext()
    XCTAssertNil(empty)
    XCTAssertEqual(session.snapshot().processedChunkCount, 2)
    XCTAssertEqual(session.snapshot().segments.count, 2)
  }

  func testSessionFinishFlushesTail() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 10,
      minChunkDuration: 1,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 4
    )
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      [Self.backendSegment(id: "final", text: chunk.isFinal ? "final" : "not final", start: chunk.startTime, end: 1)]
    }

    XCTAssertEqual(session.append(pcmData: pcm(samples: [1_000, 1_000, 1_000]), startTime: 2).enqueuedChunks, 0)
    let finish = session.finishInput()

    XCTAssertTrue(finish.didFinishInput)
    XCTAssertEqual(finish.enqueuedChunks, 1)
    let result = try await session.transcribeNext()
    XCTAssertEqual(result?.chunk.startTime, 2)
    XCTAssertTrue(result?.chunk.isFinal ?? false)
  }

  func testSessionRetainsChunkWhenTranscriptionFails() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 1.0,
      minChunkDuration: 0.5,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 4
    )
    var shouldFail = true
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      if shouldFail {
        shouldFail = false
        throw NSError(domain: "test", code: 1)
      }
      return [Self.backendSegment(id: "retry", text: "retried", start: chunk.startTime, end: chunk.startTime + 1)]
    }

    XCTAssertEqual(session.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 0).enqueuedChunks, 1)

    do {
      _ = try await session.transcribeNext()
      XCTFail("Expected first transcription attempt to fail")
    } catch {
      XCTAssertEqual(session.pendingChunkCount, 1)
    }

    let retried = try await session.transcribeNext()
    XCTAssertEqual(retried?.chunk.startTime, 0)
    XCTAssertEqual(session.pendingChunkCount, 0)
    XCTAssertEqual(session.snapshot().processedChunkCount, 1)
  }

  func testTranscriptMergerDeduplicatesAndMergesOverlap() {
    var merger = BackgroundTranscriptMerger()
    let first = Self.backendSegment(id: "a", text: "hello world", speakerId: 0, start: 0, end: 2)
    let duplicate = Self.backendSegment(id: nil, text: "hello world", speakerId: 0, start: 0.5, end: 1.8)
    let overlap = Self.backendSegment(id: "b", text: "world again", speakerId: 0, start: 1.5, end: 3)

    XCTAssertEqual(merger.merge([first]).count, 1)
    XCTAssertEqual(merger.merge([duplicate]).count, 1)
    let merged = merger.merge([overlap])

    XCTAssertEqual(merged.count, 1)
    XCTAssertEqual(merged[0].text, "hello world again")
    XCTAssertEqual(merged[0].start, 0)
    XCTAssertEqual(merged[0].end, 3)
  }

  func testSpeakerSegmentReducerUpdatesAndPreservesTranslations() {
    var reducer = SpeakerSegmentReducer(maxInMemorySegments: 10)
    let original = SpeakerSegment(
      segmentId: "seg-1",
      speaker: 1,
      text: "hello",
      start: 0,
      end: 1,
      translations: [SegmentTranslation(lang: "es", text: "hola")]
    )
    _ = reducer.apply([original])

    let update = Self.backendSegment(id: "seg-1", text: "hello again", speakerId: 1, start: 0, end: 2)
    let result = reducer.apply([update])

    XCTAssertEqual(result.added, 0)
    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(result.totalSegmentCount, 1)
    XCTAssertEqual(result.totalWordCount, 2)
    XCTAssertEqual(reducer.segments[0].translations.first?.text, "hola")
  }

  func testRoutingGuardOnlyAllowsCloudBatchForEnabledMicrophone() {
    let guardrail = BackgroundTranscriptionRoutingGuard()

    XCTAssertEqual(
      guardrail.decide(batchEnabled: true, serverAssemblyBackgroundEnabled: true, audioSource: .microphone),
      .cloudBatchAssembly
    )
    XCTAssertEqual(
      guardrail.decide(batchEnabled: true, serverAssemblyBackgroundEnabled: true, audioSource: .bleDevice),
      .cloudListenStreaming(reason: "batch_microphone_only")
    )
    XCTAssertEqual(
      guardrail.decide(batchEnabled: false, serverAssemblyBackgroundEnabled: true, audioSource: .microphone),
      .cloudListenStreaming(reason: "batch_disabled")
    )
    XCTAssertEqual(
      guardrail.decide(batchEnabled: true, serverAssemblyBackgroundEnabled: false, audioSource: .microphone),
      .cloudListenStreaming(reason: "server_background_batch_disabled")
    )
  }

  private static func backendSegment(
    id: String?,
    text: String,
    speakerId: Int = 0,
    start: Double,
    end: Double
  ) -> TranscriptionService.BackendSegment {
    TranscriptionService.BackendSegment(
      id: id,
      text: text,
      speaker: "SPEAKER_\(String(format: "%02d", speakerId))",
      speaker_id: speakerId,
      is_user: false,
      person_id: nil,
      start: start,
      end: end,
      translations: nil,
      stt_provider: "assemblyai",
      stt_model: "universal-2",
      provider_cluster_id: nil,
      provider_speaker_label: nil,
      speaker_identity_state: nil,
      speaker_identity_confidence: nil,
      speaker_identity_source: nil,
      speaker_identity_version: nil
    )
  }

  private func pcm(samples: [Int16]) -> Data {
    var samples = samples
    return samples.withUnsafeMutableBufferPointer { Data(buffer: $0) }
  }

  private func sampleCount(_ data: Data) -> Int {
    data.count / MemoryLayout<Int16>.size
  }
}
