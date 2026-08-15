import Foundation

//  The first-run cinematic's *values*: the beat order, the timing tables, and the cue table.
//
//  Six beats over ~8.6 s, played on one borderless window covering the display under the pointer,
//  which then hands off to the onboarding Omi already has. Every beat carries a sound.
//
//      1  dim      the desktop darkens; the ambient bed fades in
//      2  mark     the eight dots of the Omi mark arrive one at a time, then the wordmark resolves
//      3  bar      mark and wordmark collapse into a single horizontal bar
//      4  prompt   the bar stretches into a prompt field and a question types itself
//      5  windows  window cards fly in on staggered swooshes and settle into a grid
//      6  recede   everything scales toward the onboarding panel's footprint and hands off
//
//  Three rules shape this feature:
//
//  - **Decoration must never be able to block onboarding.** Nothing here throws, nothing here waits
//    on I/O, and `OmiCinematicDirector.finish` is latched and idempotent — Esc, the Skip button, the
//    last beat and the watchdog all land in the same terminal state exactly once.
//  - **The sequence is a value, the timing is a value, and the cues go through a seam.** So the part
//    worth testing — beat order, abort from any beat, reduce-motion collapse, which sound belongs to
//    which beat, where a dot is in its arrival — runs with no window, no clock and no audio device.
//  - **Reduce Motion collapses every beat to a cross-fade.** One timing table
//    (`OmiCinematicTiming.reduced`) does it, so honouring the setting is a lookup rather than a
//    discipline kept beat by beat.

// MARK: - Beats

/// The six beats, in the only order they ever run.
enum OmiCinematicBeat: Int, CaseIterable, Comparable, Sendable {
  case dim = 0
  case mark
  case bar
  case prompt
  case windows
  case recede

  static func < (lhs: OmiCinematicBeat, rhs: OmiCinematicBeat) -> Bool {
    lhs.rawValue < rhs.rawValue
  }

  /// The beat after this one, or `nil` at the end of the sequence.
  var next: OmiCinematicBeat? { OmiCinematicBeat(rawValue: rawValue + 1) }

  /// For logs. Never shown to the user.
  var name: String {
    switch self {
    case .dim: return "dim"
    case .mark: return "mark"
    case .bar: return "bar"
    case .prompt: return "prompt"
    case .windows: return "windows"
    case .recede: return "recede"
    }
  }
}

/// How the run ended. Every case is terminal, and every case hands off to onboarding — there is
/// deliberately no "failed" outcome, because a cinematic that fails still owes the user their
/// onboarding.
enum OmiCinematicEnd: Equatable, Sendable {
  /// All six beats played.
  case completed
  /// Esc, or the "Skip intro" button, during this beat.
  case skipped(OmiCinematicBeat)
  /// The watchdog fired: something stalled past the whole sequence's budget. Should never happen;
  /// exists so that if it does, onboarding still arrives.
  case expired(OmiCinematicBeat)

  /// The beat the run was in when it ended.
  var beat: OmiCinematicBeat {
    switch self {
    case .completed: return .recede
    case .skipped(let beat), .expired(let beat): return beat
    }
  }

  /// True when the run stopped before the last beat. The bed still fades rather than cutting; this
  /// only distinguishes *why* it stopped.
  var wasInterrupted: Bool {
    if case .completed = self { return false }
    return true
  }
}

/// Where the run is. `idle` before `start()`, `ended` after exactly one terminal transition.
enum OmiCinematicStage: Equatable, Sendable {
  case idle
  case playing(OmiCinematicBeat)
  case ended(OmiCinematicEnd)

  var isTerminal: Bool {
    if case .ended = self { return true }
    return false
  }

  /// The beat on screen, or `nil` before the first one and after the last.
  var beat: OmiCinematicBeat? {
    if case .playing(let beat) = self { return beat }
    return nil
  }
}

/// The beat order, as a value, with no clock and no view attached.
///
/// Separate from `OmiCinematicDirector` because ordering and abort are the two things worth
/// asserting and neither needs a display: a test walks this the same way the director does.
struct OmiCinematicSequence: Equatable, Sendable {
  private(set) var stage: OmiCinematicStage = .idle
  /// Every beat the run has entered, in order. The director copies this into its log line, and
  /// tests assert against it rather than against a schedule of sleeps.
  private(set) var visited: [OmiCinematicBeat] = []

