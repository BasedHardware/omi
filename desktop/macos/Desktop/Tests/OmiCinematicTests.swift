import CoreGraphics
import Foundation
import XCTest

@testable import Omi_Computer

/// The cinematic's *values*: the timing tables, the beat order, the per-dot arrival, the cue table
/// and the grid. Every assertion here runs with no window, no clock and no audio device, which is
/// the whole reason the sequence and the timing are values rather than state inside the director.
final class OmiCinematicTests: XCTestCase {

  // MARK: - Timing tables

  func testStandardBeatTwoSumsToItsSubBeats() {
    let timing = OmiCinematicTiming.standard
    XCTAssertEqual(timing.dots + timing.markHold + timing.wordmark, timing.mark, accuracy: 1e-9)
  }

  func testStandardBeatFourSumsToItsSubBeats() {
    let timing = OmiCinematicTiming.standard
    XCTAssertEqual(
      timing.stretch + timing.typing + timing.promptHold, timing.prompt, accuracy: 1e-9)
  }

  func testStandardTotalIsTheSumOfEveryBeat() {
    let timing = OmiCinematicTiming.standard
    let summed = OmiCinematicBeat.allCases.reduce(0) { $0 + timing.duration(of: $1) }
    XCTAssertEqual(timing.total, summed, accuracy: 1e-9)
    XCTAssertEqual(timing.total, 8.60, accuracy: 1e-9)
  }

  func testWatchdogAlwaysOutlastsTheRunItProtects() {
    for timing in [OmiCinematicTiming.standard, .reduced] {
      XCTAssertEqual(timing.watchdogDeadline, timing.total + OmiCinematicTiming.watchdogSlack)
      XCTAssertGreaterThan(timing.watchdogDeadline, timing.total)
    }
  }

  /// Reduce Motion is a *table swap*, not a set of `if`s: every beat becomes the same cross-fade,
  /// nothing travels, and the sub-beats that only exist to pace movement collapse to zero.
  func testReducedTableMakesEveryBeatTheSameCrossFade() {
    let reduced = OmiCinematicTiming.reduced
    XCTAssertTrue(reduced.isCrossFade)
    for beat in OmiCinematicBeat.allCases {
      XCTAssertEqual(
        reduced.duration(of: beat), OmiCinematicTiming.crossFade, accuracy: 1e-9,
        "\(beat.name) should be one cross-fade under Reduce Motion")
    }
    XCTAssertEqual(reduced.markHold, 0)
    XCTAssertEqual(reduced.typing, 0)
    XCTAssertEqual(reduced.promptHold, 0)
    XCTAssertEqual(reduced.cardStagger, 0)
    // One arrival, not eight: eight cues inside 0.30 s is a rattle, not eight dots landing.
    XCTAssertEqual(reduced.dotArrivals, 1)
  }

  func testStandardTableStepsTheArrivalOncePerDot() {
    XCTAssertFalse(OmiCinematicTiming.standard.isCrossFade)
    XCTAssertEqual(OmiCinematicTiming.standard.dotArrivals, OmiCinematicMarkDraw.dotCount)
  }

  // MARK: - Beat sequencing

  func testSequenceWalksEveryBeatOnceInOrderAndThenCompletes() {
    var sequence = OmiCinematicSequence()
    var walked: [OmiCinematicBeat] = []
    while let beat = sequence.advance() { walked.append(beat) }

    XCTAssertEqual(walked, OmiCinematicBeat.allCases)
    XCTAssertEqual(sequence.visited, OmiCinematicBeat.allCases)
    XCTAssertEqual(sequence.stage, .ended(.completed))
  }

  func testSequenceCanBeAbortedFromEveryBeatAndRecordsWhichOne() {
    for beat in OmiCinematicBeat.allCases {
      var sequence = OmiCinematicSequence()
      while sequence.stage.beat != beat { XCTAssertNotNil(sequence.advance()) }

      XCTAssertEqual(sequence.abort(), .skipped(beat))
      XCTAssertEqual(sequence.stage, .ended(.skipped(beat)))
      // A late timer cannot walk a finished sequence forward.
      XCTAssertNil(sequence.advance())
      XCTAssertEqual(sequence.visited.last, beat)
    }
  }

