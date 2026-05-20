import XCTest

@testable import Omi_Computer

final class TranscriptionProviderPolicyTests: XCTestCase {
  func testAutoPrefersMLXOnlyOnNativeAppleSilicon() {
    let capabilities = LocalTranscriptionCapabilities(
      processor: .nativeAppleSilicon,
      physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
      availableEngines: [.mlxWhisper, .fasterWhisper]
    )

    let result = TranscriptionProviderPolicy().resolve(
      selection: TranscriptionProviderSelection(mode: .auto, quality: .balanced),
      capabilities: capabilities
    )

    XCTAssertEqual(result.provider, .local)
    XCTAssertEqual(result.localEngine, .mlxWhisper)
    XCTAssertEqual(result.localPlan?.model, .small)
    XCTAssertNil(result.fallbackReason)
  }

  func testAutoFallsBackToFasterWhisperWhenMLXIsNotViable() {
    let capabilities = LocalTranscriptionCapabilities(
      processor: .rosettaOnAppleSilicon,
      physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
      availableEngines: [.mlxWhisper, .fasterWhisper]
    )

    let result = TranscriptionProviderPolicy().resolve(
      selection: TranscriptionProviderSelection(mode: .auto, quality: .fast),
      capabilities: capabilities
    )

    XCTAssertEqual(result.provider, .local)
    XCTAssertEqual(result.localEngine, .fasterWhisper)
    XCTAssertEqual(result.localPlan?.model, .base)
  }

  func testAutoFallsBackToCloudWhenNoLocalEngineExists() {
    let capabilities = LocalTranscriptionCapabilities(
      processor: .nativeAppleSilicon,
      physicalMemoryBytes: 8 * 1024 * 1024 * 1024,
      availableEngines: []
    )

    let result = TranscriptionProviderPolicy().resolve(
      selection: TranscriptionProviderSelection(mode: .auto, quality: .auto),
      capabilities: capabilities
    )

    XCTAssertEqual(result.provider, .cloud)
    XCTAssertNil(result.localEngine)
    XCTAssertNil(result.localPlan)
    XCTAssertNotNil(result.fallbackReason)
  }

  func testCloudSelectionAlwaysUsesCloud() {
    let capabilities = LocalTranscriptionCapabilities(
      processor: .nativeAppleSilicon,
      physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
      availableEngines: [.mlxWhisper]
    )

    let result = TranscriptionProviderPolicy().resolve(
      selection: TranscriptionProviderSelection(mode: .cloud, quality: .accurate),
      capabilities: capabilities
    )

    XCTAssertEqual(result.provider, .cloud)
    XCTAssertNil(result.localEngine)
    XCTAssertNil(result.localPlan)
    XCTAssertNil(result.fallbackReason)
  }

  func testAccurateUsesLargerModelsOnlyWhenMemoryAllows() {
    let lowMemory = LocalTranscriptionCapabilities(
      processor: .nativeAppleSilicon,
      physicalMemoryBytes: 8 * 1024 * 1024 * 1024,
      availableEngines: [.mlxWhisper]
    )
    let highMemory = LocalTranscriptionCapabilities(
      processor: .nativeAppleSilicon,
      physicalMemoryBytes: 24 * 1024 * 1024 * 1024,
      availableEngines: [.mlxWhisper]
    )

    let policy = TranscriptionProviderPolicy()
    let lowMemoryResult = policy.resolve(
      selection: TranscriptionProviderSelection(mode: .local, quality: .accurate),
      capabilities: lowMemory
    )
    let highMemoryResult = policy.resolve(
      selection: TranscriptionProviderSelection(mode: .local, quality: .accurate),
      capabilities: highMemory
    )

    XCTAssertEqual(lowMemoryResult.localPlan?.model, .small)
    XCTAssertEqual(highMemoryResult.localPlan?.model, .largeV3Turbo)
  }

