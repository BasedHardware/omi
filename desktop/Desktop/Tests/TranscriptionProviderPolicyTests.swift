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
    XCTAssertNil(result.fallbackReason)
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
