import Combine
import Foundation
import OmiTheme
import SwiftUI

//  Runs the six beats and publishes what the view draws.
//
//  Everything that could take an unknown amount of time is kept off the sequence's path: the beat
//  loop only ever awaits `sleep`, and beat 5's windows are seeded synchronously at `start()` from a
//  fixed deck. That is what makes the run bounded by construction rather than by a timeout.

// MARK: - The cue seam

/// Everything the director asks of the audio layer.
///
/// A seam, so the cue *decisions* — one per beat, one per dot, a swoosh per card, and a fade rather
/// than a cut on abort — are asserted without an audio device. `OmiOnboardingSound` already gates
/// chrome on the system UI-sound setting and already degrades to silence, so nothing here gates
/// anything a second time.
@MainActor
protocol OmiCinematicCues: AnyObject {
  /// Warm the decoders so the first click of the cinematic is not the one that pays for them.
  func prepare()
  func startMusic()
  func stopMusic(fadeOut: TimeInterval)
  func play(_ effect: OmiSoundEffect)
  /// The bed's own mute control — the one that governs it, since the system's UI-sound switch
  /// governs chrome and the bed is content. Persisted by `OmiSoundController`.
  var isMusicEnabled: Bool { get }
  func setMusicEnabled(_ enabled: Bool)
}

/// `OmiCinematicCues` on the real `OmiOnboardingSound`.
@MainActor
final class OmiSystemCinematicCues: OmiCinematicCues {
  /// `nonisolated` so this can be a default argument: there is no state to initialise, and a
  /// default argument is evaluated outside the main actor even when the callee is on it.
  nonisolated init() {}

  func prepare() { OmiOnboardingSound.prepare() }
  func startMusic() { OmiOnboardingSound.music.start() }
  func stopMusic(fadeOut: TimeInterval) { OmiOnboardingSound.music.stop(fadeOut: fadeOut) }
  func play(_ effect: OmiSoundEffect) { OmiOnboardingSound.effect(effect) }

  var isMusicEnabled: Bool { OmiOnboardingSound.music.isEnabled }

  /// Turning it off fades the bed out (`OmiSoundController` does that itself); turning it back on
  /// has to restart it, because nothing else is going to.
  func setMusicEnabled(_ enabled: Bool) {
    OmiOnboardingSound.music.isEnabled = enabled
    if enabled { OmiOnboardingSound.music.start() }
  }
}

// MARK: - Which timing table

extension OmiCinematicTiming {
  /// The table for the machine as it is configured right now. `nonisolated`, because it is a
  /// default argument and those are evaluated outside the callee's actor.
  static var current: OmiCinematicTiming {
    OmiMotion.reduceMotion ? .reduced : .standard
  }
}

// MARK: - Director

@MainActor
final class OmiCinematicDirector: ObservableObject {
  /// The one seam the beat loop waits on. Injected so a test walks the whole sequence in
  /// microseconds without a clock.
  typealias Sleep = @Sendable (Double) async -> Void

  /// `nonisolated`, because it is a default argument and those are evaluated outside the actor.
  nonisolated static let realSleep: Sleep = { seconds in
    guard seconds > 0 else { return }
    try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
  }

  /// The question that types itself in beat 4.
  static let question = "what was I working on today?"

  /// How the bed leaves. Longer than `OmiOnboardingMusic.defaultFadeOut` when the run completed,
  /// because then it is dissolving into onboarding rather than being cut short.
  static let completedFadeOut: TimeInterval = 2.0
  static let interruptedFadeOut: TimeInterval = OmiOnboardingMusic.defaultFadeOut

  /// Every fourth character. At ~38 ms per character that is a keystroke every 150 ms — texture,
  /// not a typewriter.
  static let keystrokeEvery = 4

  // MARK: Published

  @Published private(set) var stage: OmiCinematicStage = .idle
  /// 0 → 1 across beat 1. The scrim's opacity.
  @Published private(set) var dim: Double = 0
  @Published private(set) var draw = OmiCinematicMarkDraw()
  @Published private(set) var form: OmiCinematicForm = .mark
  /// True once every dot has landed: the mark hands off to its own comet pulse from here.
  @Published private(set) var pulsing = false
  /// Characters of `question` shown so far.
  @Published private(set) var typedCount: Int = 0
  /// Beat 5's windows. Fixed, synthetic, and identical on every run.
  @Published private(set) var windows: [OmiCinematicWindowSpec] = []
  /// How many windows have arrived. Window `i` is in flight until `i < settledCards`.
  @Published private(set) var settledCards: Int = 0
  /// Beat 5 has made room: the prompt has lifted and the grid's space is open. Never closes.
  @Published private(set) var gridOpen = false
  /// Beat 6.
  @Published private(set) var receding = false
  /// Mirrors the bed's persisted mute control, so the button in the corner reads it.
  @Published private(set) var musicEnabled = true

  // MARK: Injected

  let timing: OmiCinematicTiming
  private let cues: OmiCinematicCues
  private let sleep: Sleep

  // MARK: Private

