import Foundation
import XCTest

@testable import Omi_Computer

/// What the audio layer was asked to do, in order. A seam rather than a device, so the cue
/// *decisions* — one per beat, one per dot, a swoosh per card, a fade rather than a cut on abort —
/// are asserted with no CoreAudio anywhere.
@MainActor
private final class RecordingCues: OmiCinematicCues {
  enum Event: Equatable {
    case prepare
    case startMusic
    case stopMusic(TimeInterval)
    case play(OmiSoundEffect)
    case setMusicEnabled(Bool)
  }

  /// What the composition looked like at the instant a cue fired.
  ///
  /// Recorded here rather than sampled from the test's own task, because "which beat did this click
  /// belong to" is only answerable at the moment of the call — polling from outside depends on how
  /// two tasks happen to interleave, which is exactly the kind of timing dependence an injected
  /// clock exists to remove.
  struct Snapshot: Equatable {
    var effect: OmiSoundEffect
    var beat: OmiCinematicBeat?
    var placed: Double
    var pulsing: Bool
  }

  private(set) var events: [Event] = []
  private(set) var snapshots: [Snapshot] = []
  var isMusicEnabled: Bool = true

  /// Set by the test right after the director is built. `weak`, so the recorder never keeps the
  /// object it is observing alive.
  weak var director: OmiCinematicDirector?

  var plays: [OmiSoundEffect] {
    events.compactMap { if case .play(let effect) = $0 { return effect } else { return nil } }
  }

  var stopFades: [TimeInterval] {
    events.compactMap { if case .stopMusic(let fade) = $0 { return fade } else { return nil } }
  }

  func count(of effect: OmiSoundEffect) -> Int { plays.filter { $0 == effect }.count }

  func prepare() { events.append(.prepare) }
  func startMusic() { events.append(.startMusic) }
  func stopMusic(fadeOut: TimeInterval) { events.append(.stopMusic(fadeOut)) }
  func play(_ effect: OmiSoundEffect) {
    events.append(.play(effect))
    guard let director else { return }
    snapshots.append(
      Snapshot(
        effect: effect, beat: director.stage.beat, placed: director.draw.placed,
        pulsing: director.pulsing))
  }

  /// Every cue that fired during `beat`, in order.
  func snapshots(during beat: OmiCinematicBeat) -> [Snapshot] {
    snapshots.filter { $0.beat == beat }
  }

  func setMusicEnabled(_ enabled: Bool) {
    isMusicEnabled = enabled
    events.append(.setMusicEnabled(enabled))
  }
}

/// The director driven by an injected clock: `sleep` yields instead of waiting, so the whole
/// eight-second run resolves in microseconds and nothing here is timing-dependent.
@MainActor
final class OmiCinematicDirectorTests: XCTestCase {
  /// The one seam the beat loop waits on.
  private static let instantSleep: OmiCinematicDirector.Sleep = { _ in await Task.yield() }

  /// Lets the director's task run until it reaches a terminal stage. Bounded, and driven by
  /// cooperative yields rather than wall-clock time.
  private func drain(_ director: OmiCinematicDirector, limit: Int = 50_000) async {
    for _ in 0..<limit {
      if director.stage.isTerminal { return }
      await Task.yield()
    }
    XCTFail("the cinematic never reached a terminal stage")
  }

  /// Runs until `beat` is on screen, so a test can interrupt a specific beat without a stopwatch.
  private func advance(
    _ director: OmiCinematicDirector, to beat: OmiCinematicBeat, limit: Int = 50_000
  ) async {
    for _ in 0..<limit {
      if director.stage.beat == beat { return }
      if director.stage.isTerminal { break }
      await Task.yield()
    }
    XCTFail("the cinematic never reached \(beat.name)")
  }

  // MARK: - The full run

  func testAFullRunPlaysEveryBeatInOrderAndCompletes() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    var ended: OmiCinematicEnd?
    director.start { ended = $0 }
    await drain(director)

