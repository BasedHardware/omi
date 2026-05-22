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

    let chunks = chunker.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 10) + [0, 0, 0]), startTime: 0)

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

    let chunks = chunker.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 3)

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(chunks[0].startTime, 3)
    XCTAssertEqual(sampleCount(chunks[0].pcmData), 10)
    XCTAssertEqual(sampleCount(chunker.finishInput()[0].pcmData), 4)
  }

  func testSessionBackpressuresWhenPendingQueueIsFull() async throws {
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
      return [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)", text: "hello", start: chunk.startTime,
          end: chunk.startTime + 1)
      ]
    }

    let first = session.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 0)
    let second = session.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 1.2)

    XCTAssertEqual(first.enqueuedChunks, 1)
    XCTAssertEqual(first.pendingChunkCount, 1)
    XCTAssertTrue(first.isBackpressured)
    XCTAssertEqual(second.enqueuedChunks, 0)
    XCTAssertEqual(second.pendingChunkCount, 1)
    XCTAssertEqual(second.acceptedInputBytes, 0)
    XCTAssertTrue(second.isBackpressured)
    XCTAssertEqual(session.pendingChunkCount, 1)
    XCTAssertTrue(transcribedStarts.isEmpty)
  }

  func testChunkerDoesNotLoopWhenOverlapEqualsMinimumCut() {
    var chunker = BackgroundAudioChunker(
      configuration: BackgroundTranscriptionConfiguration(
        sampleRate: 10,
        maxChunkDuration: 3.0,
        minChunkDuration: 1.0,
        overlapDuration: 1.0,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 10,
        speechPeakAmplitudeThreshold: 100,
        speechRMSAmplitudeThreshold: 20,
        maxPendingChunks: 4
      )
    )

    let chunks = chunker.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 10) + [0, 0, 0]), startTime: 0)

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(sampleCount(chunks[0].pcmData), 11)
    let final = chunker.finishInput()
    XCTAssertEqual(final.count, 1)
    XCTAssertEqual(sampleCount(final[0].pcmData), 12)
  }

  func testFifteenSecondContinuousSpeechProducesChunkThroughSession() async throws {
    let configuration = BackgroundTranscriptionConfiguration.cloudBatch
    var transcribedStarts: [Double] = []
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      transcribedStarts.append(chunk.startTime)
      return [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)",
          text: "continuous speech",
          start: chunk.startTime,
          end: chunk.startTime + 1
        )
      ]
    }

    let samplesPerFrame = configuration.sampleRate / 10
    let frame = pcm(samples: Array(repeating: 1_000, count: samplesPerFrame))
    var enqueuedChunks = 0

    for frameIndex in 0..<160 {
      let result = session.append(pcmData: frame, startTime: Double(frameIndex) / 10.0)
      enqueuedChunks += result.enqueuedChunks
    }

    XCTAssertEqual(enqueuedChunks, 1)
    XCTAssertEqual(session.pendingChunkCount, 1)

    let first = try await session.transcribeNext()
    XCTAssertNotNil(first)
    XCTAssertEqual(first!.chunk.startTime, 0, accuracy: 0.001)
    XCTAssertEqual(sampleCount(first!.chunk.pcmData), configuration.sampleRate * 15)
    XCTAssertEqual(transcribedStarts, [0])
    XCTAssertEqual(session.snapshot().processedChunkCount, 1)
    XCTAssertEqual(session.snapshot().segments.count, 1)
  }

  func testCloudBatchDropsSilentChunksBeforeUpload() async throws {
    let configuration = BackgroundTranscriptionConfiguration.cloudBatch
    var uploadCount = 0
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      uploadCount += 1
      return [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)",
          text: "should not upload",
          start: chunk.startTime,
          end: chunk.startTime + 1
        )
      ]
    }

    let samplesPerFrame = configuration.sampleRate / 10
    let frame = pcm(samples: Array(repeating: 0, count: samplesPerFrame))
    var enqueuedChunks = 0

    for frameIndex in 0..<160 {
      let result = session.append(pcmData: frame, startTime: Double(frameIndex) / 10.0)
      enqueuedChunks += result.enqueuedChunks
    }

    XCTAssertEqual(enqueuedChunks, 0)
    XCTAssertEqual(session.pendingChunkCount, 0)
    let uploaded = try await session.transcribeNext()
    XCTAssertNil(uploaded)
    XCTAssertEqual(uploadCount, 0)
    XCTAssertEqual(session.snapshot().droppedChunkCount, 1)
    XCTAssertEqual(session.snapshot().lastSpeechActivityDecision?.reason, .insufficientSpeech)
  }

  func testCloudBatchUploadsChunkWithMinimumSpeechEnergy() async throws {
    let configuration = BackgroundTranscriptionConfiguration.cloudBatch
    var uploadCount = 0
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      uploadCount += 1
      return [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)",
          text: "speech",
          start: chunk.startTime,
          end: chunk.startTime + 1
        )
      ]
    }

    let speechSamples = Array(
      repeating: Int16(1_000), count: Int(Double(configuration.sampleRate) * 1.0))
    let silenceSamples = Array(
      repeating: Int16(0),
      count: configuration.sampleRate * 16 - speechSamples.count
    )
    let result = session.append(
      pcmData: pcm(samples: speechSamples + silenceSamples),
      startTime: 0
    )

    XCTAssertEqual(result.enqueuedChunks, 1)
    XCTAssertEqual(session.pendingChunkCount, 1)

    let uploaded = try await session.transcribeNext()
    XCTAssertEqual(uploaded?.chunk.startTime, 0)
    XCTAssertEqual(uploadCount, 1)
    XCTAssertEqual(session.snapshot().lastSpeechActivityDecision?.reason, .speechDetected)
  }

  func testCloudBatchRejectsEnergeticNonSpeechNoiseBeforeUpload() async throws {
    let configuration = BackgroundTranscriptionConfiguration.cloudBatch
    var uploadCount = 0
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      uploadCount += 1
      return [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)",
          text: "noise",
          start: chunk.startTime,
          end: chunk.startTime + 1
        )
      ]
    }

    let samples = (0..<(configuration.sampleRate * 16)).map { index -> Int16 in
      index.isMultiple(of: 2) ? 2_000 : -2_000
    }
    let result = session.append(pcmData: pcm(samples: samples), startTime: 0)

    XCTAssertEqual(result.enqueuedChunks, 0)
    XCTAssertEqual(session.pendingChunkCount, 0)
    let uploaded = try await session.transcribeNext()
    XCTAssertNil(uploaded)
    XCTAssertEqual(uploadCount, 0)
    XCTAssertEqual(session.snapshot().droppedChunkCount, 1)
    XCTAssertEqual(session.snapshot().lastSpeechActivityDecision?.reason, .energeticNonSpeech)
    XCTAssertGreaterThan(
      session.snapshot().lastSpeechActivityDecision?.rejectedHighZeroCrossingWindows ?? 0,
      0
    )
  }

  func testCloudBatchFinishSplitsLongTailAtFifteenSecondWindows() {
    let configuration = BackgroundTranscriptionConfiguration.cloudBatch
    var chunker = BackgroundAudioChunker(configuration: configuration)

    let samples = Array(repeating: Int16(1_000), count: configuration.sampleRate * 31)
    let chunks = chunker.append(pcmData: pcm(samples: samples), startTime: 0)
    let final = chunker.finishInput()

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(sampleCount(chunks[0].pcmData), configuration.sampleRate * 15)
    XCTAssertEqual(final.count, 2)
    XCTAssertEqual(sampleCount(final[0].pcmData), configuration.sampleRate * 15)
    XCTAssertLessThanOrEqual(sampleCount(final[1].pcmData), configuration.sampleRate * 2)
    XCTAssertTrue(final[1].isFinal)
  }

  func testSessionFinishEnqueuesTailEvenWhenLiveQueueIsFull() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 1.0,
      minChunkDuration: 1.0,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 1
    )
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      [
        Self.backendSegment(
          id: "chunk-\(chunk.startTime)", text: "chunk", start: chunk.startTime,
          end: chunk.startTime + 1)
      ]
    }

    let append = session.append(
      pcmData: pcm(samples: Array(repeating: 1_000, count: 16)), startTime: 0)
    let finish = session.finishInput()

    XCTAssertEqual(append.enqueuedChunks, 1)
    XCTAssertEqual(finish.enqueuedChunks, 1)
    XCTAssertEqual(finish.pendingChunkCount, 2)
    XCTAssertTrue(finish.isBackpressured)

    let first = try await session.transcribeNext()
    let tail = try await session.transcribeNext()
    XCTAssertEqual(first?.chunk.startTime, 0)
    XCTAssertEqual(tail!.chunk.startTime, 1, accuracy: 0.001)
    XCTAssertTrue(tail?.chunk.isFinal ?? false)
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
      [
        Self.backendSegment(
          id: "final", text: chunk.isFinal ? "final" : "not final", start: chunk.startTime, end: 1)
      ]
    }

    XCTAssertEqual(
      session.append(pcmData: pcm(samples: [1_000, 1_000, 1_000]), startTime: 2).enqueuedChunks,
      0)
    let finish = session.finishInput()

    XCTAssertTrue(finish.didFinishInput)
    XCTAssertEqual(finish.enqueuedChunks, 1)
    let result = try await session.transcribeNext()
    XCTAssertEqual(result?.chunk.startTime, 2)
    XCTAssertTrue(result?.chunk.isFinal ?? false)
  }

  func testSessionRetainsFailedChunkForRetry() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 1.0,
      minChunkDuration: 0.5,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 4,
      maxChunkTranscriptionAttempts: 3
    )
    var shouldFail = true
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      if shouldFail {
        shouldFail = false
        throw NSError(domain: "test", code: 1)
      }
      return [
        Self.backendSegment(
          id: "retry", text: "retried", start: chunk.startTime, end: chunk.startTime + 1)
      ]
    }

    XCTAssertEqual(
      session.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 0)
        .enqueuedChunks, 1)

    do {
      _ = try await session.transcribeNext()
      XCTFail("Expected first transcription attempt to fail")
    } catch {
      XCTAssertEqual(session.pendingChunkCount, 1)
      XCTAssertEqual(session.snapshot().droppedChunkCount, 0)
    }

    let retried = try await session.transcribeNext()
    XCTAssertEqual(retried?.chunk.startTime, 0)
    XCTAssertEqual(session.pendingChunkCount, 0)
    XCTAssertEqual(session.snapshot().processedChunkCount, 1)
    XCTAssertEqual(session.snapshot().droppedChunkCount, 0)
  }

  func testSessionRetriesFailedChunkBeforeDroppingSoDrainCanContinue() async throws {
    let configuration = BackgroundTranscriptionConfiguration(
      sampleRate: 10,
      maxChunkDuration: 1.0,
      minChunkDuration: 0.5,
      overlapDuration: 0,
      silenceWindowDuration: 0.2,
      silenceAmplitudeThreshold: 10,
      speechPeakAmplitudeThreshold: 100,
      speechRMSAmplitudeThreshold: 20,
      maxPendingChunks: 4,
      maxChunkTranscriptionAttempts: 2
    )
    let session = CloudBackgroundTranscriptionSession(configuration: configuration) { chunk in
      if chunk.startTime == 0 {
        throw NSError(domain: "test", code: 1)
      }
      return [
        Self.backendSegment(
          id: "retry", text: "retried", start: chunk.startTime, end: chunk.startTime + 1)
      ]
    }

    XCTAssertEqual(
      session.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 0)
        .enqueuedChunks, 1)
    XCTAssertEqual(
      session.append(pcmData: pcm(samples: Array(repeating: 1_000, count: 12)), startTime: 1.2)
        .enqueuedChunks, 1)

    do {
      _ = try await session.transcribeNext()
      XCTFail("Expected first transcription attempt to fail")
    } catch {
      XCTAssertEqual(session.pendingChunkCount, 2)
      XCTAssertEqual(session.snapshot().droppedChunkCount, 0)
    }

    do {
      _ = try await session.transcribeNext()
      XCTFail("Expected second transcription attempt to fail and drop the chunk")
    } catch {
      XCTAssertEqual(session.pendingChunkCount, 1)
      XCTAssertEqual(session.snapshot().droppedChunkCount, 1)
    }

    let next = try await session.transcribeNext()
    XCTAssertEqual(next?.chunk.startTime, 1.0)
    XCTAssertEqual(session.pendingChunkCount, 0)
    XCTAssertEqual(session.snapshot().processedChunkCount, 1)
    XCTAssertEqual(session.snapshot().droppedChunkCount, 1)
  }

  func testBackgroundChunkIdIsStableAndPayloadSensitive() {
    let first = TranscriptionService.backgroundChunkId(
      conversationId: "conv.123",
      chunkStartMs: 15_000,
      audioData: Data([1, 2, 3, 4])
    )
    let retry = TranscriptionService.backgroundChunkId(
      conversationId: "conv.123",
      chunkStartMs: 15_000,
      audioData: Data([1, 2, 3, 4])
    )
    let changedPayload = TranscriptionService.backgroundChunkId(
      conversationId: "conv.123",
      chunkStartMs: 15_000,
      audioData: Data([1, 2, 3, 5])
    )

    XCTAssertEqual(first, retry)
    XCTAssertNotEqual(first, changedPayload)
    XCTAssertTrue(first.hasPrefix("conv_123-15000-4-"))
    XCTAssertNil(first.range(of: #"[^A-Za-z0-9_-]"#, options: .regularExpression))
  }

  func testTranscriptMergerDeduplicatesAndMergesOverlap() {
    var merger = BackgroundTranscriptMerger()
    let first = Self.backendSegment(id: "a", text: "hello world", speakerId: 0, start: 0, end: 2)
    let duplicate = Self.backendSegment(
      id: nil, text: "hello world", speakerId: 0, start: 0.5, end: 1.8)
    let overlap = Self.backendSegment(
      id: "b", text: "world again", speakerId: 0, start: 1.5, end: 3)

    XCTAssertEqual(merger.merge([first]).count, 1)
    XCTAssertEqual(merger.merge([duplicate]).count, 0)
    let changed = merger.merge([overlap])
    let merged = merger.segments

    XCTAssertEqual(changed.count, 1)
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

    let update = Self.backendSegment(
      id: "seg-1", text: "hello again", speakerId: 1, start: 0, end: 2)
    let result = reducer.apply([update])

    XCTAssertEqual(result.added, 0)
    XCTAssertEqual(result.updated, 1)
    XCTAssertEqual(result.totalSegmentCount, 1)
    XCTAssertEqual(result.totalWordCount, 2)
    XCTAssertEqual(reducer.segments[0].translations.first?.text, "hola")
  }

  func testRoutingGuardUsesCloudBatchForMicrophoneWhenCapabilityUsable() {
    let guardrail = BackgroundTranscriptionRoutingGuard()

    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: Self.backgroundBatchCapability(
          enabled: true, effectiveProvider: "assemblyai"),
        audioSource: .microphone),
      .cloudBatchAssembly
    )
    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: Self.backgroundBatchCapability(
          enabled: true, effectiveProvider: "assemblyai"),
        audioSource: .bleDevice),
      .cloudListenStreaming(reason: "batch_microphone_only")
    )
    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: Self.backgroundBatchCapability(
          enabled: false, effectiveProvider: nil, reason: "missing_assemblyai_api_key"),
        audioSource: .microphone),
      .cloudListenStreaming(reason: "missing_assemblyai_api_key")
    )
    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: nil,
        audioSource: .microphone),
      .cloudListenStreaming(reason: "server_background_batch_capability_unavailable")
    )
    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: Self.backgroundBatchCapability(
          enabled: true, effectiveProvider: nil, reason: "no_usable_batch_provider"),
        audioSource: .microphone),
      .cloudListenStreaming(reason: "no_usable_batch_provider")
    )
    XCTAssertEqual(
      guardrail.decide(
        backgroundBatchCapability: Self.backgroundBatchCapability(
          enabled: true, effectiveProvider: "unknown-provider"),
        audioSource: .microphone),
      .cloudListenStreaming(reason: "server_background_batch_provider_unsupported")
    )
    XCTAssertTrue(
      guardrail.shouldFallbackToStreamingAfterBatchStartupFailure(
        audioSource: .microphone,
        captureStarted: false
      )
    )
    XCTAssertFalse(
      guardrail.shouldFallbackToStreamingAfterBatchStartupFailure(
        audioSource: .microphone,
        captureStarted: true
      )
    )
    XCTAssertFalse(
      guardrail.shouldFallbackToStreamingAfterBatchStartupFailure(
        audioSource: .bleDevice,
        captureStarted: false
      )
    )
  }

  func testDesktopCapabilitiesDecodeEffectiveProviderFields() throws {
    let json = Data(
      """
      {
        "background_batch": {
          "enabled": true,
          "mode": "deepgram_fallback",
          "provider": "assemblyai",
          "primary_provider": "assemblyai",
          "effective_provider": "deepgram",
          "fallback_provider": "deepgram",
          "fallback_enabled": true,
          "fallback_available": true,
          "workload": "background",
          "reason": "fallback_deepgram_available",
          "sample_rate": 16000,
          "channels": 1,
          "encoding": "linear16",
          "max_chunk_seconds": 15
        }
      }
      """.utf8)

    let decoded = try JSONDecoder().decode(DesktopCapabilitiesResponse.self, from: json)

    XCTAssertTrue(decoded.backgroundBatch.enabled)
    XCTAssertEqual(decoded.backgroundBatch.mode, "deepgram_fallback")
    XCTAssertEqual(decoded.backgroundBatch.primaryProvider, "assemblyai")
    XCTAssertEqual(decoded.backgroundBatch.effectiveProvider, "deepgram")
    XCTAssertEqual(decoded.backgroundBatch.fallbackProvider, "deepgram")
    XCTAssertEqual(decoded.backgroundBatch.reason, "fallback_deepgram_available")
  }

  func testOlderDesktopCapabilitiesDecodeWithoutEffectiveProviderFields() throws {
    let json = Data(
      """
      {
        "background_batch": {
          "enabled": false,
          "provider": "assemblyai",
          "sample_rate": 16000,
          "channels": 1,
          "encoding": "linear16",
          "max_chunk_seconds": 15
        }
      }
      """.utf8)

    let decoded = try JSONDecoder().decode(DesktopCapabilitiesResponse.self, from: json)

    XCTAssertFalse(decoded.backgroundBatch.enabled)
    XCTAssertNil(decoded.backgroundBatch.effectiveProvider)
    XCTAssertEqual(
      BackgroundTranscriptionRoutingGuard().decide(
        backgroundBatchCapability: decoded.backgroundBatch,
        audioSource: .microphone),
      .cloudListenStreaming(reason: "server_background_batch_disabled")
    )
  }

  private static func backgroundBatchCapability(
    enabled: Bool,
    effectiveProvider: String?,
    reason: String? = nil
  ) -> DesktopBackgroundBatchCapability {
    DesktopBackgroundBatchCapability(
      enabled: enabled,
      mode: enabled ? "assemblyai_primary" : "disabled",
      provider: "assemblyai",
      primaryProvider: "assemblyai",
      effectiveProvider: effectiveProvider,
      fallbackProvider: "deepgram",
      fallbackEnabled: true,
      fallbackAvailable: true,
      reason: reason,
      sampleRate: 16000,
      channels: 1,
      encoding: "linear16",
      maxChunkSeconds: 15
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
