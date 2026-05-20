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

  @MainActor
  func testComparisonHarnessGroupsProviderOutputByTimeBucket() throws {
    var snapshots: [TranscriptionComparisonHarnessSnapshot] = []
    let harness = TranscriptionComparisonHarness(
      language: "en",
      deepgramAPIKey: nil,
      onSnapshot: { snapshots.append($0) }
    )

    harness.appendWhisperSegments([
      segment(id: "w1", text: "first whisper window", start: 2, end: 4),
      segment(id: "w2", text: "second whisper window", start: 35, end: 38),
    ])
    harness.appendDeepgramSegmentsForTesting([
      segment(id: "d1", text: "first deepgram window", start: 3, end: 5),
      segment(id: "d2", text: "second deepgram window", start: 36, end: 39),
    ])

    let buckets = try XCTUnwrap(snapshots.last?.timeBuckets)
    XCTAssertEqual(buckets.count, 2)
    XCTAssertEqual(buckets[0].startTime, 0, accuracy: 0.001)
    XCTAssertEqual(buckets[0].endTime, 30, accuracy: 0.001)
    XCTAssertEqual(buckets[0].whisperText, "first whisper window")
    XCTAssertEqual(buckets[0].deepgramText, "first deepgram window")
    XCTAssertEqual(buckets[1].startTime, 30, accuracy: 0.001)
    XCTAssertEqual(buckets[1].whisperText, "second whisper window")
    XCTAssertEqual(buckets[1].deepgramText, "second deepgram window")
  }

  @MainActor
  func testComparisonHarnessScoresFullTranscriptWhenPreviewIsTruncated() throws {
    var snapshots: [TranscriptionComparisonHarnessSnapshot] = []
    let harness = TranscriptionComparisonHarness(
      language: "en",
      deepgramAPIKey: nil,
      onSnapshot: { snapshots.append($0) }
    )
    let previewPadding = String(repeating: ".", count: 13_000)
    let whisperText = "wrong \(previewPadding) same"
    let deepgramText = "right \(previewPadding) same"

    harness.appendWhisperSegments([segment(id: "w-long", text: whisperText, start: 0, end: 1)])
    harness.appendDeepgramSegmentsForTesting([
      segment(id: "d-long", text: deepgramText, start: 0, end: 1)
    ])

    let snapshot = try XCTUnwrap(snapshots.last)
    XCTAssertLessThan(snapshot.whisper.transcript.count, whisperText.count)
    XCTAssertEqual(snapshot.whisper.wordCount, 2)
    XCTAssertEqual(try XCTUnwrap(snapshot.wordDifferenceRate), 0.5, accuracy: 0.0001)
  }

  private func segment(id: String, text: String, start: Double, end: Double)
    -> NormalizedTranscriptSegment
  {
    NormalizedTranscriptSegment(
      segmentId: id,
      speaker: 0,
      speakerLabel: nil,
      text: text,
      start: start,
      end: end,
      isUser: true,
      personId: nil,
      translations: []
    )
  }
}
