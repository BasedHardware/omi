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

  func testRadialPushKeepsEveryDotInsideTheIdentitySlot() {
    // Even the fully-pushed dot edge must fit the 21pt mark slot, for every
    // dot and wave phase.
    let size = NotchVoiceMorphGeometry.markSize
    let base = min(size.width, size.height)
    let dotRadius = base * NotchVoiceMorphGeometry.dotDiameterRatio / 2
    for time in stride(from: 0.0, through: 2.0, by: 0.03) {
      for index in 0..<NotchVoiceMorphGeometry.dotCount {
        let push = NotchVoiceMorphGeometry.speakingRadialPush(
          index: index, time: time, level: 1)
        let radius =
          base * NotchVoiceMorphGeometry.ringRadiusRatio
          * (1 + NotchVoiceMorphGeometry.speakingPushMax * push)
        XCTAssertLessThanOrEqual(radius + dotRadius, base / 2 + 0.001)
      }
    }
  }

  func testWaveEnvelopeIsCenterWeighted() {
    let edge = NotchVoiceMorphGeometry.waveEnvelope(index: 0)
    let center = NotchVoiceMorphGeometry.waveEnvelope(index: NotchVoiceMorphGeometry.dotCount / 2)
    XCTAssertGreaterThan(center, edge)
    XCTAssertGreaterThan(edge, 0)
  }

  func testSpikeOffsetNeverExceedsItsAmplitude() {
    let amplitude: CGFloat = 5.88
    for time in stride(from: 0.0, through: 2.0, by: 0.03) {
      for index in 0..<NotchVoiceMorphGeometry.dotCount {
        let offset = NotchVoiceMorphGeometry.spikeOffset(
          time: time, index: index, amplitude: amplitude)
        XCTAssertLessThanOrEqual(abs(offset), amplitude + 0.001)
      }
    }
  }

  func testSpikeOffsetsAreDecorrelatedAcrossDotsLikeEqualizerBands() {
    // Adjacent dots must not move as one travelling rope: at any instant
    // some dots spike up while others spike down.
    var sawOppositeSigns = false
    for time in stride(from: 0.1, through: 2.0, by: 0.13) {
      let offsets = (0..<NotchVoiceMorphGeometry.dotCount).map {
        NotchVoiceMorphGeometry.spikeOffset(time: time, index: $0, amplitude: 1)
      }
      if let maxOffset = offsets.max(), let minOffset = offsets.min(),
        maxOffset > 0.2, minOffset < -0.2
      {
        sawOppositeSigns = true
      }
    }
    XCTAssertTrue(sawOppositeSigns)
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

  func testRadialPushIsACircularWaveDrivenByTheOutputLevel() {
    // A pause in the reply must leave the ring completely still.
    for index in 0..<NotchVoiceMorphGeometry.dotCount {
      XCTAssertEqual(
        NotchVoiceMorphGeometry.speakingRadialPush(index: index, time: 0.7, level: 0),
        0,
        accuracy: 0.0001
      )
    }
    // The push is bounded by the level, outward only, and louder pushes harder.
    for index in 0..<NotchVoiceMorphGeometry.dotCount {
      let quiet = NotchVoiceMorphGeometry.speakingRadialPush(index: index, time: 0.7, level: 0.4)
      let loud = NotchVoiceMorphGeometry.speakingRadialPush(index: index, time: 0.7, level: 1)
      XCTAssertGreaterThanOrEqual(quiet, 0)
      XCTAssertLessThanOrEqual(quiet, 0.4001)
      XCTAssertLessThanOrEqual(loud, 1.0001)
      XCTAssertGreaterThanOrEqual(loud, quiet - 0.0001)
    }
    // Not a uniform swell: at one instant different dots sit at different
    // displacements, and each dot's displacement changes over time (the wave
    // travels around the ring).
    let atOnce = (0..<NotchVoiceMorphGeometry.dotCount).map {
      NotchVoiceMorphGeometry.speakingRadialPush(index: $0, time: 0.7, level: 1)
    }
    XCTAssertGreaterThan((atOnce.max() ?? 0) - (atOnce.min() ?? 0), 0.15)
    let later = NotchVoiceMorphGeometry.speakingRadialPush(index: 0, time: 1.05, level: 1)
    XCTAssertNotEqual(atOnce[0], later, accuracy: 0.01)
  }

  func testSpeakingWaveAlwaysTravelsInOneDirection() {
    // The three-crest pattern advances exactly one dot per 3/8 period,
    // always the same way around the ring: shifting one dot forward in
    // space and 3/8 period forward in time reproduces the wave exactly.
    let dotStep = NotchVoiceMorphGeometry.speakingWavePeriod * 3 / 8
    for time in stride(from: 0.0, through: 2.0, by: 0.17) {
      for index in 0..<NotchVoiceMorphGeometry.dotCount {
        let here = NotchVoiceMorphGeometry.speakingRadialPush(
          index: index, time: time, level: 1)
        let handedOff = NotchVoiceMorphGeometry.speakingRadialPush(
          index: (index + 1) % NotchVoiceMorphGeometry.dotCount,
          time: time + dotStep,
          level: 1)
        XCTAssertEqual(handedOff, here, accuracy: 0.0001)
      }
    }
    // The reversed hand-off does not reproduce it — the travel is
    // unidirectional, not a standing oscillation.
    let forward = NotchVoiceMorphGeometry.speakingRadialPush(index: 3, time: 0.4, level: 1)
    let reversed = NotchVoiceMorphGeometry.speakingRadialPush(
      index: 2, time: 0.4 + dotStep, level: 1)
    XCTAssertNotEqual(forward, reversed, accuracy: 0.05)
  }

  func testSilenceAndRoomNoiseRenderFlatButRealSpeechFillsTheRange() {
    let display = VoiceLevelDisplay(minPeak: 0.035)
    // Silence and ambient room noise (0.005–0.013 measured on real hardware)
    // must render a genuinely flat line — no display floor.
    XCTAssertEqual(display.step(rawLevel: 0, at: 0), 0, accuracy: 0.0001)
    XCTAssertEqual(display.step(rawLevel: 0.005, at: 0.05), 0, accuracy: 0.0001)
    XCTAssertEqual(display.step(rawLevel: 0.012, at: 0.1), 0, accuracy: 0.0001)
    // Quiet real speech (0.04 RMS — measured scale on real hardware) must
    // reach most of the visual range via auto-gain, not sub-pixel wiggle.
    var level: CGFloat = 0
    for i in 0..<30 {
      level = display.step(rawLevel: 0.04, at: 0.2 + Double(i) * 0.016)
    }
    XCTAssertGreaterThan(level, 0.7, "Normal speech must use the full wave height")
    // Release back to flat when the speaker stops.
    for i in 0..<60 {
      level = display.step(rawLevel: 0, at: 1.0 + Double(i) * 0.016)
    }
    XCTAssertLessThan(level, 0.05)
  }

  func testQuietPhraseTailRidesThroughTheGateInsteadOfFlatlining() {
    let display = VoiceLevelDisplay(minPeak: 0.035, peakHalfLife: 2)
    var t = 0.0
    for _ in 0..<20 {
      _ = display.step(rawLevel: 0.1, at: t)
      t += 0.016
    }
    // The trailing end of the phrase drops below the opening gate while the
    // speaker is still talking; within the hangover it must stay visible.
    var tail: CGFloat = 1
    for _ in 0..<20 {
      tail = display.step(rawLevel: 0.011, at: t)
      t += 0.016
    }
    XCTAssertGreaterThan(tail, 0.05, "Tail-of-phrase speech must not flatline mid-word")
    // But once the speaker actually stops, silence still closes the wave —
    // and true near-silence never renders, hangover or not.
    for _ in 0..<80 {
      tail = display.step(rawLevel: 0.004, at: t)
      t += 0.016
    }
    XCTAssertLessThan(tail, 0.05)
  }

  func testAutoGainAdaptsToLoudSpeechButKeepsQuietWordsVisible() {
    let display = VoiceLevelDisplay(minPeak: 0.035)
    var t = 0.0
    // A loud stretch raises the reference peak…
    for _ in 0..<30 {
      _ = display.step(rawLevel: 0.2, at: t)
      t += 0.016
    }
    // …and an immediately following quieter word is scaled relative to it,
    // still clearly visible rather than crushed to near zero.
    var quiet: CGFloat = 0
    for _ in 0..<30 {
      quiet = display.step(rawLevel: 0.08, at: t)
      t += 0.016
    }
    XCTAssertGreaterThan(quiet, 0.35)
    XCTAssertLessThan(quiet, 0.95, "Quieter speech must read as quieter than the loud peak")
  }
}
