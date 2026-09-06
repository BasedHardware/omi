import XCTest

@testable import Omi_Computer

/// Clock rules and provisional-title derivation for a processing row.
final class ConversationProcessingProgressTests: XCTestCase {
  private let base = Date(timeIntervalSince1970: 1_700_000_000)

  private func conversation(
    createdAt: Date,
    finishedAt: Date?,
    segments: [TranscriptSegment] = []
  ) -> ServerConversation {
    ServerConversation(
      id: "c",
      createdAt: createdAt,
      updatedAt: nil,
      startedAt: nil,
      finishedAt: finishedAt,
      structured: Structured(title: "", overview: "", emoji: "", category: "", actionItems: [], events: []),
      transcriptSegments: segments,
      transcriptSegmentsIncluded: !segments.isEmpty,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: nil,
      status: .processing,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil
    )
  }

  private func segment(_ text: String) -> TranscriptSegment {
    TranscriptSegment(
      id: UUID().uuidString, text: text, speaker: "SPEAKER_00", isUser: false, personId: nil, start: 0, end: 1)
  }

  // MARK: - Phase thresholds

  func test_phaseBoundaries() {
    XCTAssertEqual(ConversationProcessingProgress.phase(elapsed: 0), .summarizing)
    XCTAssertEqual(ConversationProcessingProgress.phase(elapsed: 119), .summarizing)
    XCTAssertEqual(ConversationProcessingProgress.phase(elapsed: 120), .slow)
    XCTAssertEqual(ConversationProcessingProgress.phase(elapsed: 599), .slow)
    XCTAssertEqual(ConversationProcessingProgress.phase(elapsed: 600), .stalled)
  }

  func test_elapsedCountsFromRecordingEnd_notRowCreation() {
    // A 40-minute meeting: created when it started, finished 40 minutes later.
    let created = base
    let finished = base.addingTimeInterval(40 * 60)
    let conv = conversation(createdAt: created, finishedAt: finished)
    let now = finished.addingTimeInterval(30)
    XCTAssertEqual(ConversationProcessingProgress.elapsed(for: conv, now: now), 30)
    XCTAssertEqual(ConversationProcessingProgress.phase(for: conv, now: now), .summarizing)
  }

  func test_elapsedFallsBackToCreatedAt_whenNoFinishedAt() {
    let conv = conversation(createdAt: base, finishedAt: nil)
    XCTAssertEqual(ConversationProcessingProgress.phase(for: conv, now: base.addingTimeInterval(700)), .stalled)
  }

  func test_elapsedNeverNegative() {
    let conv = conversation(createdAt: base, finishedAt: base.addingTimeInterval(60))
    XCTAssertEqual(ConversationProcessingProgress.elapsed(for: conv, now: base), 0)
  }

  // MARK: - Provisional title

  func test_provisionalTitle_skipsShortSegments_capitalises() {
    let title = ConversationProcessingProgress.provisionalTitle(from: [
      segment("um"),
      segment("ok yeah"),
      segment("so the plan for the launch is to ship on friday"),
    ])
    XCTAssertEqual(title, "So the plan for the launch is to ship on friday")
  }

  func test_provisionalTitle_truncatesAtWordBoundary_withEllipsis() {
    let long = "we should talk about the quarterly numbers before the board meeting on thursday afternoon"
    guard let title = ConversationProcessingProgress.provisionalTitle(from: [segment(long)]) else {
      return XCTFail("Expected a provisional title")
    }
    XCTAssertTrue(title.hasSuffix("…"))
    XCTAssertLessThanOrEqual(title.count, ConversationProcessingProgress.provisionalTitleMaxLength + 1)
    XCTAssertFalse(title.dropLast().hasSuffix(" "), "Truncation must end on a whole word")
    XCTAssertTrue(long.hasPrefix(String(title.dropLast()).lowercased()))
  }

  func test_provisionalTitle_stripsTrailingPunctuationBeforeEllipsis() {
    let text = "alright, let us start with the first item on the agenda, which is hiring, and then budget"
    let title = ConversationProcessingProgress.provisionalTitle(from: [segment(text)]) ?? ""
    XCTAssertFalse(title.isEmpty)
    XCTAssertFalse(title.contains(",…"))
  }

  func test_provisionalTitle_nilWhenNothingSubstantive() {
    XCTAssertNil(ConversationProcessingProgress.provisionalTitle(from: []))
    XCTAssertNil(ConversationProcessingProgress.provisionalTitle(from: [segment("hi there"), segment("yes")]))
  }
}