  func testCapabilityDetectorDistinguishesRosettaFromNativeArm() {
    let native = LocalTranscriptionCapabilityDetector(
      physicalMemoryBytes: { 1 },
      isTranslatedProcess: { false },
      availableEngines: { [] }
    ).detect()
    let translated = LocalTranscriptionCapabilityDetector(
      physicalMemoryBytes: { 1 },
      isTranslatedProcess: { true },
      availableEngines: { [] }
    ).detect()

    #if arch(arm64)
      XCTAssertEqual(native.processor, .nativeAppleSilicon)
      XCTAssertEqual(translated.processor, .rosettaOnAppleSilicon)
    #elseif arch(x86_64)
      XCTAssertEqual(native.processor, .intel)
      XCTAssertEqual(translated.processor, .rosettaOnAppleSilicon)
    #else
      XCTAssertEqual(native.processor, .unknown)
      XCTAssertEqual(translated.processor, .unknown)
    #endif
  }
}

final class SpeakerSegmentReducerTests: XCTestCase {
  func testReducerAddsUpdatesAndPreservesTranslations() {
    var reducer = SpeakerSegmentReducer(maxInMemorySegments: 10)
    let initial = SpeakerSegment(
      segmentId: "s1",
      speaker: 0,
      text: "hello world",
      start: 0,
      end: 1,
      isUser: true,
      personId: "p1",
      translations: [SegmentTranslation(lang: "es", text: "hola mundo")]
    )

    let first = reducer.apply([initial])
    XCTAssertEqual(first.added, 1)
    XCTAssertEqual(reducer.totalSegmentCount, 1)
    XCTAssertEqual(reducer.totalWordCount, 2)

    let updateWithoutTranslations = SpeakerSegment(
      segmentId: "s1",
      speaker: 0,
      text: "hello again world",
      start: 0,
      end: 1.5,
      isUser: true,
      personId: "p1",
      translations: []
    )

    let second = reducer.apply([updateWithoutTranslations])
    XCTAssertEqual(second.updated, 1)
    XCTAssertEqual(reducer.totalSegmentCount, 1)
    XCTAssertEqual(reducer.totalWordCount, 3)
    XCTAssertEqual(reducer.segments.first?.translations.first?.text, "hola mundo")
  }

  func testReducerTrimsInMemorySegmentsButKeepsTotalCount() {
    var reducer = SpeakerSegmentReducer(maxInMemorySegments: 2)

    for index in 0..<3 {
      _ = reducer.apply([
        SpeakerSegment(
          segmentId: "s\(index)",
          speaker: 0,
          text: "word",
          start: Double(index),
          end: Double(index + 1)
        )
      ])
    }

    XCTAssertEqual(reducer.totalSegmentCount, 3)
    XCTAssertEqual(reducer.segments.map(\.segmentId), ["s1", "s2"])
  }
}

final class LocalASRRuntimeTests: XCTestCase {
  func testHelperContractRoundTripsFixtureSegments() throws {
    let request = LocalASRTranscriptionRequest(
      requestId: "fixture-1",
      audioPath: "/tmp/audio.pcm",
      language: "en",
      sampleRate: 16000,
      channels: 1,
      engine: .mlxWhisper,
      model: .small,
      fixtureSegments: [
        LocalASRTranscriptSegment(id: "seg-1", speaker: 0, text: "hello local", start: 0, end: 1)
      ]
    )

    let encoded = try JSONEncoder().encode(request)
    let decoded = try JSONDecoder().decode(LocalASRTranscriptionRequest.self, from: encoded)

    XCTAssertEqual(decoded, request)
  }

