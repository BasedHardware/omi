import XCTest

@testable import Omi_Computer

final class CaptureAudioTimelineTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1000)

  func test150SecondGateGapPreservesWallTimeAndSplitsDecodeWindows() {
    var timeline = CaptureAudioTimeline()
    timeline.setPaused(true, at: start, capturedSamples: 16000)
    timeline.setPaused(false, at: start.addingTimeInterval(150), capturedSamples: 16000)
    let beforeGap = timeline.samplesUntilNextGap(after: 0)
    XCTAssertEqual(beforeGap, 16000, "buffered pre-gap speech must drain separately")
    XCTAssertEqual(timeline.timestamp(at: 0, sampleRate: 16000), 0)
    XCTAssertEqual(timeline.timestamp(at: 16000, sampleRate: 16000), 151)
    XCTAssertEqual(timeline.timestamp(at: 32000, sampleRate: 16000), 152)
    XCTAssertNil(timeline.samplesUntilNextGap(after: 16000))
  }

  func testRepeatedPausedReconcilesDoNotShortenTheGapAndSamePositionGapsAccumulate() {
    var timeline = CaptureAudioTimeline()
    timeline.setPaused(true, at: start, capturedSamples: 0)
    timeline.setPaused(true, at: start.addingTimeInterval(100), capturedSamples: 0)
    timeline.setPaused(false, at: start.addingTimeInterval(150), capturedSamples: 0)
    timeline.setPaused(false, at: start.addingTimeInterval(160), capturedSamples: 0)
    XCTAssertEqual(timeline.timestamp(at: 0, sampleRate: 16000), 150)
    timeline.setPaused(true, at: start.addingTimeInterval(170), capturedSamples: 0)
    timeline.setPaused(false, at: start.addingTimeInterval(180), capturedSamples: 0)
    XCTAssertEqual(timeline.timestamp(at: 0, sampleRate: 16000), 160)
  }

  func testContinuousAlwaysCaptureAndClockRollbackDoNotAddGaps() {
    var timeline = CaptureAudioTimeline()
    timeline.setPaused(false, at: start, capturedSamples: 0)
    timeline.setPaused(false, at: start.addingTimeInterval(150), capturedSamples: 16000)
    XCTAssertEqual(timeline.timestamp(at: 16000, sampleRate: 16000), 1)
    timeline.setPaused(true, at: start, capturedSamples: 16000)
    timeline.setPaused(false, at: start.addingTimeInterval(-1), capturedSamples: 16000)
    XCTAssertEqual(timeline.timestamp(at: 32000, sampleRate: 16000), 2)
  }
}
