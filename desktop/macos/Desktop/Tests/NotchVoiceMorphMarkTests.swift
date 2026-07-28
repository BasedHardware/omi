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
      NotchVoiceMorphGeometry.lineProgress(1),
      1,
      accuracy: 0.001,
      "The completed morph must not overshoot and project dots outside the mark slot."
    )
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

  func testRingAndWaveformShareTheNormalOmiMarkCenter() {
    let size = NotchVoiceMorphGeometry.markSize
    XCTAssertEqual(NotchVoiceMorphGeometry.center(in: size).x, 10.5, accuracy: 0.001)
    XCTAssertEqual(NotchVoiceMorphGeometry.center(in: size).y, 10.5, accuracy: 0.001)

    let first = NotchVoiceMorphGeometry.dotPosition(index: 0, size: size, progress: 1)
    let last = NotchVoiceMorphGeometry.dotPosition(
      index: NotchVoiceMorphGeometry.dotCount - 1,
      size: size,
      progress: 1
    )
    XCTAssertEqual((first.x + last.x) / 2, size.width / 2, accuracy: 0.001)
  }

  func testWaveformDotsStayInsideTheVisibleIdentitySlot() {
    let size = NotchVoiceMorphGeometry.markSize
    let radius = min(size.width, size.height) * NotchVoiceMorphGeometry.dotDiameterRatio / 2

    for progress in stride(from: CGFloat(0), through: 1, by: 0.05) {
      for index in 0..<NotchVoiceMorphGeometry.dotCount {
        let point = NotchVoiceMorphGeometry.dotPosition(
          index: index,
          size: size,
          progress: progress,
          waveOffset: 4
        )
        XCTAssertGreaterThanOrEqual(point.x - radius, 0)
        XCTAssertLessThanOrEqual(point.x + radius, size.width)
        XCTAssertGreaterThanOrEqual(point.y - radius, 0)
        XCTAssertLessThanOrEqual(point.y + radius, size.height)
      }
    }
  }

  func testQuietListeningStillProducesAVisibleWave() {
    XCTAssertEqual(
      NotchVoiceMorphGeometry.normalizedLevel(0),
      NotchVoiceMorphGeometry.quietLevelFloor,
      accuracy: 0.001
    )
    XCTAssertGreaterThan(NotchVoiceMorphGeometry.normalizedLevel(0), 0.25)
    XCTAssertEqual(NotchVoiceMorphGeometry.normalizedLevel(1), 1, accuracy: 0.001)
  }
}