  func testDeterministicMergeDeduplicatesOverlappingChunksAndIsIdempotent() {
    var merger = LocalTranscriptMerger()
    let first = LocalASRTranscriptSegment(
      id: nil,
      speaker: 0,
      text: "hello local whisper",
      start: 0.0,
      end: 2.0
    ).normalized()
    let duplicate = LocalASRTranscriptSegment(
      id: nil,
      speaker: 0,
      text: "hello  local whisper",
      start: 0.1,
      end: 2.1
    ).normalized()
    let next = LocalASRTranscriptSegment(
      id: "s2",
      speaker: 0,
      text: "next segment",
      start: 2.2,
      end: 3.0
    ).normalized()

    XCTAssertEqual(
      merger.merge([first, next]).map(\.text), ["hello local whisper", "next segment"])
    XCTAssertEqual(
      merger.merge([duplicate, next]).map(\.text), ["hello local whisper", "next segment"])
    XCTAssertEqual(merger.merge([first, next]).count, 2)
  }

  func testDeterministicMergeCombinesPartialOverlapByTokenBoundary() {
    var merger = LocalTranscriptMerger()
    let first = LocalASRTranscriptSegment(
      id: "chunk-1",
      speaker: 0,
      text: "hello local whisper",
      start: 0.0,
      end: 2.0
    ).normalized()
    let second = LocalASRTranscriptSegment(
      id: "chunk-2",
      speaker: 0,
      text: "whisper works offline",
      start: 1.8,
      end: 3.2
    ).normalized()

    let result = merger.merge([first, second])

    XCTAssertEqual(result.count, 1)
    XCTAssertEqual(result[0].text, "hello local whisper works offline")
    XCTAssertEqual(result[0].start, 0.0)
    XCTAssertEqual(result[0].end, 3.2)
  }

  func testLocalBatchTranscriberWritesPCMAndNormalizesMergedSegments() async throws {
    var capturedRequest: LocalASRTranscriptionRequest?
    let tempDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "LocalASRRuntimeTests-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(
      at: tempDirectory,
      withIntermediateDirectories: true
    )
    defer { try? FileManager.default.removeItem(at: tempDirectory) }

    let transcriber = LocalASRBatchTranscriber(
      requestHandler: { request in
        capturedRequest = request
        XCTAssertTrue(FileManager.default.fileExists(atPath: request.audioPath))
        return LocalASRTranscriptionResponse(
          requestId: request.requestId,
          engine: request.engine,
          model: request.model,
          language: request.language,
          segments: [
            LocalASRTranscriptSegment(
              id: "a",
              speaker: 0,
              text: "hello local",
              start: 0,
              end: 1
            ),
            LocalASRTranscriptSegment(
              id: "b",
              speaker: 0,
              text: "local whisper",
              start: 0.9,
              end: 2
            ),
          ],
          fixture: true
        )
      },
      temporaryDirectory: tempDirectory,
      makeRequestId: { "req-1" }
    )

    let result = try await transcriber.transcribe(
      audioData: Data([1, 2, 3]),
      language: "en",
      plan: LocalTranscriptionPlan(engine: .mlxWhisper, model: .small, quality: .balanced)
    )