  init() {}

  /// Enters the next beat, or ends the run after the last one. A no-op once terminal, so a late
  /// timer cannot walk a finished sequence forward.
  ///
  /// - Returns: the beat now playing, or `nil` when this call ended the run (or found it ended).
  @discardableResult
  mutating func advance() -> OmiCinematicBeat? {
    switch stage {
    case .ended:
      return nil
    case .idle:
      return enter(OmiCinematicBeat.allCases[0])
    case .playing(let beat):
      guard let next = beat.next else {
        stage = .ended(.completed)
        return nil
      }
      return enter(next)
    }
  }

  /// Esc or "Skip intro". Records the beat it interrupted. Idempotent.
  @discardableResult
  mutating func abort() -> OmiCinematicEnd? {
    end(with: .skipped(stage.beat ?? OmiCinematicBeat.allCases[0]))
  }

  /// The watchdog. Idempotent, and never overwrites an end that already happened.
  @discardableResult
  mutating func expire() -> OmiCinematicEnd? {
    end(with: .expired(stage.beat ?? OmiCinematicBeat.allCases[0]))
  }

  private mutating func end(with end: OmiCinematicEnd) -> OmiCinematicEnd? {
    guard !stage.isTerminal else { return nil }
    stage = .ended(end)
    return end
  }

  private mutating func enter(_ beat: OmiCinematicBeat) -> OmiCinematicBeat {
    stage = .playing(beat)
    visited.append(beat)
    return beat
  }
}

// MARK: - Timing

/// Seconds per beat, plus the sub-beat divisions beats 2, 4 and 5 need.
///
/// A table rather than constants scattered through the director, because Reduce Motion is a
/// *different table* and not a set of `if` statements: `reduced` collapses every beat to one
/// cross-fade, and the director reads whichever table it was handed without knowing which it got.
struct OmiCinematicTiming: Equatable, Sendable {
  var dim: Double
  var mark: Double
  var bar: Double
  var prompt: Double
  var windows: Double
  var recede: Double

  /// Beat 2, in order: the eight dots arriving, the hold before the wordmark, and the wordmark
  /// resolving. Sums to `mark` in the standard table.
  var dots: Double
  var markHold: Double
  var wordmark: Double

  /// Beat 4: the stretch, then the question typing itself, then the hold before beat 5.
  var stretch: Double
  var typing: Double
  var promptHold: Double

  /// Beat 5: one card's flight, and the gap between two cards leaving.
  var cardFlight: Double
  var cardStagger: Double

  /// How many separate arrivals beat 2 is divided into — one per dot at full pacing, and exactly
  /// one under Reduce Motion, where eight cues inside a 0.30 s cross-fade would be a rattle rather
  /// than eight dots landing. In the table rather than an `if`, for the same reason every other
  /// difference is.
  var dotArrivals: Int

  /// True when this table is the Reduce Motion one — every beat one cross-fade, no travel.
  var isCrossFade: Bool

  /// The full run.
  var total: Double { dim + mark + bar + prompt + windows + recede }

  /// When the watchdog gives up and hands off to onboarding anyway.
  ///
  /// Generous on purpose: it exists to guarantee onboarding arrives if a beat somehow stalls, not
  /// to police the pacing. A watchdog tight enough to fire during a slow frame would be a bug that
  /// truncates the intro on exactly the machines least able to spare the goodwill.
  var watchdogDeadline: Double { total + Self.watchdogSlack }

  static let watchdogSlack: Double = 6

  func duration(of beat: OmiCinematicBeat) -> Double {
    switch beat {
    case .dim: return dim
    case .mark: return mark
    case .bar: return bar
    case .prompt: return prompt
    case .windows: return windows
    case .recede: return recede
    }
  }

  /// The shipping pacing. Beat 2 is the longest because it is the moment the app introduces itself,
  /// and eight dots landing one at a time is the thing the whole intro is built around.
  static let standard = OmiCinematicTiming(
    dim: 0.60,
    mark: 2.40,
    bar: 0.70,
    prompt: 2.05,
    windows: 2.10,
    recede: 0.75,
    dots: 1.55,
    markHold: 0.25,
    wordmark: 0.60,
    stretch: 0.55,
    typing: 1.15,
    promptHold: 0.35,
    cardFlight: 0.60,
    cardStagger: 0.13,
    dotArrivals: OmiCinematicMarkDraw.dotCount,
    isCrossFade: false)

