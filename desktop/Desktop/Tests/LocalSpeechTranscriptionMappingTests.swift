import XCTest

@testable import Omi_Computer

final class LocalSpeechTranscriptionMappingTests: XCTestCase {

  func testHybridRollingSegmentsMatchTranscriptionStorageContract() {
    let segments = LocalSpeechTranscriptionAdapter.makeHybridRollingSegments(
      text: "hello world",
      elapsedSeconds: 12.5
    )
    XCTAssertEqual(segments.count, 1)
    let segment = segments[0]
    XCTAssertEqual(segment.id, LocalSpeechTranscriptionAdapter.pseudoBackendSegmentId)
    XCTAssertEqual(segment.text, "hello world")
    XCTAssertEqual(segment.speaker, "SPEAKER_00")
    XCTAssertEqual(segment.speaker_id, 0)
    XCTAssertTrue(segment.is_user)
    XCTAssertNil(segment.person_id)
    XCTAssertEqual(segment.start, 0)
    XCTAssertEqual(segment.end, 12.5)
    XCTAssertNil(segment.translations)
  }

  func testNormalizedLocaleIdentifierHandlesMultiAndTwoLetterCodes() {
    let multi = LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(
      forAssistantLanguageCode: "multi")
    XCTAssertFalse(multi.isEmpty)

    let uk = LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(
      forAssistantLanguageCode: "uk")
    XCTAssertTrue(uk.lowercased().contains("uk"))

    let zh = LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(
      forAssistantLanguageCode: "zh")
    XCTAssertTrue(zh.lowercased().contains("zh"))
  }
}