  private var sequence = OmiCinematicSequence()
  private var runTask: Task<Void, Never>?
  private var watchdogTask: Task<Void, Never>?
  private var onFinish: ((OmiCinematicEnd) -> Void)?
  /// Latched. Esc, the Skip button, the last beat and the watchdog can all arrive; exactly one of
  /// them is allowed to hand off.
  private var didFinish = false

  init(
    timing: OmiCinematicTiming = .current,
    cues: OmiCinematicCues = OmiSystemCinematicCues(),
    sleep: @escaping Sleep = OmiCinematicDirector.realSleep
  ) {
    self.timing = timing
    self.cues = cues
    self.sleep = sleep
    self.musicEnabled = cues.isMusicEnabled
  }

  /// Every beat entered so far, for the log line and for tests.
  var visitedBeats: [OmiCinematicBeat] { sequence.visited }

  /// The question, truncated to what beat 4 has typed.
  var typedQuestion: String {
    String(Self.question.prefix(typedCount))
  }

  /// True once the caret should be visible: it arrives with the prompt and leaves with beat 6.
  var showsCaret: Bool {
    form == .prompt && !receding
  }

  // MARK: Lifecycle

  /// Starts the run. `onFinish` is called exactly once, on the main actor, whatever happens.
  func start(onFinish: @escaping (OmiCinematicEnd) -> Void) {
    guard case .idle = sequence.stage, runTask == nil else { return }
    self.onFinish = onFinish

    cues.prepare()
    // The full composition, immediately. There is nothing to wait for and nothing that can arrive
    // late, which is what keeps beat 5 from ever opening onto an empty grid.
    windows = OmiCinematicWindowDeck.windows(count: OmiCinematicGrid.slots)
    armWatchdog()

    runTask = Task { [weak self] in
      await self?.run()
    }
  }

  /// Esc, or the "Skip intro" button.
  func skip() {
    guard let end = sequence.abort() else { return }
    stage = sequence.stage
    finish(end)
  }

  /// The bed's mute control. Muting fades it out; unmuting picks it back up where the run is.
  func toggleMusic() {
    cues.setMusicEnabled(!musicEnabled)
    musicEnabled = cues.isMusicEnabled
  }

  // MARK: The beat loop

  private func run() async {
    while let beat = advance() {
      await play(beat)
      if Task.isCancelled { return }
    }
    // `advance()` returned nil without being cancelled: the sequence ran out of beats.
    guard case .ended(let end) = sequence.stage else { return }
    finish(end)
  }

  /// Enters the next beat and mirrors the sequence into `stage` for the view.
  private func advance() -> OmiCinematicBeat? {
    guard !Task.isCancelled else { return nil }
    let beat = sequence.advance()
    stage = sequence.stage
    return beat
  }

  private func play(_ beat: OmiCinematicBeat) async {
    switch beat {
    case .dim: await playDim()
    case .mark: await playMark()
    case .bar: await playBar()
    case .prompt: await playPrompt()
    case .windows: await playWindows()
    case .recede: await playRecede()
    }
  }

  /// Beat 1. The desktop darkens and the bed fades in under it.
  private func playDim() async {
    cues.play(OmiCinematicCue.effect(for: .dim))
    cues.startMusic()
    animate(timing.dim) { self.dim = 1 }
    await sleep(timing.dim)
  }

  /// Beat 2 — the centrepiece. The eight dots of the Omi mark arrive one at a time, then the
  /// wordmark resolves under them, then the mark takes over its own comet pulse.
  ///
  /// One `placed` progress drives all eight entrances (`OmiCinematicMarkDraw.arrival`), stepped
  /// once per dot so each step carries its own cue and its own spring. Eight independent timers
  /// would be eight things to keep in step with each other and with the audio; one animated
  /// `Double` is one.
  ///
  /// `timing.dotArrivals` is 8 at full pacing and 1 under Reduce Motion — the reduced table asks
  /// for one cross-fade, and eight cues inside 0.30 s would be a rattle rather than eight dots
  /// landing.
  private func playMark() async {
    let steps = max(1, timing.dotArrivals)
    let perStep = timing.dots / Double(steps)

    for step in 1...steps {
      cues.play(OmiCinematicCue.effect(for: .mark))
      // A spring, so a dot lands with a little overshoot: these are fills, and a linear ramp reads
      // as an image appearing rather than as a dot being set down.
      animate(perStep, curve: .spring(response: perStep, dampingFraction: 0.58)) {
        self.draw.placed = Double(step) / Double(steps)
      }
      await sleep(perStep)
      if Task.isCancelled { return }
    }

    // Hand off to the mark's own comet pulse. It is a clock-driven `TimelineView`, not an
    // animation, so it must not start until the arrival has finished travelling.
    pulsing = true

    await sleep(timing.markHold)

    cues.play(.click)
    animate(timing.wordmark) { self.draw.wordmark = 1 }
    await sleep(timing.wordmark)
  }

