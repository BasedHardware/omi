import XCTest

@testable import Omi_Computer

final class LiveTranscriptRenderPlanTests: XCTestCase {
  func testOnlyTheLatestSegmentIsLive() {
    let segments = [
      segment(id: "first", text: "first"),
      segment(id: "second", text: "second"),
      segment(id: "live", text: "still speaking"),
    ]

    XCTAssertEqual(
      LiveTranscriptRenderPlan.settledSegments(from: segments).map(\.id),
      ["first", "second"]
    )
    XCTAssertEqual(LiveTranscriptRenderPlan.liveSegment(from: segments)?.id, "live")
  }

  func testUpdatingLiveTextLeavesSettledSegmentsUntouched() {
    let initial = [
      segment(id: "first", text: "unchanged"),
      segment(id: "live", text: "partial"),
    ]
    let updated = [
      segment(id: "first", text: "unchanged"),
      segment(id: "live", text: "partial transcript completed"),
    ]

    XCTAssertEqual(
      LiveTranscriptRenderPlan.settledSegments(from: initial).map(\.text),
      LiveTranscriptRenderPlan.settledSegments(from: updated).map(\.text)
    )
    XCTAssertNotEqual(
      LiveTranscriptRenderPlan.liveSegment(from: initial)?.text,
      LiveTranscriptRenderPlan.liveSegment(from: updated)?.text
    )
  }

  func testEmptyTranscriptHasNoLiveSegment() {
    XCTAssertTrue(LiveTranscriptRenderPlan.settledSegments(from: []).isEmpty)
    XCTAssertNil(LiveTranscriptRenderPlan.liveSegment(from: []))
  }

  func testUnchangedSegmentCanReuseItsLayout() {
    let previous = segment(id: "first", text: "unchanged")
    let next = segment(id: "first", text: "unchanged")

    XCTAssertTrue(
      LiveTranscriptRenderPlan.canReuseSegmentLayout(
        previous: previous,
        next: next,
        previousSpeakerName: nil,
        nextSpeakerName: nil,
        previousHasTapAction: false,
        nextHasTapAction: false
      )
    )
  }

  func testChangedTranscriptTextInvalidatesOnlyThatSegmentLayout() {
    let previous = segment(id: "live", text: "partial")
    let next = segment(id: "live", text: "partial transcript completed")

    XCTAssertFalse(
      LiveTranscriptRenderPlan.canReuseSegmentLayout(
        previous: previous,
        next: next,
        previousSpeakerName: nil,
        nextSpeakerName: nil,
        previousHasTapAction: false,
        nextHasTapAction: false
      )
    )
  }

  private func segment(id: String, text: String) -> SpeakerSegment {
    SpeakerSegment(
      segmentId: id,
      speaker: 1,
      text: text,
      start: 0,
      end: 1
    )
  }
}