  func testAbortBeforeTheFirstBeatBlamesTheFirstBeat() {
    var sequence = OmiCinematicSequence()
    XCTAssertEqual(sequence.abort(), .skipped(.dim))
  }

  func testTheFirstTerminalTransitionWins() {
    var sequence = OmiCinematicSequence()
    sequence.advance()
    sequence.advance()

    XCTAssertEqual(sequence.abort(), .skipped(.mark))
    // The watchdog arriving afterwards must not overwrite the user's own abort.
    XCTAssertNil(sequence.expire())
    XCTAssertNil(sequence.abort())
    XCTAssertEqual(sequence.stage, .ended(.skipped(.mark)))
  }

  func testExpiryIsTerminalAndNamesTheStalledBeat() {
    var sequence = OmiCinematicSequence()
    while sequence.stage.beat != .windows { sequence.advance() }

    XCTAssertEqual(sequence.expire(), .expired(.windows))
    XCTAssertEqual(sequence.stage.isTerminal, true)
    XCTAssertNil(sequence.expire())
  }

  func testEveryEndReportsWhetherTheUserInterruptedIt() {
    XCTAssertFalse(OmiCinematicEnd.completed.wasInterrupted)
    XCTAssertEqual(OmiCinematicEnd.completed.beat, .recede)
    XCTAssertTrue(OmiCinematicEnd.skipped(.bar).wasInterrupted)
    XCTAssertEqual(OmiCinematicEnd.skipped(.bar).beat, .bar)
    XCTAssertTrue(OmiCinematicEnd.expired(.prompt).wasInterrupted)
    XCTAssertEqual(OmiCinematicEnd.expired(.prompt).beat, .prompt)
  }

  // MARK: - The cue table

  func testEveryBeatCarriesACue() {
    let expected: [OmiCinematicBeat: OmiSoundEffect] = [
      .dim: .click, .mark: .click, .bar: .click,
      .prompt: .swoosh, .windows: .swoosh, .recede: .chime,
    ]
    for beat in OmiCinematicBeat.allCases {
      XCTAssertEqual(OmiCinematicCue.effect(for: beat), expected[beat], "beat \(beat.name)")
    }
  }

  func testOnlyInterfaceChromeAnswersToTheSystemUISoundSetting() {
    XCTAssertTrue(OmiSoundEffect.click.isChrome)
    XCTAssertTrue(OmiSoundEffect.swoosh.isChrome)
    // The completion cue is content: it marks the run finishing, not a click on a control.
    XCTAssertFalse(OmiSoundEffect.chime.isChrome)
  }

  // MARK: - The Omi mark's per-dot arrival

