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

  // MARK: - Rolling-window playback echoes

  private func hopperEchoText() -> (mic: String, system: String) {
    // Measured shape from the 2026-09-04 session: the mic lane re-transcribed a
    // mid-reply slice of the same playback the system-audio tap captured in full,
    // with recognizer noise at the fragment edges.
    (
      "place the iron ingot in the center slot then put planks",
      "To craft the hopper you will need one iron ingot and five wooden planks. "
        + "Place the iron ingot in the center slot, then put planks in the top left."
    )
  }

  func testPartialWindowEchoAcrossLanesIsSuppressed() {
    let (micText, systemText) = hopperEchoText()
    let mic = segment(text: micText, isUser: true, start: 1, end: 10)
    let system = segment(text: systemText, isUser: false, start: 0, end: 10)

    XCTAssertEqual(
      LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]),
      .suppressIncoming
    )
    XCTAssertEqual(
      LocalTranscriptionDuplicatePolicy.decision(for: system, existing: [mic]),
      .replaceExisting(segmentId: mic.segmentId ?? "")
    )
  }

  func testShortContainedRunIsNotSuppressed() {
    let mic = segment(
      text: "iron ingot in the center", isUser: true, start: 0, end: 10)
    let system = segment(
      text: "Place the iron ingot in the center slot, then put planks in the top left",
      isUser: false, start: 0, end: 10)

    // Four shared contiguous words sit below the containment floor: ordinary
    // conversational overlap, not playback bleed.
    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }

  func testContainedRunOutsideTimingWindowIsKept() {
    let (micText, systemText) = hopperEchoText()
    let mic = segment(text: micText, isUser: true, start: 0, end: 8)
    let system = segment(text: systemText, isUser: false, start: 12, end: 20)

    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }

  func testContainmentRequiresContiguousRun() {
    let mic = segment(
      text: "place the hopper then put planks around", isUser: true, start: 0, end: 10)
    let system = segment(
      text: "Place the iron ingot in the center slot, then put planks in the top left",
      isUser: false, start: 0, end: 10)

    // Same vocabulary scattered across different word order is not an echo.
    XCTAssertEqual(LocalTranscriptionDuplicatePolicy.decision(for: mic, existing: [system]), .accept)
  }
}