    XCTAssertEqual(
      capturedRequest?.audioPath, tempDirectory.appendingPathComponent("req-1.pcm").path)
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: tempDirectory.appendingPathComponent("req-1.pcm").path)
    )
    XCTAssertEqual(result.map(\.text), ["hello local whisper"])
  }

  func testBackgroundChunkerUsesSilenceBoundaryAndOverlap() {
    var chunker = LocalBackgroundAudioChunker(
      configuration: LocalBackgroundChunkerConfiguration(
        sampleRate: 10,
        bytesPerSample: 2,
        maxChunkDuration: 1.0,
        minChunkDuration: 0.4,
        overlapDuration: 0.2,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 2,
        maxPendingChunks: 4
      )
    )
    let samples: [Int16] = [20, 20, 20, 20, 0, 0, 20, 20, 20, 20, 20, 20]

    let chunks = chunker.append(pcmData: pcm(samples), startTime: 3.0)
    let final = chunker.flush()

    XCTAssertEqual(chunks.count, 1)
    XCTAssertEqual(chunks[0].sequence, 0)
    XCTAssertEqual(chunks[0].startTime, 3.0, accuracy: 0.001)
    XCTAssertEqual(chunks[0].endTime, 3.6, accuracy: 0.001)
    XCTAssertLessThanOrEqual(chunks[0].duration, 1.0)
    let finalChunk = tryUnwrap(final.first)
    XCTAssertEqual(finalChunk.startTime, 3.4, accuracy: 0.001)
    XCTAssertEqual(tryUnwrap(finalChunk.overlappedStartTime), 3.4, accuracy: 0.001)
  }

  func testBackgroundSessionAppliesBackpressureToPendingChunks() {
    let session = LocalBackgroundTranscriptionSession(
      language: "en",
      plan: LocalTranscriptionPlan(engine: .mlxWhisper, model: .small, quality: .balanced),
      configuration: LocalBackgroundChunkerConfiguration(
        sampleRate: 10,
        bytesPerSample: 2,
        maxChunkDuration: 1,
        minChunkDuration: 0.5,
        overlapDuration: 0,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 1,
        maxPendingChunks: 2
      ),
      requestHandler: { request in
        LocalASRTranscriptionResponse(
          requestId: request.requestId,
          engine: request.engine,
          model: request.model,
          language: request.language,
          segments: [],
          fixture: false
        )
      }
    )

    let result = session.append(pcmData: pcm(Array(repeating: 10, count: 31)), startTime: 0)

    XCTAssertEqual(result.enqueuedChunks.count, 3)
    XCTAssertEqual(result.droppedChunks.map(\.sequence), [0])
    XCTAssertEqual(result.pendingChunkCount, 2)
    XCTAssertEqual(session.droppedChunkCount, 1)
  }

  func testBackgroundSessionRemapsRawChunkResultsAndMergesOverlap() async throws {
    var capturedRequests: [LocalASRTranscriptionRequest] = []
    var dates = [
      Date(timeIntervalSince1970: 10),
      Date(timeIntervalSince1970: 10.25),
      Date(timeIntervalSince1970: 11),
      Date(timeIntervalSince1970: 11.5),
    ]
    let tempDirectory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "LocalBackgroundSessionTests-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDirectory) }

    let session = LocalBackgroundTranscriptionSession(
      language: "en",
      plan: LocalTranscriptionPlan(engine: .mlxWhisper, model: .small, quality: .balanced),
      configuration: LocalBackgroundChunkerConfiguration(
        sampleRate: 10,
        bytesPerSample: 2,
        maxChunkDuration: 1,
        minChunkDuration: 0.5,
        overlapDuration: 0.2,
        silenceWindowDuration: 0.2,
        silenceAmplitudeThreshold: 1,
        maxPendingChunks: 4
      ),
      requestHandler: { request in
        capturedRequests.append(request)
        XCTAssertTrue(FileManager.default.fileExists(atPath: request.audioPath))
        let sequence = capturedRequests.count - 1
        let segments: [LocalASRTranscriptSegment]
        if sequence == 0 {
          segments = [
            LocalASRTranscriptSegment(
              id: nil,
              speaker: 0,
              text: "hello local whisper",
              start: 0,
              end: 1.0
            )
          ]
        } else {
          segments = [
            LocalASRTranscriptSegment(
              id: nil,
              speaker: 0,
              text: "whisper runs here",
              start: 0.0,
              end: 0.9
            )
          ]
        }
        return LocalASRTranscriptionResponse(
          requestId: request.requestId,
          engine: request.engine,
          model: request.model,
          language: request.language,
          segments: segments,
          fixture: false
        )
      },
      temporaryDirectory: tempDirectory,
      makeRequestId: {
        "background-\(capturedRequests.count)"
      },
      now: {
        dates.removeFirst()
      }
    )

    _ = session.append(pcmData: pcm(Array(repeating: 10, count: 17)), startTime: 5)
    _ = session.finishInput()
    let results = try await session.transcribePending()
    let snapshot = session.snapshot()

    XCTAssertEqual(results.count, 2)
    XCTAssertEqual(results[0].remappedSegments[0].start, 5.0, accuracy: 0.001)
    XCTAssertEqual(results[1].chunk.startTime, 5.8, accuracy: 0.001)
    XCTAssertEqual(results[1].remappedSegments[0].start, 5.8, accuracy: 0.001)
    XCTAssertEqual(results[0].latencySeconds, 0.25, accuracy: 0.001)
    XCTAssertEqual(snapshot.rawChunkResults.count, 2)
    XCTAssertEqual(snapshot.joinedTranscript, "hello local whisper runs here")
    XCTAssertEqual(capturedRequests.map(\.sampleRate), [10, 10])
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: tempDirectory.appendingPathComponent("background-0.pcm").path)
    )
  }

  func testBackgroundPipelineCanExerciseRealHelperWhenRuntimeAvailable() async throws {
    guard let helperURL = LocalASRHelperLocator.defaultExecutableURL() else {
      throw XCTSkip("Local ASR helper executable is not available")
    }
    let engines = LocalASRHelperLocator.detectedEngines(executableURL: helperURL)
    guard let engine = engines.first else {
      throw XCTSkip("No real local ASR engine/model is available")
    }

    let session = LocalBackgroundTranscriptionSession(
      language: "en",
      plan: LocalTranscriptionPlan(engine: engine, model: .base, quality: .fast),
      configuration: LocalBackgroundChunkerConfiguration(
        maxChunkDuration: 0.5,
        minChunkDuration: 0.25,
        overlapDuration: 0,
        maxPendingChunks: 2
      ),
      executableURL: helperURL,
      timeoutSeconds: 20
    )

    _ = session.append(pcmData: pcm(Array(repeating: 0, count: 16000)), startTime: 0)
    _ = session.finishInput()
    let results = try await session.transcribePending()

    XCTAssertFalse(results.isEmpty)
    XCTAssertTrue(results.allSatisfy { !$0.response.fixture })
  }

  func testDetectedEnginesUsesHelperCapabilityProbe() throws {
    let helper = try makeExecutableHelper(
      body:
        #"printf '{"engines":[{"engine":"mlx-whisper","available":true},{"engine":"faster-whisper","available":false,"reason":"missing model"}]}'"#
    )

    let engines = LocalASRHelperLocator.detectedEngines(executableURL: helper)

    XCTAssertEqual(engines, [.mlxWhisper])
  }

  func testDetectedEnginesReturnsEmptyOnProbeFailure() throws {
    let helper = try makeExecutableHelper(body: "exit 2")

    let engines = LocalASRHelperLocator.detectedEngines(executableURL: helper)

    XCTAssertTrue(engines.isEmpty)
  }

  private func makeExecutableHelper(body: String) throws -> URL {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "LocalASRHelperLocatorTests-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let helper = directory.appendingPathComponent("local-asr-helper")
    let script = "#!/bin/sh\n\(body)\n"
    try script.write(to: helper, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o755],
      ofItemAtPath: helper.path
    )
    addTeardownBlock {
      try? FileManager.default.removeItem(at: directory)
    }
    return helper
  }

  private func pcm(_ samples: [Int16]) -> Data {
    samples.withUnsafeBufferPointer { Data(buffer: $0) }
  }

  private func tryUnwrap<T>(_ value: T?, file: StaticString = #filePath, line: UInt = #line) -> T {
    guard let value else {
      XCTFail("Expected non-nil value", file: file, line: line)
      fatalError("Expected non-nil value")
    }
    return value
  }
}