  /// `clamp(placed · 8 − i, 0, 1)`: one progress value, eight staggered entrances.
  func testDotArrivalIsStaggeredAcrossThePlacedProgress() {
    let count = OmiCinematicMarkDraw.dotCount

    // Nothing has landed at the start.
    for index in 0..<count {
      XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: index, placed: 0), 0)
    }
    // Everything has landed at the end.
    for index in 0..<count {
      XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: index, placed: 1), 1)
    }

    // Exactly one dot per step: at placed = k/8, dots 0..<k are down and the rest are untouched.
    for step in 0...count {
      let placed = Double(step) / Double(count)
      for index in 0..<count {
        let arrival = OmiCinematicMarkDraw.arrival(dot: index, placed: placed)
        if index < step {
          XCTAssertEqual(arrival, 1, "dot \(index) should be placed at \(placed)")
        } else {
          XCTAssertEqual(arrival, 0, "dot \(index) should not have started at \(placed)")
        }
      }
    }

    // Mid-step, exactly one dot is in flight.
    let midway = 3.5 / Double(count)
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: 3, placed: midway), 0.5, accuracy: 1e-9)
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: 2, placed: midway), 1)
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: 4, placed: midway), 0)
  }

  func testDotArrivalIsClampedAgainstOvershootAndNegativeIndices() {
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: 0, placed: 4), 1)
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: 7, placed: -1), 0)
    XCTAssertEqual(OmiCinematicMarkDraw.arrival(dot: -1, placed: 1), 0)
  }

  /// A dot grows from a third of its size, not from nothing: a dot that grows from zero reads as a
  /// bubble, one that grows from a third reads as being set down.
  func testDotEntranceScaleRunsFromTheFloorToFullSize() {
    XCTAssertEqual(
      OmiCinematicMarkDraw.entranceScale(dot: 0, placed: 0), OmiCinematicMarkDraw.entranceFloor)
    XCTAssertEqual(OmiCinematicMarkDraw.entranceScale(dot: 0, placed: 1), 1, accuracy: 1e-9)
    XCTAssertGreaterThan(OmiCinematicMarkDraw.entranceFloor, 0)
    XCTAssertLessThan(OmiCinematicMarkDraw.entranceFloor, 1)

    // Monotone in `placed`, so a spring interpolating it never runs a dot backwards.
    var previous = -1.0
    for step in 0...40 {
      let value = OmiCinematicMarkDraw.entranceScale(dot: 5, placed: Double(step) / 40)
      XCTAssertGreaterThanOrEqual(value, previous)
      previous = value
    }
  }

  // MARK: - The mark's geometry and comet pulse

  func testMarkPlacesEightDotsOnARingWithTheDiagonalsFurtherOut() {
    let centres = OmiCinematicMark.dotCentres
    XCTAssertEqual(centres.count, OmiCinematicMarkDraw.dotCount)

    let origin = CGPoint(x: OmiCinematicMark.centre, y: OmiCinematicMark.centre)
    for (index, point) in centres.enumerated() {
      let radius = hypot(point.x - origin.x, point.y - origin.y)
      let expected =
        index.isMultiple(of: 2) ? OmiCinematicMark.axisRadius : OmiCinematicMark.diagonalRadius
      XCTAssertEqual(radius, expected, accuracy: 1e-4, "dot \(index)")
    }
    // Dot 0 is due north in SwiftUI's y-down space.
    XCTAssertEqual(centres[0].x, origin.x, accuracy: 1e-9)
    XCTAssertLessThan(centres[0].y, origin.y)
    XCTAssertGreaterThan(OmiCinematicMark.diagonalRadius, OmiCinematicMark.axisRadius)
  }

  func testCometBrightnessPeaksOnOneDotAndIdlesOnTheRest() {
    // No phase at all is the static mark: every dot at full brightness.
    for index in 0..<OmiCinematicMarkDraw.dotCount {
      XCTAssertEqual(OmiCinematicMark.brightness(index: index, phase: nil), 1)
    }

    // The comet sitting exactly on dot 3 lights it and leaves the far side idle.
    let peak = 3.0 / Double(OmiCinematicMarkDraw.dotCount)
    XCTAssertEqual(OmiCinematicMark.brightness(index: 3, phase: peak), 1, accuracy: 1e-9)
    XCTAssertEqual(
      OmiCinematicMark.brightness(index: 7, phase: peak), OmiCinematicMark.idleBrightness,
      accuracy: 1e-9)

    // The pulse wraps: a comet just past dot 0 still brightens dot 7 behind it.
    XCTAssertGreaterThan(
      OmiCinematicMark.brightness(index: 7, phase: 0.01), OmiCinematicMark.idleBrightness)
  }

  func testCometPhaseIsOneLapPerLapSeconds() {
    let start = Date(timeIntervalSinceReferenceDate: 0)
    let halfLap = Date(timeIntervalSinceReferenceDate: OmiCinematicMark.lapSeconds / 2)
    let fullLap = Date(timeIntervalSinceReferenceDate: OmiCinematicMark.lapSeconds)

    XCTAssertEqual(OmiCinematicMark.phase(at: start), 0, accuracy: 1e-9)
    XCTAssertEqual(OmiCinematicMark.phase(at: halfLap), 0.5, accuracy: 1e-9)
    XCTAssertEqual(OmiCinematicMark.phase(at: fullLap), 0, accuracy: 1e-9)
  }

  // MARK: - Equal-power fades

  /// Equal power, not linear: a linear ramp on amplitude is heard as arriving late and leaving
  /// early, because loudness is not linear in amplitude.
  func testFadeIsEqualPowerRatherThanLinear() {
    XCTAssertEqual(
      OmiSoundFade.amplitude(from: 0, to: 1, progress: 0.5), Float(sin(Double.pi / 4)),
      accuracy: 1e-6)
    // Which is audibly *ahead* of the linear ramp at the same point.
    XCTAssertGreaterThan(OmiSoundFade.amplitude(from: 0, to: 1, progress: 0.5), 0.5)

    // A fade-out is the same curve read the other way.
    XCTAssertEqual(
      OmiSoundFade.amplitude(from: 1, to: 0, progress: 0.5),
      1 - Float(sin(Double.pi / 4)), accuracy: 1e-6)
  }

  func testFadeClampsSoALateTimerTickCannotOvershoot() {
    XCTAssertEqual(OmiSoundFade.amplitude(from: 0.2, to: 1, progress: -3), 0.2)
    XCTAssertEqual(OmiSoundFade.amplitude(from: 0.2, to: 1, progress: 0), 0.2)
    XCTAssertEqual(OmiSoundFade.amplitude(from: 0.2, to: 1, progress: 1), 1)
    XCTAssertEqual(OmiSoundFade.amplitude(from: 0.2, to: 1, progress: 9), 1)
  }

  func testFadeIsMonotoneAcrossTheRamp() {
    var previous: Float = -1
    for step in 0...100 {
      let value = OmiSoundFade.amplitude(from: 0, to: 1, progress: Double(step) / 100)
      XCTAssertGreaterThanOrEqual(value, previous)
      previous = value
    }
  }

  // MARK: - Beat 5's grid

  func testGridCentresEveryRowAroundTheComposition() {
    let count = OmiCinematicGrid.slots
    XCTAssertEqual(OmiCinematicGrid.rows(for: count), 2)

    let xs = (0..<count).map { OmiCinematicGrid.slot($0, count: count).width }
    // Both rows are symmetric about the centre.
    XCTAssertEqual(xs[0] + xs[2], 0, accuracy: 1e-9)
    XCTAssertEqual(xs[3] + xs[5], 0, accuracy: 1e-9)
    XCTAssertEqual(xs[1], 0, accuracy: 1e-9)

    // A short last row is centred rather than left-aligned: five windows leave two in the second
    // row, straddling the centre instead of hugging the leading edge.
    let shortRow = [
      OmiCinematicGrid.slot(3, count: 5).width, OmiCinematicGrid.slot(4, count: 5).width,
    ]
    XCTAssertEqual(shortRow[0] + shortRow[1], 0, accuracy: 1e-9)
    XCTAssertLessThan(shortRow[0], 0)
    XCTAssertGreaterThan(
      shortRow[0], OmiCinematicGrid.slot(3, count: 6).width,
      "a two-card row sits inside where a three-card row starts")
  }

  func testGridIsExactlyAsWideAsThePromptAboveIt() {
    XCTAssertEqual(OmiCinematicGrid.width, OmiCinematicVesselMetrics.promptWidth, accuracy: 0.001)
  }

  func testEveryWindowEntersFromOffTheStage() {
    let stage = CGSize(width: 700, height: 470)
    let count = OmiCinematicGrid.slots
    for index in 0..<count {
      let entry = OmiCinematicGrid.entry(index, count: count, in: stage)
      XCTAssertEqual(hypot(entry.width, entry.height), stage.width * 0.78, accuracy: 0.001)
    }
  }

  func testTheDeckIsTotalForAnyGridSizeAndStableAcrossRuns() {
    XCTAssertEqual(OmiCinematicWindowDeck.windows(count: 0), [])
    XCTAssertEqual(
      OmiCinematicWindowDeck.windows(count: OmiCinematicGrid.slots).map(\.id), Array(0..<6))
    // More slots than archetypes cycles rather than trapping.
    XCTAssertEqual(OmiCinematicWindowDeck.windows(count: 11).count, 11)
    // No randomness: two builds of the same deck are identical.
    XCTAssertEqual(
      OmiCinematicWindowDeck.windows(count: 6), OmiCinematicWindowDeck.windows(count: 6))
  }

  func testTheFieldOnlyFloatsWhenMotionIsAllowed() {
    XCTAssertTrue(OmiCinematicWindowMotion.allowsDrift(crossFade: false, reduceMotion: false))
    XCTAssertFalse(OmiCinematicWindowMotion.allowsDrift(crossFade: true, reduceMotion: false))
    XCTAssertFalse(OmiCinematicWindowMotion.allowsDrift(crossFade: false, reduceMotion: true))
    XCTAssertFalse(OmiCinematicWindowMotion.allowsDrift(crossFade: true, reduceMotion: true))
  }

  func testNoTwoWindowsFloatInStep() {
    // The drift at one instant differs window to window, which is what stops the grid reading as
    // one sheet of paper.
    let drifts = (0..<OmiCinematicGrid.slots).map {
      OmiCinematicWindowMotion.drift(index: $0, at: 3.25, depth: OmiCinematicGrid.depth($0))
    }
    for (a, b) in zip(drifts, drifts.dropFirst()) {
      XCTAssertNotEqual(a, b)
    }
    XCTAssertEqual(OmiCinematicWindowMotion.drift(index: -1, at: 3.25), .still)
  }

  // MARK: - Composition

  func testTheSkipControlsArriveWithTheScrimAndLeaveWithTheLastBeat() {
    XCTAssertFalse(OmiCinematicView.controlsVisible(dim: 0, receding: false))
    XCTAssertTrue(OmiCinematicView.controlsVisible(dim: 1, receding: false))
    XCTAssertFalse(OmiCinematicView.controlsVisible(dim: 1, receding: true))
  }

  func testCompositionScaleIsFlooredAndCapped() {
    XCTAssertEqual(OmiCinematicView.scale(for: CGSize(width: 400, height: 300)), 0.78)
    XCTAssertEqual(OmiCinematicView.scale(for: CGSize(width: 8000, height: 6000)), 1.5)
    XCTAssertEqual(OmiCinematicView.scale(for: .zero), 1)
  }

  func testTheVesselKeepsItsCentreWhileTheShellStretches() {
    let mark = OmiCinematicVesselMetrics.metrics(for: .mark)
    let bar = OmiCinematicVesselMetrics.metrics(for: .bar)
    let prompt = OmiCinematicVesselMetrics.metrics(for: .prompt)

    // The shell exists at the wordmark's footprint before beat 3 so the bar grows out of it.
    XCTAssertEqual(mark.shellOpacity, 0)
    XCTAssertEqual(bar.shellOpacity, 1)
    XCTAssertLessThan(bar.shellSize.width, prompt.shellSize.width)

    // The mark shrinks into the leading edge and stays on the shell's centre line from beat 3 on.
    XCTAssertGreaterThan(mark.markSize, bar.markSize)
    XCTAssertEqual(bar.markOffset.height, 0)
    XCTAssertEqual(prompt.markOffset.height, 0)
    XCTAssertLessThan(prompt.markOffset.width, 0)

    // The question only exists once there is a field to hold it.
    XCTAssertEqual(mark.questionOpacity, 0)
    XCTAssertEqual(bar.questionOpacity, 0)
    XCTAssertEqual(prompt.questionOpacity, 1)
  }
}
