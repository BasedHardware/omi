import XCTest

@testable import Omi_Computer

final class NotchVoiceMorphMarkTests: XCTestCase {
  func testListeningStateOwnsTheMorphTarget() {
    XCTAssertEqual(NotchVoiceMorphGeometry.targetProgress(isListening: false), 0)
    XCTAssertEqual(NotchVoiceMorphGeometry.targetProgress(isListening: true), 1)
  }

  func testMorphMovesThroughRingLineAndWaveformStages() {
    XCTAssertEqual(NotchVoiceMorphGeometry.stage(progress: 0), .ring)
    XCTAssertEqual(NotchVoiceMorphGeometry.stage(progress: 0.55), .line)
    XCTAssertEqual(NotchVoiceMorphGeometry.stage(progress: 0.9), .line)
    XCTAssertEqual(NotchVoiceMorphGeometry.stage(progress: 1), .waveform)
  }

  func testLineProgressIsMonotonicAndWaveWaitsForBoundary() {
    let early = NotchVoiceMorphGeometry.lineProgress(0.2)
    let middle = NotchVoiceMorphGeometry.lineProgress(0.4)
    let complete = NotchVoiceMorphGeometry.lineProgress(0.55)

    XCTAssertGreaterThan(early, 0)
    XCTAssertGreaterThan(middle, early)
    XCTAssertEqual(complete, 1, accuracy: 0.001)
    XCTAssertEqual(
      NotchVoiceMorphGeometry.waveProgress(0.5, reduceMotion: false),
      0,
      accuracy: 0.001
    )
    XCTAssertGreaterThan(
      NotchVoiceMorphGeometry.waveProgress(0.8, reduceMotion: false),
      0
    )
  }

  func testReduceMotionSuppressesLiveWaveDisplacement() {
    XCTAssertEqual(
      NotchVoiceMorphGeometry.waveProgress(1, reduceMotion: true),
      0,
      accuracy: 0.001
    )
  }
}