    XCTAssertEqual(ended, .completed)
    XCTAssertEqual(director.visitedBeats, OmiCinematicBeat.allCases)
    XCTAssertEqual(director.stage, .ended(.completed))
  }

  func testTheRunEndsWithTheWholeCompositionBuilt() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    director.start { _ in }
    await drain(director)

    XCTAssertEqual(director.draw, .complete)
    XCTAssertEqual(director.typedQuestion, OmiCinematicDirector.question)
    XCTAssertEqual(director.form, .prompt)
    XCTAssertTrue(director.pulsing)
    XCTAssertTrue(director.gridOpen)
    XCTAssertTrue(director.receding)
    XCTAssertEqual(director.settledCards, OmiCinematicGrid.slots)
    XCTAssertEqual(director.dim, 0, "beat 6 lifts the dim back off the desktop")
  }

  /// Beat 2 is the centrepiece: the arrival is stepped once per dot, each step carries its own cue,
  /// and the comet pulse does not start until the last dot is down.
  ///
  /// Every cue records the composition it fired against, so this asserts the beat's whole shape at
  /// once: eight clicks, each one landing on a mark that has exactly the previous dots down, and
  /// then — with the pulse already handed over — the wordmark's.
  func testBeatTwoStepsTheArrivalOncePerDotWithACueEachTime() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)
    cues.director = director

    director.start { _ in }
    await drain(director)

    let markCues = cues.snapshots(during: .mark)
    let arrival = markCues.filter { !$0.pulsing }
    let afterArrival = markCues.filter { $0.pulsing }

    // One cue per dot, and nothing else, while the dots are still landing.
    XCTAssertEqual(arrival.count, OmiCinematicMarkDraw.dotCount)
    XCTAssertTrue(arrival.allSatisfy { $0.effect == .click })
    for (index, cue) in arrival.enumerated() {
      XCTAssertEqual(
        cue.placed, Double(index) / Double(OmiCinematicMarkDraw.dotCount), accuracy: 1e-9,
        "cue \(index) should land on a mark with \(index) dots already down")
    }

    // Then the pulse takes over, and the wordmark's cue is the only one that follows.
    XCTAssertEqual(afterArrival.count, 1)
    XCTAssertEqual(afterArrival.first?.effect, .click)
    XCTAssertEqual(afterArrival.first?.placed, 1)
  }

  func testTheArrivalNeverStartsThePulseEarly() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)
    cues.director = director

    director.start { _ in }
    await drain(director)

    // No cue anywhere in the run fired against a partly-placed mark that was already pulsing.
    for cue in cues.snapshots where cue.pulsing {
      XCTAssertEqual(cue.placed, 1, "the comet must not run while dots are still arriving")
    }
  }

  func testEveryBeatCarriesItsCueAcrossAWholeRun() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    director.start { _ in }
    await drain(director)

    let keystrokes = OmiCinematicDirector.question.count / OmiCinematicDirector.keystrokeEvery
    XCTAssertEqual(
      cues.count(of: .click),
      1  // beat 1
        + OmiCinematicMarkDraw.dotCount  // beat 2, one per dot
        + 1  // beat 2's wordmark
        + 1  // beat 3
        + keystrokes  // beat 4's typing texture
    )
    XCTAssertEqual(
      cues.count(of: .swoosh),
      1  // beat 4's stretch
        + OmiCinematicGrid.slots  // beat 5, one per card
    )
    XCTAssertEqual(cues.count(of: .chime), 1, "the completion cue fires exactly once")
    XCTAssertEqual(cues.plays.last, .chime)
  }

  func testTheBedIsWarmedStartedOnceAndFadedOutRatherThanCut() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    director.start { _ in }
    await drain(director)

    XCTAssertEqual(cues.events.first, .prepare, "decoders are warmed before the first cue")
    XCTAssertEqual(cues.events.filter { $0 == .startMusic }.count, 1)
    XCTAssertEqual(cues.stopFades, [OmiCinematicDirector.completedFadeOut])
  }

  // MARK: - Interruption

  func testSkippingMidRunEndsOnTheBeatItInterruptedAndFadesFaster() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    var ended: OmiCinematicEnd?
    director.start { ended = $0 }
    await advance(director, to: .prompt)
    director.skip()

    XCTAssertEqual(ended, .skipped(.prompt))
    XCTAssertEqual(cues.stopFades, [OmiCinematicDirector.interruptedFadeOut])
    XCTAssertLessThan(
      OmiCinematicDirector.interruptedFadeOut, OmiCinematicDirector.completedFadeOut,
      "an abort should feel like a stop, a completed run like an ending")
    // No beat after the one that was interrupted.
    XCTAssertEqual(director.visitedBeats.last, .prompt)
  }

  /// Esc, the Skip button, the last beat and the watchdog can all arrive; exactly one of them is
  /// allowed to hand off.
  func testTheExitIsLatchedSoOnlyOneThingCanHandOff() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    var handoffs = 0
    director.start { _ in handoffs += 1 }
    await advance(director, to: .mark)

    director.skip()
    director.skip()
    director.skip()
    await Task.yield()

    XCTAssertEqual(handoffs, 1)
    XCTAssertEqual(cues.stopFades.count, 1, "the bed is stopped exactly once")
  }

  func testACompletedRunCannotBeSkippedAfterwards() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    var handoffs = 0
    director.start { _ in handoffs += 1 }
    await drain(director)

    director.skip()
    XCTAssertEqual(handoffs, 1)
    XCTAssertEqual(cues.stopFades, [OmiCinematicDirector.completedFadeOut])
  }

  func testStartIsIdempotent() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    director.start { _ in }
    director.start { _ in }
    await drain(director)

    XCTAssertEqual(director.visitedBeats, OmiCinematicBeat.allCases)
    XCTAssertEqual(cues.events.filter { $0 == .startMusic }.count, 1)
  }

  // MARK: - Reduce Motion

  /// The reduced table is a *swap*, and the director does not know which table it got: the beats
  /// still happen, in order, with their sounds — the run is a slideshow rather than a sequence of
  /// moves.
  func testTheReducedTableStillPlaysEveryBeatWithItsCue() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .reduced, cues: cues, sleep: Self.instantSleep)

    var ended: OmiCinematicEnd?
    director.start { ended = $0 }
    await drain(director)

    XCTAssertEqual(ended, .completed)
    XCTAssertEqual(director.visitedBeats, OmiCinematicBeat.allCases)
    XCTAssertEqual(cues.count(of: .chime), 1)
    XCTAssertEqual(cues.count(of: .swoosh), 1 + OmiCinematicGrid.slots)
  }

  func testTheReducedTablePlacesEveryDotOnOneCueAndSkipsTheTyping() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .reduced, cues: cues, sleep: Self.instantSleep)
    cues.director = director

    director.start { _ in }
    await drain(director)

    // beat 1, one arrival for the whole mark, the wordmark, beat 3 — and no keystroke texture,
    // because there is no typing to give texture to.
    XCTAssertEqual(cues.count(of: .click), 4)
    // The whole ring is placed on a single cue rather than eight.
    XCTAssertEqual(cues.snapshots(during: .mark).filter { !$0.pulsing }.count, 1)
    XCTAssertEqual(director.draw, .complete)
    // The question still arrives in full; it simply does not type itself.
    XCTAssertEqual(director.typedQuestion, OmiCinematicDirector.question)
  }

  // MARK: - The mute control

  func testTheMuteControlMirrorsTheBedsOwnPersistedSetting() {
    let cues = RecordingCues()
    cues.isMusicEnabled = false
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    XCTAssertFalse(director.musicEnabled, "the button reads the persisted control, not a default")

    director.toggleMusic()
    XCTAssertTrue(director.musicEnabled)
    XCTAssertEqual(cues.events.last, .setMusicEnabled(true))

    director.toggleMusic()
    XCTAssertFalse(director.musicEnabled)
    XCTAssertEqual(cues.events.last, .setMusicEnabled(false))
  }

  // MARK: - The caret

  func testTheCaretOnlyExistsInsideThePromptAndLeavesWithTheLastBeat() async {
    let cues = RecordingCues()
    let director = OmiCinematicDirector(timing: .standard, cues: cues, sleep: Self.instantSleep)

    director.start { _ in }
    await advance(director, to: .mark)
    XCTAssertFalse(director.showsCaret)

    await advance(director, to: .windows)
    XCTAssertTrue(director.showsCaret)

    await drain(director)
    XCTAssertFalse(director.showsCaret, "beat 6 takes the caret with it")
  }

  func testTheCaretBlinksOnMacOSsOwnCadence() {
    let half = OmiCinematicCaret.blinkSeconds / 2
    XCTAssertTrue(OmiCinematicCaret.isOn(at: Date(timeIntervalSinceReferenceDate: 0)))
    XCTAssertFalse(OmiCinematicCaret.isOn(at: Date(timeIntervalSinceReferenceDate: half + 0.01)))
    XCTAssertTrue(
      OmiCinematicCaret.isOn(at: Date(timeIntervalSinceReferenceDate: half * 2 + 0.01)))
  }
}
