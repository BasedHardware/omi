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

  @MainActor
  func testComparisonHarnessPublishesWhisperSnapshotWithoutDeepgramKey() {
    var snapshots: [TranscriptionComparisonHarnessSnapshot] = []
    let harness = TranscriptionComparisonHarness(
      language: "en",
      deepgramAPIKey: nil,
      onSnapshot: { snapshots.append($0) }
    )

    harness.start()
    harness.appendWhisperSegments([
      NormalizedTranscriptSegment(
        segmentId: "whisper-1",
        speaker: 0,
        speakerLabel: nil,
        text: "hello local whisper",
        start: 0,
        end: 1,
        isUser: true,
        personId: nil,
        translations: []
      )
    ])

    let snapshot = try! XCTUnwrap(snapshots.last)
    XCTAssertTrue(snapshot.isRunning)
    XCTAssertEqual(snapshot.whisper.transcript, "hello local whisper")
    XCTAssertEqual(snapshot.whisper.wordCount, 3)
    XCTAssertEqual(snapshot.deepgram.status, "Missing Deepgram API key")
    XCTAssertNotNil(snapshot.deepgram.error)
    XCTAssertNil(snapshot.wordDifferenceRate)
  }
}
