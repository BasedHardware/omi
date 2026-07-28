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

  func testSpeakerPulseStaysBoundedAndRespectsReduceMotion() {
    for time in stride(from: 0.0, through: 3.0, by: 0.05) {
      let pulse = NotchVoiceMorphGeometry.speakerPulse(time: time, reduceMotion: false)
      XCTAssertGreaterThanOrEqual(pulse, 0)
      XCTAssertLessThanOrEqual(pulse, 1)
    }
    XCTAssertEqual(
      NotchVoiceMorphGeometry.speakerPulse(time: 0.42, reduceMotion: true),
      0,
      accuracy: 0.001
    )
  }

  func testSpeakingPulseKeepsEveryDotInsideTheIdentitySlot() {
    // Speaker pulse scales both the ring radius and the dot diameter; at full
    // pulse the outermost dot edge must still fit the 21pt mark slot.
    let size = NotchVoiceMorphGeometry.markSize
    let base = min(size.width, size.height)
    let maxRingRadius =
      base * NotchVoiceMorphGeometry.ringRadiusRatio
      * NotchVoiceMorphGeometry.speakingRingRadiusScale(pulse: 1)
    let maxDotRadius =
      base * NotchVoiceMorphGeometry.dotDiameterRatio
      * NotchVoiceMorphGeometry.speakingDotScale(pulse: 1) / 2
    XCTAssertLessThanOrEqual(maxRingRadius + maxDotRadius, base / 2)
  }

  func testWaveEnvelopeIsCenterWeighted() {
    let edge = NotchVoiceMorphGeometry.waveEnvelope(index: 0)
    let center = NotchVoiceMorphGeometry.waveEnvelope(index: NotchVoiceMorphGeometry.dotCount / 2)
    XCTAssertGreaterThan(center, edge)
    XCTAssertGreaterThan(edge, 0)
  }

  func testWaveOffsetNeverExceedsItsAmplitude() {
    let amplitude: CGFloat = 5.88
    for time in stride(from: 0.0, through: 2.0, by: 0.03) {
      for index in 0..<NotchVoiceMorphGeometry.dotCount {
        let offset = NotchVoiceMorphGeometry.waveOffset(
          time: time, index: index, amplitude: amplitude)
        XCTAssertLessThanOrEqual(abs(offset), amplitude + 0.001)
      }
    }
  }

  func testLevelSmootherAttacksFasterThanItReleases() {
    let smoother = VoiceLevelSmoother()
    smoother.step(target: 0, at: 0)
    let afterAttack = smoother.step(target: 1, at: 0.1)
    XCTAssertGreaterThan(afterAttack, 0.7, "Speech onset must register within ~100ms")

    let peak = smoother.displayed
    let afterRelease = smoother.step(target: 0, at: 0.2)
    XCTAssertGreaterThan(
      afterRelease, peak * 0.4,
      "A pause must decay gently, not snap the waveform flat")
    XCTAssertLessThan(afterRelease, peak)
  }

  func testLevelSmootherClampsInputAndSurvivesTimeGaps() {
    let smoother = VoiceLevelSmoother()
    XCTAssertEqual(smoother.step(target: 7, at: 0), 1, accuracy: 0.001)
    // A paused TimelineView resuming (huge dt) converges without overshoot.
    let resumed = smoother.step(target: 0.5, at: 100)
    XCTAssertGreaterThan(resumed, 0.4)
    XCTAssertLessThanOrEqual(resumed, 1)
    // Non-advancing time snaps rather than dividing by zero.
    XCTAssertEqual(smoother.step(target: 0.25, at: 100), 0.25, accuracy: 0.001)
  }

  func testSpeakingLevelModulationKeepsFloorAndCeiling() {
    XCTAssertEqual(
      NotchVoiceMorphGeometry.speakingLevelModulation(0),
      NotchVoiceMorphGeometry.speakingLevelFloor,
      accuracy: 0.001,
      "Silent stretches of a reply must keep a visible breath")
    XCTAssertEqual(NotchVoiceMorphGeometry.speakingLevelModulation(1), 1, accuracy: 0.001)
    XCTAssertEqual(NotchVoiceMorphGeometry.speakingLevelModulation(5), 1, accuracy: 0.001)
    XCTAssertEqual(NotchVoiceMorphGeometry.normalizedVoiceLevel(0), 0, accuracy: 0.001)
    XCTAssertEqual(NotchVoiceMorphGeometry.normalizedVoiceLevel(1), 1, accuracy: 0.001)
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