final class PTTBatchTranscriptionRouterTests: XCTestCase {
  func testLocalProviderUsesHelperPathAndDoesNotCallCloud() async throws {
    var cloudCalls = 0
    var localPlan: LocalTranscriptionPlan?
    let router = PTTBatchTranscriptionRouter(
      selection: { TranscriptionProviderSelection(mode: .local, quality: .balanced) },
      capabilities: {
        LocalTranscriptionCapabilities(
          processor: .nativeAppleSilicon,
          physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
          availableEngines: [.mlxWhisper]
        )
      },
      cloudTranscribe: { _, _, _ in
        cloudCalls += 1
        return "cloud transcript"
      },
      localTranscribe: { _, _, plan in
        localPlan = plan
        return [
          LocalASRTranscriptSegment(
            id: "local-1",
            speaker: 0,
            text: "local transcript",
            start: 0,
            end: 1
          ).normalized()
        ]
      }
    )

    let result = try await router.transcribe(
      audioData: Data([1]),
      language: "en",
      contextKeywords: ["Omi"]
    )

    XCTAssertEqual(result.provider, .local)
    XCTAssertEqual(result.transcript, "local transcript")
    XCTAssertEqual(localPlan?.engine, .mlxWhisper)
    XCTAssertEqual(cloudCalls, 0)
  }

