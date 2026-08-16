import XCTest

@testable import Omi_Computer

final class LocalTranscriptionDuplicatePolicyTests: XCTestCase {
  private func segment(
    text: String,
    isUser: Bool,
    start: Double = 0,
    end: Double = 10,
    id: String? = UUID().uuidString
  ) -> SpeakerSegment {
    SpeakerSegment(
      segmentId: id,
      speaker: isUser ? 0 : 1,
      text: text,
      start: start,
      end: end,
      isUser: isUser
    )
  }

  func testExactOverlappingPlaybackReturnsSourceAwareDecision() {
    let mic = segment(text: "This is the video transcript", isUser: true, id: "mic")
    let system = segment(text: "This is the video transcript.", isUser: false, id: "system")

    XCTAssertEqual(
      LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]),
      .suppressIncoming
    )
    XCTAssertEqual(
      LocalTranscriptionDuplicatePolicy.decision(for: system, existing: [mic]),
      .replaceExisting(segmentId: "mic")
    )
  }

  func testIdenticalWordsOutsideTimingWindowAreKept() {
    let mic = segment(text: "This is the video transcript", isUser: true, start: 0, end: 2)
    let system = segment(text: "This is the video transcript", isUser: false, start: 4, end: 6)

    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }

  func testFuzzyTextIsNotSuppressed() {
    let mic = segment(text: "This is the video transcript", isUser: true)
    let system = segment(text: "This is a video transcript", isUser: false)

    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }

  func testShortAcknowledgementIsNotSuppressed() {
    let mic = segment(text: "Yes okay", isUser: true)
    let system = segment(text: "Yes, okay", isUser: false)

    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }

  func testSameSourceSpeechIsNeverSuppressed() {
    let first = segment(text: "This is the video transcript", isUser: true)
    let second = segment(text: "This is the video transcript", isUser: true)

    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: second, existing: [first]), .accept)
  }
}
