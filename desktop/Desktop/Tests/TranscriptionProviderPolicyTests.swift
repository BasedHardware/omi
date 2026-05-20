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
