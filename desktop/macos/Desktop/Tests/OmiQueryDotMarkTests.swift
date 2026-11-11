import XCTest

@testable import Omi_Computer

/// The query mark's resting contract.
///
/// The measurement behind this file: with `is_sending=false is_streaming=false`, the 52×52 mark box
/// was the *only* repainting region on the entire surface across eight captured idle frames, and the
/// app sat near a tenth of a core behind a completely static window. The mark turned forever and the
/// working state only changed how fast — so "turning" carried no information, and the resting state
/// was visually indistinguishable from a loading spinner.
///
/// `turns` is the production decision, not a restatement of it: the view installs its rotating
/// modifier if and only if this returns true, and removes it outright otherwise.
final class OmiQueryDotMarkTests: XCTestCase {
  func testAnIdleMarkIsNotDrivenByAnAnimationAtAll() {
    XCTAssertFalse(
      OmiQueryMarkMotion.turns(isWorking: false, reduceMotion: false),
      "A resting mark must not ask the run loop for a frame.")
  }

  func testAMarkTurnsOnlyWhileATurnIsInFlight() {
    XCTAssertTrue(OmiQueryMarkMotion.turns(isWorking: true, reduceMotion: false))
  }

  /// Reduce Motion takes the rotation away in both states rather than slowing it down — "animate
  /// this more gently" is not what the setting asks for.
  func testReduceMotionStopsTheTurnInBothStates() {
    XCTAssertFalse(OmiQueryMarkMotion.turns(isWorking: true, reduceMotion: true))
    XCTAssertFalse(OmiQueryMarkMotion.turns(isWorking: false, reduceMotion: true))
  }

  /// Motion is not the only thing separating the two states, which is what lets Reduce Motion remove
  /// the rotation without removing the signal along with it.
  func testTheWorkingStateStaysLegibleWithoutMotion() {
    let resting = OmiQueryMarkMotion.alphas(isWorking: false)
    let working = OmiQueryMarkMotion.alphas(isWorking: true)

    XCTAssertNotEqual(
      resting, working,
      "Working and resting must differ in the still frame, not only in motion.")
    XCTAssertEqual(
      Set(resting).count, 1,
      "A resting ring is flat: no leading edge, so it reads as a mark rather than a stopped spinner.")
    XCTAssertGreaterThan(
      Set(working).count, 1,
      "A turning ring needs a leading edge, or the rotation is invisible.")
    XCTAssertEqual(
      resting.count, working.count,
      "The ring keeps its shape across states; only the ramp changes.")
    XCTAssertEqual(resting.count, OmiQueryMarkMotion.dotCount)
  }

  /// There is deliberately no resting period to name. A resting period is what made the old mark a
  /// perpetual spinner: `isWorking` only chose between 9 s and 1.6 s, and neither was "stop".
  func testOnlyTheWorkingStateHasADuration() {
    XCTAssertGreaterThan(OmiQueryMarkMotion.workingPeriod, 0)
  }
}