  /// Beat 3. The mark shrinks into the left of a bar and the wordmark's block becomes the bar.
  private func playBar() async {
    cues.play(OmiCinematicCue.effect(for: .bar))
    animate(timing.bar, curve: .spring(response: timing.bar, dampingFraction: 0.86)) {
      self.form = .bar
    }
    await sleep(timing.bar)
  }

  /// Beat 4. The bar widens into a prompt field, then the question types itself.
  private func playPrompt() async {
    cues.play(OmiCinematicCue.effect(for: .prompt))
    animate(timing.stretch, curve: .spring(response: timing.stretch, dampingFraction: 0.82)) {
      self.form = .prompt
    }
    await sleep(timing.stretch)

    await typeQuestion()
    await sleep(timing.promptHold)
  }

  /// One character at a time, with a keystroke every few characters — every character would be a
  /// stutter, and none at all reads as text being pasted in.
  private func typeQuestion() async {
    let characters = Self.question.count
    guard timing.typing > 0, characters > 0 else {
      typedCount = characters
      return
    }
    let perCharacter = timing.typing / Double(characters)
    for index in 1...characters {
      typedCount = index
      if index.isMultiple(of: Self.keystrokeEvery) { cues.play(.click) }
      await sleep(perCharacter)
      if Task.isCancelled { return }
    }
  }

  /// Beat 5. Windows arrive one at a time, each on its own swoosh.
  private func playWindows() async {
    let count = windows.count
    guard count > 0 else {
      // No windows at all should be impossible — `start()` seeds the whole deck — but a beat that
      // silently does nothing is still better than one that hangs.
      await sleep(timing.windows)
      return
    }

    // Make room first: the prompt lifts and the grid's space opens under it. The lift rides the
    // first window's spring rather than getting a beat of its own.
    animate(timing.cardFlight, curve: .spring(response: timing.cardFlight, dampingFraction: 0.85)) {
      self.gridOpen = true
    }

    for index in 0..<count {
      cues.play(OmiCinematicCue.effect(for: .windows))
      animate(timing.cardFlight, curve: .spring(response: timing.cardFlight, dampingFraction: 0.78)) {
        self.settledCards = index + 1
      }
      await sleep(timing.cardStagger)
      if Task.isCancelled { return }
    }

    // The last window is still flying when the loop ends; let it land before beat 6 starts.
    let flown = timing.cardStagger * Double(count)
    await sleep(max(0, timing.windows - flown))
  }

  /// Beat 6. Everything scales toward where onboarding will be, and the dim lifts.
  private func playRecede() async {
    cues.play(OmiCinematicCue.effect(for: .recede))
    animate(timing.recede) {
      self.receding = true
      self.dim = 0
    }
    await sleep(timing.recede)
  }

  // MARK: Animation

  /// Every mutation the view animates goes through here, so Reduce Motion is applied in one place:
  /// under it, `OmiMotion.withGated` mutates with no animation and the state change is instant —
  /// the beat still happens and still holds for `crossFade`, it just does not travel.
  private func animate(
    _ duration: Double,
    curve: OmiCinematicCurve = .easeOut,
    _ body: () -> Void
  ) {
    OmiMotion.withGated(curve.animation(duration: duration), body)
  }

  // MARK: Ending

  private func armWatchdog() {
    // Deliberately a real sleep and not the injected seam: the watchdog is a guarantee about
    // wall-clock time, and wiring it to a test's instant clock would make it fire immediately and
    // race the run it exists to protect.
    let deadline = timing.watchdogDeadline
    watchdogTask = Task { [weak self] in
      await OmiCinematicDirector.realSleep(deadline)
      guard !Task.isCancelled else { return }
      await MainActor.run { self?.expire() }
    }
  }

  private func expire() {
    guard let end = sequence.expire() else { return }
    stage = sequence.stage
    logError("cinematic stalled in \(end.beat.name); handing off to onboarding")
    finish(end)
  }

  /// The single exit. Latched, so the four things that can end a run cannot hand off twice.
  private func finish(_ end: OmiCinematicEnd) {
    guard !didFinish else { return }
    didFinish = true

    runTask?.cancel()
    runTask = nil
    watchdogTask?.cancel()
    watchdogTask = nil

    // Never a cut, on any path. An abort mid-beat fades faster than a completed run, which is the
    // difference between "stop" and "that's the end of it".
    cues.stopMusic(fadeOut: end.wasInterrupted ? Self.interruptedFadeOut : Self.completedFadeOut)

    log(
      "cinematic ended \(end.wasInterrupted ? "early" : "complete") after "
        + sequence.visited.map(\.name).joined(separator: "→"))

    let handoff = onFinish
    onFinish = nil
    handoff?(end)
  }
}

/// The two curves the cinematic uses, named so `animate` reads as intent.
enum OmiCinematicCurve {
  case easeOut
  /// `response` is the duration the caller budgeted; the spring is tuned to settle inside it.
  case spring(response: Double, dampingFraction: Double)

  func animation(duration: Double) -> Animation {
    switch self {
    case .easeOut:
      return .easeOut(duration: duration)
    case .spring(let response, let damping):
      return .spring(response: max(0.05, response), dampingFraction: damping, blendDuration: 0)
    }
  }
}