  /// Reduce Motion. Every beat is the same short cross-fade, every sub-beat is that cross-fade too,
  /// and nothing travels: the beats still *happen*, in order, with their sounds — the run is a
  /// slideshow of the same six states rather than a sequence of moves.
  static let reduced = OmiCinematicTiming(
    dim: crossFade,
    mark: crossFade,
    bar: crossFade,
    prompt: crossFade,
    windows: crossFade,
    recede: crossFade,
    dots: crossFade,
    markHold: 0,
    wordmark: crossFade,
    stretch: crossFade,
    typing: 0,
    promptHold: 0,
    cardFlight: crossFade,
    cardStagger: 0,
    dotArrivals: 1,
    isCrossFade: true)

  /// Long enough to read as a change of state, short enough that six of them are not a wait.
  static let crossFade: Double = 0.30
}

// MARK: - Sound cues

/// Which cue belongs to which beat.
///
/// A table, so "every beat has a sound" is a fact a test can check rather than a claim in a
/// comment. The bed is not in here: it is started by beat 1 and stopped once, at the end, and is
/// therefore lifecycle rather than a cue.
enum OmiCinematicCue {
  /// The one-shot that marks a beat's arrival.
  static func effect(for beat: OmiCinematicBeat) -> OmiSoundEffect {
    switch beat {
    // Beat 1 is the bed arriving; the click is the shutter that starts it.
    case .dim: return .click
    // One tick per dot as it lands — see `OmiCinematicDirector.playMark`.
    case .mark: return .click
    // Two things becoming one.
    case .bar: return .click
    // The swoosh, on the stretch.
    case .prompt: return .swoosh
    // One per card, staggered.
    case .windows: return .swoosh
    // The completion cue: the world has changed and the app is here.
    case .recede: return .chime
    }
  }
}

// MARK: - Animatable state

/// How far beat 2 has got. The director walks this from all-zero to `.complete`.
struct OmiCinematicMarkDraw: Equatable, Sendable {
  /// The eight dots of the Omi mark. Not a coincidence that it is also `OmiCinematicMark`'s ring
  /// size — the arrival math below is expressed in dots, so the two must be the same number.
  static let dotCount = 8

  /// 0 → 1 across the arrival. Dot `i` is placed once this passes `(i + 1) / dotCount`.
  var placed: Double = 0
  /// The "omi" wordmark resolving under the ring.
  var wordmark: Double = 0

  static let complete = OmiCinematicMarkDraw(placed: 1, wordmark: 1)

  /// How far dot `index` is into its own entrance, 0…1.
  ///
  /// `clamp(placed · dotCount − index, 0, 1)`: dot 0 is fully placed by the time `placed` reaches
  /// 1/8, dot 7 does not begin until `placed` reaches 7/8. One progress value therefore drives
  /// eight staggered entrances, which is what lets the whole beat be a single animated `Double`
  /// that SwiftUI can interpolate with a spring — eight independent timers could not stay in step
  /// with each other or with the cue that lands beside them.
  static func arrival(dot index: Int, placed: Double) -> Double {
    guard index >= 0 else { return 0 }
    return min(max(placed * Double(dotCount) - Double(index), 0), 1)
  }

  /// The scale dot `index` is drawn at. Springs are applied by the caller's animation; this is the
  /// value the spring travels *to*, and it starts small enough that the dot reads as being placed
  /// rather than faded up.
  static func entranceScale(dot index: Int, placed: Double) -> Double {
    let arrival = arrival(dot: index, placed: placed)
    return Self.entranceFloor + (1 - Self.entranceFloor) * arrival
  }

  /// Where a dot's entrance starts from. Small, but not zero: a dot that grows from nothing reads
  /// as a bubble, and one that grows from a third of its size reads as being set down.
  static let entranceFloor: Double = 0.34
}

/// What the mark-and-wordmark object currently *is*. One object through all three: the views never
/// change identity, so SwiftUI interpolates the geometry itself and there is nothing to match.
enum OmiCinematicForm: Equatable, Sendable {
  /// Beat 2: the mark large and centred, the wordmark under it.
  case mark
  /// Beat 3: a single horizontal bar.
  case bar
  /// Beats 4–5: the bar stretched into a prompt field.
  case prompt
}
