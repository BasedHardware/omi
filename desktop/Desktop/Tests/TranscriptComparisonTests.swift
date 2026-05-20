import XCTest

@testable import Omi_Computer

final class TranscriptComparisonTests: XCTestCase {
  func testNormalizationRemovesCasePunctuationAndRepeatedWhitespace() {
    XCTAssertEqual(
      TranscriptComparison.normalizedText(" Hello,   LOCAL Whisper! "),
      "hello local whisper"
    )
  }

  func testWordErrorRateCountsSubstitutionInsertionAndDeletion() {
    XCTAssertEqual(
      TranscriptComparison.wordErrorRate(
        reference: "hello local whisper",
        hypothesis: "hello cloud whisper now"
      ),
      2.0 / 3.0,
      accuracy: 0.0001
    )
  }

  func testCharacterErrorRateUsesNormalizedCharactersWithoutSpaces() {
    XCTAssertEqual(
      TranscriptComparison.characterErrorRate(reference: "abc def", hypothesis: "abc dxf"),
      1.0 / 6.0,
      accuracy: 0.0001
    )
  }

  func testEmptyReferenceScoringIsBounded() {
    XCTAssertEqual(TranscriptComparison.wordErrorRate(reference: "", hypothesis: ""), 0)
    XCTAssertEqual(TranscriptComparison.wordErrorRate(reference: "", hypothesis: "extra"), 1)
  }
}