  func testCloudProviderKeepsExistingBatchPath() async throws {
    var localCalls = 0
    var capturedKeywords: [String] = []
    let router = PTTBatchTranscriptionRouter(
      selection: { TranscriptionProviderSelection(mode: .cloud, quality: .auto) },
      capabilities: {
        LocalTranscriptionCapabilities(
          processor: .nativeAppleSilicon,
          physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
          availableEngines: [.mlxWhisper]
        )
      },
      cloudTranscribe: { _, _, keywords in
        capturedKeywords = keywords
        return "cloud transcript"
      },
      localTranscribe: { _, _, _ in
        localCalls += 1
        return []
      }
    )

    let result = try await router.transcribe(
      audioData: Data([1]),
      language: "en",
      contextKeywords: ["keyword"]
    )

    XCTAssertEqual(result.provider, .cloud)
    XCTAssertEqual(result.transcript, "cloud transcript")
    XCTAssertEqual(capturedKeywords, ["keyword"])
    XCTAssertEqual(localCalls, 0)
  }

  func testExplicitLocalWithoutEngineDoesNotCallCloud() async {
    var cloudCalls = 0
    let router = PTTBatchTranscriptionRouter(
      selection: { TranscriptionProviderSelection(mode: .local, quality: .auto) },
      capabilities: {
        LocalTranscriptionCapabilities(
          processor: .nativeAppleSilicon,
          physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
          availableEngines: []
        )
      },
      cloudTranscribe: { _, _, _ in
        cloudCalls += 1
        return "cloud transcript"
      },
      localTranscribe: { _, _, _ in [] }
    )

    do {
      _ = try await router.transcribe(
        audioData: Data([1]),
        language: "en",
        contextKeywords: []
      )
      XCTFail("Expected explicit local mode without an engine to fail")
    } catch {
      XCTAssertEqual(cloudCalls, 0)
      XCTAssertTrue(error.localizedDescription.contains("No local transcription engine"))
    }
  }
}

final class BackgroundTranscriptionRoutingGuardTests: XCTestCase {
  func testAutoCloudFallbackAllowsBackgroundCloud() {
    let decision = BackgroundTranscriptionRoutingGuard().decide(
      selection: TranscriptionProviderSelection(mode: .auto, quality: .auto),
      capabilities: LocalTranscriptionCapabilities(
        processor: .intel,
        physicalMemoryBytes: 8 * 1024 * 1024 * 1024,
        availableEngines: []
      )
    )

    XCTAssertTrue(decision.useCloudBackend)
    XCTAssertNotNil(decision.unsupportedLocalReason)
    XCTAssertNil(decision.localPlan)
  }

  func testResolvedLocalBackgroundRoutesToLocalWhisperAndNotCloudListen() {
    let decision = BackgroundTranscriptionRoutingGuard().decide(
      selection: TranscriptionProviderSelection(mode: .local, quality: .balanced),
      capabilities: LocalTranscriptionCapabilities(
        processor: .nativeAppleSilicon,
        physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
        availableEngines: [.mlxWhisper]
      )
    )

    XCTAssertFalse(decision.useCloudBackend)
    XCTAssertEqual(decision.localPlan?.engine, .mlxWhisper)
    XCTAssertNil(decision.unsupportedLocalReason)
  }

