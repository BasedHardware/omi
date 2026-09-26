import Foundation
import XCTest

@testable import Omi_Computer

/// `ServerConversation.durationInSeconds` reports the transcript span, not the
/// live-socket wall window.
///
/// `started_at` is the streaming-session origin, so `finished_at - started_at`
/// over-counts by however long the socket had already been open: on 2026-09-07 an
/// 8-second dictation scrap read as 42m45s in the macOS row while mobile showed 8s
/// (#4056). The vectors below mirror the Flutter suite
/// (`app/test/unit/conversation_duration_test.dart`) and the shared parity fixture
/// (`contracts/parity/conversation_duration.json`).
final class ConversationDurationTests: XCTestCase {

  // MARK: - Fixtures

  /// Built through the wire adapter rather than JSON so a non-finite bound can
  /// be expressed at all (JSON has no infinity).
  private func segments(_ specs: [(text: String, start: Double, end: Double)])
    -> [TranscriptSegment]
  {
    specs.enumerated().map { index, spec in
      TranscriptSegment(
        OmiAPI.TranscriptSegment(
          end: spec.end,
          id: "seg-\(index)",
          isUser: true,
          speaker: "SPEAKER_00",
          start: spec.start,
          text: spec.text
        ))
    }
  }

  private func conversation(
    segments: [TranscriptSegment] = [],
    startedAt: Date? = nil,
    finishedAt: Date? = nil
  ) -> ServerConversation {
    ServerConversation(
      id: "conversation-duration",
      createdAt: startedAt ?? Date(timeIntervalSince1970: 1_757_287_953),
      updatedAt: nil,
      startedAt: startedAt,
      finishedAt: finishedAt,
      structured: Structured(
        title: "Title", overview: "", emoji: "💬", category: "other", actionItems: [], events: []),
      transcriptSegments: segments,
      transcriptSegmentsIncluded: !segments.isEmpty,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }

  /// Astra's Cost, 2026-09-07: started_at 23:32:33, finished_at 00:15:18.
  private let sessionOrigin = Date(timeIntervalSince1970: 1_757_287_953)
  private var wallWindowEnd: Date { sessionOrigin.addingTimeInterval(2565) }

  // MARK: - Transcript span

  func testUsesTheTranscriptSpanRatherThanTheInflatedSessionWindow() throws {
    let conversation = conversation(
      segments: segments([(text: "how much does astra cost", start: 0, end: 8)]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, 8)
    XCTAssertEqual(conversation.formattedDuration, "8s")
  }

  func testSpanIsTheMaximumEndNotTheLastSegment() throws {
    let conversation = conversation(
      segments: segments([
        (text: "second half of the sentence", start: 8, end: 27),
        (text: "first half", start: 0, end: 8),
      ]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, 27)
  }

  func testSpanWinsEvenWhenItExceedsTheWallWindow() throws {
    let conversation = conversation(
      segments: segments([(text: "still talking", start: 0, end: 90)]),
      startedAt: sessionOrigin,
      finishedAt: sessionOrigin.addingTimeInterval(30)
    )

    XCTAssertEqual(conversation.durationInSeconds, 90)
  }

  func testSegmentsWithoutTimestampsStillReportTheSpan() throws {
    let conversation = conversation(segments: segments([(text: "hello", start: 0, end: 15)]))

    XCTAssertEqual(conversation.durationInSeconds, 15)
  }

  func testAZeroLengthTranscriptReportsZeroRatherThanTheWallWindow() throws {
    let conversation = conversation(
      segments: segments([(text: "hm", start: 0, end: 0)]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, 0)
  }

  // MARK: - Segment validation

  func testBlankTextSegmentsDoNotExtendTheSpan() throws {
    let conversation = conversation(
      segments: segments([
        (text: "the only speech", start: 0, end: 8),
        (text: "   ", start: 0, end: 2565),
      ]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, 8)
  }

  func testReversedAndNonFiniteIntervalsAreIgnored() throws {
    let conversation = conversation(
      segments: segments([
        (text: "good", start: 0, end: 8),
        (text: "reversed", start: 3000, end: 12),
        (text: "infinite", start: 0, end: .infinity),
      ]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, 8)
  }

  func testANegativeIntervalClampsToZeroRatherThanGoingBackwards() throws {
    let conversation = conversation(
      segments: segments([(text: "before the origin", start: -9, end: -4)]))

    XCTAssertEqual(conversation.durationInSeconds, 0)
  }

  func testAFiniteOutOfRangeEndClampsToMaxIntInsteadOfTrapping() throws {
    // isFinite alone does not bound the value: a malformed persisted segment
    // can carry a finite end beyond Int.max, where Int(Double) would trap.
    let conversation = conversation(
      segments: segments([(text: "corrupt", start: 0, end: .greatestFiniteMagnitude)]),
      startedAt: sessionOrigin,
      finishedAt: wallWindowEnd
    )

    XCTAssertEqual(conversation.durationInSeconds, Int.max)
  }

  func testSegmentsThatAllFailValidationFallBackToTheWallWindow() throws {
    let conversation = conversation(
      segments: segments([(text: "  ", start: 0, end: 8)]),
      startedAt: sessionOrigin,
      finishedAt: sessionOrigin.addingTimeInterval(90)
    )

    XCTAssertEqual(conversation.durationInSeconds, 90)
  }

  // MARK: - Wall-window fallback

  func testATranscriptFreeRecordUsesTheWallWindow() {
    let conversation = conversation(
      startedAt: sessionOrigin, finishedAt: sessionOrigin.addingTimeInterval(45))

    XCTAssertEqual(conversation.durationInSeconds, 45)
  }

  func testAReversedWallWindowClampsToZero() {
    let conversation = conversation(
      startedAt: sessionOrigin, finishedAt: sessionOrigin.addingTimeInterval(-45))

    XCTAssertEqual(conversation.durationInSeconds, 0)
  }

  func testNeitherSegmentsNorBothTimestampsReportsZero() {
    XCTAssertEqual(conversation().durationInSeconds, 0)
    XCTAssertEqual(conversation(startedAt: sessionOrigin).durationInSeconds, 0)
  }

  // MARK: - Shared parity vectors

  func testSharedDurationContractVectors() throws {
    let testFile = URL(fileURLWithPath: #filePath)
    let repositoryRoot =
      testFile
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let fixtureURL =
      repositoryRoot
      .appendingPathComponent("contracts/parity/conversation_duration.json")
    let fixture =
      try JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
    let cases = try XCTUnwrap(fixture?["cases"] as? [[String: Any]])
    XCTAssertFalse(cases.isEmpty)

    let formatter = ISO8601DateFormatter()
    for testCase in cases {
      let name = try XCTUnwrap(testCase["name"] as? String)
      let specs = try XCTUnwrap(testCase["segments"] as? [[String: Any]])
      let decoded = try JSONDecoder().decode(
        [TranscriptSegment].self, from: JSONSerialization.data(withJSONObject: specs))
      let conversation = conversation(
        segments: decoded,
        startedAt: (testCase["started_at"] as? String).flatMap(formatter.date(from:)),
        finishedAt: (testCase["finished_at"] as? String).flatMap(formatter.date(from:))
      )

      let expected = try XCTUnwrap(testCase["expected_seconds"] as? Int)
      XCTAssertEqual(conversation.durationInSeconds, expected, "parity case \(name)")
    }
  }
}