  func testAutoResolvedLocalBackgroundRoutesToLocalWhisperAndNotCloudListen() {
    let decision = BackgroundTranscriptionRoutingGuard().decide(
      selection: TranscriptionProviderSelection(mode: .auto, quality: .balanced),
      capabilities: LocalTranscriptionCapabilities(
        processor: .nativeAppleSilicon,
        physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
        availableEngines: [.mlxWhisper]
      )
    )

    XCTAssertFalse(decision.useCloudBackend)
    XCTAssertEqual(decision.localPlan?.engine, .mlxWhisper)
    XCTAssertNil(decision.unsupportedLocalReason)
  }

  func testExplicitLocalWithoutEngineDoesNotSilentlyUseCloudForBackground() {
    let decision = BackgroundTranscriptionRoutingGuard().decide(
      selection: TranscriptionProviderSelection(mode: .local, quality: .balanced),
      capabilities: LocalTranscriptionCapabilities(
        processor: .nativeAppleSilicon,
        physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
        availableEngines: []
      )
    )

    XCTAssertFalse(decision.useCloudBackend)
    XCTAssertEqual(decision.unsupportedLocalReason, "No local transcription engine is available")
    XCTAssertNil(decision.localPlan)
  }
}

final class TranscriptionProviderOnboardingAdvisorTests: XCTestCase {
  func testEligibleNativeAppleSiliconRecommendsLocalFirst() {
    let recommendation = TranscriptionProviderOnboardingAdvisor().recommendation(
      capabilities: LocalTranscriptionCapabilities(
        processor: .nativeAppleSilicon,
        physicalMemoryBytes: 16 * 1024 * 1024 * 1024,
        availableEngines: [.mlxWhisper, .fasterWhisper]
      )
    )

    XCTAssertTrue(recommendation.canRecommendLocal)
    XCTAssertEqual(recommendation.recommendedSelection.mode, .auto)
    XCTAssertTrue(recommendation.detail.contains("Continuous background transcription"))
    XCTAssertFalse(recommendation.detail.contains("still requires cloud transcription"))
    XCTAssertTrue(recommendation.status.contains("MLX Whisper"))
  }

  func testUnavailableLocalEngineRecommendsCloudFallback() {
    let recommendation = TranscriptionProviderOnboardingAdvisor().recommendation(
      capabilities: LocalTranscriptionCapabilities(
        processor: .intel,
        physicalMemoryBytes: 8 * 1024 * 1024 * 1024,
        availableEngines: []
      )
    )

    XCTAssertFalse(recommendation.canRecommendLocal)
    XCTAssertEqual(recommendation.recommendedSelection.mode, .cloud)
    XCTAssertTrue(recommendation.detail.contains("continuous background capture"))
    XCTAssertTrue(recommendation.status.contains("cloud"))
  }
}

final class PTTTranscriptPostProcessorTests: XCTestCase {
  func testLocalModeBypassesLLMCleanup() async {
    var cleanupCalls = 0
    let result = await PTTTranscriptPostProcessor.process(
      "raw local transcript",
      keywords: ["Omi"],
      provider: .local,
      cleanup: { transcript, _ in
        cleanupCalls += 1
        return "\(transcript) cleaned"
      }
    )

    XCTAssertEqual(result, "raw local transcript")
    XCTAssertEqual(cleanupCalls, 0)
  }

  func testCloudModeUsesCleanup() async {
    let result = await PTTTranscriptPostProcessor.process(
      "raw cloud transcript",
      keywords: [],
      provider: .cloud,
      cleanup: { transcript, _ in "\(transcript) cleaned" }
    )

    XCTAssertEqual(result, "raw cloud transcript cleaned")
  }
}
